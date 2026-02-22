"""RapidFuzz-based medicine fuzzy matcher.

Provides multi-field scoring against a distributor's catalog.
Fields matched (by weight):

* ``medicine_name``  — weight 1.0 (primary)
* ``generic_name``   — weight 0.85
* ``brand_name``     — weight 0.80
* ``search_keywords`` — weight 0.75 (best keyword score)

A composite score is the maximum weighted score across all fields.
Results are sorted descending by score and capped at ``max_results``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

from loguru import logger
from rapidfuzz import fuzz, process

from app.core.constants import FUZZY_MATCH_HIGH_CONFIDENCE, FUZZY_MATCH_THRESHOLD
from app.db.models.catalog import CatalogItem


# ═══════════════════════════════════════════════════════════════════
# DATA TYPES
# ═══════════════════════════════════════════════════════════════════


@dataclass(slots=True, frozen=True)
class FuzzyMatchResult:
    """Single fuzzy-match result.

    Attributes:
        item: The matched catalog item.
        score: Composite similarity score (0-100).
        matched_field: Which field produced the best score.
        is_high_confidence: Whether the score exceeds the high
            confidence threshold (auto-selectable).
    """

    item: CatalogItem
    score: float
    matched_field: str
    is_high_confidence: bool


@dataclass(slots=True)
class FuzzyMatchResponse:
    """Complete response from a fuzzy-matching operation.

    Attributes:
        query: The normalised query string.
        matches: Ranked list of match results.
        auto_selected: The single result when exactly one match
            exceeds the high-confidence threshold and is the only
            result, or ``None``.
        needs_disambiguation: True when there are multiple matches
            above threshold but none is clearly dominant.
    """

    query: str
    matches: list[FuzzyMatchResult] = field(default_factory=list)
    auto_selected: Optional[FuzzyMatchResult] = None
    needs_disambiguation: bool = False


# ═══════════════════════════════════════════════════════════════════
# TEXT NORMALISATION
# ═══════════════════════════════════════════════════════════════════

# Common Roman Urdu → English medicine name substitutions
_ROMAN_URDU_MEDICINE_MAP: dict[str, str] = {
    "panadol": "panadol",
    "parcetamol": "paracetamol",
    "paracitamol": "paracetamol",
    "parasitamol": "paracetamol",
    "peracetamol": "paracetamol",
    "parasetamol": "paracetamol",
    "amxcillin": "amoxicillin",
    "amoxcilin": "amoxicillin",
    "amoxicilin": "amoxicillin",
    "augmentin": "augmentin",
    "augmantin": "augmentin",
    "flagyl": "flagyl",
    "flagil": "flagyl",
    "brufn": "brufen",
    "broofen": "brufen",
    "disprin": "disprin",
    "dispren": "disprin",
    "septran": "septran",
    "septra": "septran",
}

# Regex to extract strength components like "500mg", "250 mg", "625"
_STRENGTH_PATTERN = re.compile(
    r"(\d+)\s*(mg|ml|gm|mcg|iu|%)?",
    re.IGNORECASE,
)


def _normalise_query(text: str) -> str:
    """Normalise a user query for matching.

    Lowercases, removes excessive whitespace and special chars,
    applies common Roman Urdu corrections.

    Args:
        text: Raw user input text.

    Returns:
        Cleaned and normalised query string.
    """
    text = text.strip().lower()
    # Remove zero-width chars
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text)
    # Apply Roman Urdu corrections word-by-word
    words = text.split()
    corrected = [_ROMAN_URDU_MEDICINE_MAP.get(w, w) for w in words]
    return " ".join(corrected)


def _extract_strength(text: str) -> str | None:
    """Extract strength component from query text.

    Args:
        text: Normalised query text.

    Returns:
        Extracted strength string (e.g., "500mg") or None.
    """
    match = _STRENGTH_PATTERN.search(text)
    if match:
        number = match.group(1)
        unit = (match.group(2) or "").lower()
        return f"{number}{unit}"
    return None


def _strip_strength(text: str) -> str:
    """Remove strength components from query for name-only matching.

    Args:
        text: Normalised query text.

    Returns:
        Query with strength components removed.
    """
    return _STRENGTH_PATTERN.sub("", text).strip()


# ═══════════════════════════════════════════════════════════════════
# FIELD WEIGHTS
# ═══════════════════════════════════════════════════════════════════

_FIELD_WEIGHTS: dict[str, float] = {
    "medicine_name": 1.0,
    "generic_name": 0.85,
    "brand_name": 0.80,
    "search_keywords": 0.75,
}


# ═══════════════════════════════════════════════════════════════════
# CORE MATCHER
# ═══════════════════════════════════════════════════════════════════


def _score_item(
    query: str,
    query_strength: str | None,
    item: CatalogItem,
) -> tuple[float, str]:
    """Score a single catalog item against the query.

    Uses a combination of token_sort_ratio and partial_ratio
    (taking the max) for each field, weighted by field importance.
    Strength matching adds a bonus.

    Args:
        query: Normalised query string (strength stripped).
        query_strength: Extracted strength string, or None.
        item: Catalog item to score against.

    Returns:
        Tuple of (best composite score, matched field name).
    """
    best_score = 0.0
    best_field = "medicine_name"

    for field_name, weight in _FIELD_WEIGHTS.items():
        if field_name == "search_keywords":
            # Score against each keyword, keep the best
            keywords = item.search_keywords or []
            for kw in keywords:
                if not kw:
                    continue
                kw_lower = kw.lower()
                raw = max(
                    fuzz.token_sort_ratio(query, kw_lower),
                    fuzz.partial_ratio(query, kw_lower),
                )
                weighted = raw * weight
                if weighted > best_score:
                    best_score = weighted
                    best_field = field_name
        else:
            value = getattr(item, field_name, None)
            if not value:
                continue
            value_lower = value.lower()
            raw = max(
                fuzz.token_sort_ratio(query, value_lower),
                fuzz.partial_ratio(query, value_lower),
            )
            weighted = raw * weight
            if weighted > best_score:
                best_score = weighted
                best_field = field_name

    # Strength bonus: if the query has a strength and the item's
    # strength or medicine_name contains it, add a bonus
    if query_strength and best_score >= FUZZY_MATCH_THRESHOLD:
        item_strength = (item.strength or "").lower().replace(" ", "")
        item_name = (item.medicine_name or "").lower().replace(" ", "")
        if query_strength in item_strength or query_strength in item_name:
            best_score = min(best_score + 5.0, 100.0)

    return best_score, best_field


def fuzzy_match_medicine(
    query: str,
    catalog: Sequence[CatalogItem],
    *,
    threshold: float = FUZZY_MATCH_THRESHOLD,
    high_confidence: float = FUZZY_MATCH_HIGH_CONFIDENCE,
    max_results: int = 10,
) -> FuzzyMatchResponse:
    """Find the best-matching catalog items for a user query.

    Applies multi-field fuzzy matching with RapidFuzz scoring.
    Results are sorted by score descending and capped at
    ``max_results``.

    Auto-selection occurs when exactly one match is above the
    high-confidence threshold OR the top match score is >= 95
    and > second-best by at least 10 points.

    Args:
        query: Customer text describing a medicine.
        catalog: Full active catalog for the distributor.
        threshold: Minimum score to include in results.
        high_confidence: Score above which auto-selection is
            considered.
        max_results: Maximum number of results to return.

    Returns:
        FuzzyMatchResponse with ranked matches and auto-selection
        info.
    """
    if not query or not query.strip():
        logger.debug("fuzzy_match.empty_query")
        return FuzzyMatchResponse(query="")

    normalised = _normalise_query(query)
    query_strength = _extract_strength(normalised)
    query_for_name = _strip_strength(normalised)

    if not query_for_name.strip():
        query_for_name = normalised

    logger.debug(
        "fuzzy_match.start",
        query=normalised,
        query_for_name=query_for_name,
        strength=query_strength,
        catalog_size=len(catalog),
    )

    if not catalog:
        logger.debug("fuzzy_match.empty_catalog")
        return FuzzyMatchResponse(query=normalised)

    # Score all items
    scored: list[tuple[float, str, CatalogItem]] = []
    for item in catalog:
        score, matched_field = _score_item(
            query_for_name,
            query_strength,
            item,
        )
        if score >= threshold:
            scored.append((score, matched_field, item))

    # Sort descending by score
    scored.sort(key=lambda x: x[0], reverse=True)

    # Cap results
    scored = scored[:max_results]

    matches = [
        FuzzyMatchResult(
            item=item,
            score=score,
            matched_field=matched_field,
            is_high_confidence=score >= high_confidence,
        )
        for score, matched_field, item in scored
    ]

    # Determine auto-selection
    auto_selected: FuzzyMatchResult | None = None
    needs_disambiguation = False

    if len(matches) == 1 and matches[0].is_high_confidence:
        auto_selected = matches[0]
    elif len(matches) >= 2:
        top = matches[0]
        second = matches[1]
        if top.score >= 95.0 and (top.score - second.score) >= 10.0:
            auto_selected = top
        elif top.is_high_confidence and not second.is_high_confidence:
            auto_selected = top
        else:
            needs_disambiguation = True
    elif len(matches) == 1:
        # Single match but not high-confidence
        needs_disambiguation = True

    logger.info(
        "fuzzy_match.complete",
        query=normalised,
        match_count=len(matches),
        top_score=matches[0].score if matches else 0.0,
        auto_selected=auto_selected is not None,
        needs_disambiguation=needs_disambiguation,
    )

    return FuzzyMatchResponse(
        query=normalised,
        matches=matches,
        auto_selected=auto_selected,
        needs_disambiguation=needs_disambiguation,
    )


def format_match_options(
    matches: list[FuzzyMatchResult],
    *,
    language: str = "roman_urdu",
) -> str:
    """Format fuzzy matches as a numbered list for WhatsApp display.

    Args:
        matches: Ranked list of match results.
        language: Language for the header text.

    Returns:
        Formatted string with numbered options.
    """
    if not matches:
        if language == "english":
            return "No matching medicines found."
        return "Koi medicine nahi mili."

    lines: list[str] = []
    for i, m in enumerate(matches, 1):
        item = m.item
        strength = f" {item.strength}" if item.strength else ""
        form = f" {item.form}" if item.form else ""
        price_rs = item.price_per_unit_paisas / 100
        line = f"{i}. {item.medicine_name}{strength}{form} — Rs.{price_rs:,.0f}"
        if m.is_high_confidence:
            line += " ✓"
        lines.append(line)

    if language == "english":
        header = "I found these matches:"
    else:
        header = "Ye medicines mili hain:"

    return header + "\n" + "\n".join(lines)
