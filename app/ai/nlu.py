"""Natural Language Understanding — intent classification, entity extraction.

Processes raw customer messages and returns structured NLU results.
Handles Roman Urdu, English, and mixed-language inputs.  All AI calls
go through the provider factory with fallback.  If AI is unavailable,
falls back to keyword-based classification.
"""

from __future__ import annotations

import json
import re
import time
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field

from app.ai.factory import generate_text_with_fallback, get_ai_provider
from app.ai.prompts.nlu import (
    SYSTEM_PROMPT_DISAMBIGUATION,
    SYSTEM_PROMPT_NLU,
    SYSTEM_PROMPT_SENTIMENT,
)
from app.core.constants import AI_MAX_PROMPT_INPUT_LENGTH
from app.core.security import sanitize_for_prompt


# ═══════════════════════════════════════════════════════════════════
# RESULT MODELS
# ═══════════════════════════════════════════════════════════════════


class ExtractedItem(BaseModel):
    """A single item extracted from a customer message.

    Attributes:
        name: Medicine/product name as stated by customer.
        quantity: Numeric quantity (None if not mentioned).
        unit: Unit of measure (strip, box, peti, etc.).
    """

    name: str
    quantity: Optional[int] = None
    unit: Optional[str] = None


class NLUResult(BaseModel):
    """Structured output from NLU processing.

    Attributes:
        intent: Classified intent string.
        items: Extracted medicine items.
        language: Detected language.
        sentiment: Detected sentiment.
        raw_text: Original sanitised text.
        confidence: How confident the classification is.
        used_fallback: Whether keyword fallback was used.
    """

    intent: str = "unclear"
    items: list[ExtractedItem] = Field(default_factory=list)
    language: str = "roman_urdu"
    sentiment: str = "neutral"
    raw_text: str = ""
    confidence: str = "medium"
    used_fallback: bool = False


class SentimentResult(BaseModel):
    """Output from sentiment analysis.

    Attributes:
        sentiment: positive / neutral / negative / urgent.
        escalate: Whether to escalate to human operator.
        reason: Reason for escalation (if any).
    """

    sentiment: str = "neutral"
    escalate: bool = False
    reason: str = ""


class DisambiguationResult(BaseModel):
    """Output from item disambiguation.

    Attributes:
        selected_index: 0-based index into candidates (-1 if none).
        confidence: high / medium / low.
        reasoning: Brief explanation.
    """

    selected_index: int = -1
    confidence: str = "low"
    reasoning: str = ""


# ═══════════════════════════════════════════════════════════════════
# ROMAN URDU NORMALISATION
# ═══════════════════════════════════════════════════════════════════

# Common Roman Urdu number words → digits
_URDU_NUMBER_MAP: dict[str, int] = {
    "ek": 1, "aik": 1, "1": 1,
    "do": 2, "dow": 2, "2": 2,
    "teen": 3, "tin": 3, "3": 3,
    "char": 4, "chaar": 4, "4": 4,
    "panch": 5, "paanch": 5, "5": 5,
    "chay": 6, "chhe": 6, "che": 6, "6": 6,
    "saat": 7, "sat": 7, "7": 7,
    "aath": 8, "aat": 8, "8": 8,
    "nau": 9, "no": 9, "9": 9,
    "das": 10, "dus": 10, "10": 10,
    "bees": 20, "bis": 20, "20": 20,
    "tees": 30, "30": 30,
    "chalees": 40, "40": 40,
    "pachas": 50, "50": 50,
    "sou": 100, "sau": 100, "100": 100,
    "darjan": 12, "dozen": 12,
    "adha": 6, "aadha": 6,  # half dozen
}

# Common unit aliases
_UNIT_ALIASES: dict[str, str] = {
    "strip": "strip",
    "strips": "strip",
    "patti": "strip",
    "peti": "box",
    "box": "box",
    "boxes": "box",
    "carton": "carton",
    "cartons": "carton",
    "dabba": "box",
    "dabbe": "box",
    "dozen": "dozen",
    "darjan": "dozen",
    "vial": "vial",
    "vials": "vial",
    "shishi": "vial",
    "ampoule": "ampoule",
    "amp": "ampoule",
    "sachet": "sachet",
    "sachets": "sachet",
    "packet": "packet",
    "packets": "packet",
    "bottle": "bottle",
    "bottles": "bottle",
    "tube": "tube",
    "tubes": "tube",
}


def normalise_roman_urdu_number(word: str) -> int | None:
    """Convert a Roman Urdu number word to an integer.

    Args:
        word: A word that might represent a number.

    Returns:
        The integer value, or None if not a number.
    """
    return _URDU_NUMBER_MAP.get(word.lower().strip())


def normalise_unit(word: str) -> str | None:
    """Normalise a unit word to canonical form.

    Args:
        word: A word that might represent a unit.

    Returns:
        Canonical unit string, or None.
    """
    return _UNIT_ALIASES.get(word.lower().strip())


def normalise_text(text: str) -> str:
    """Clean and normalise customer text for NLU.

    Lowercases, removes excessive whitespace and special chars.

    Args:
        text: Raw customer message.

    Returns:
        Cleaned text.
    """
    text = text.strip()
    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text)
    # Remove zero-width characters common in WhatsApp
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    return text


# ═══════════════════════════════════════════════════════════════════
# KEYWORD FALLBACK (when AI is unavailable)
# ═══════════════════════════════════════════════════════════════════

_INTENT_KEYWORDS: dict[str, list[str]] = {
    "greet": [
        "salam", "assalam", "hello", "hi", "hey", "aoa",
        "walaikum", "good morning", "good evening",
    ],
    "thanks": ["shukriya", "thanks", "thank", "meharbani", "jazak"],
    "goodbye": ["allah hafiz", "bye", "khuda hafiz", "goodbye", "alvida"],
    "place_order": [
        "order", "chahiye", "bhejo", "mangwa", "dedo", "send",
        "manga", "laga", "daal", "dal",
    ],
    "add_item": ["aur", "add", "bhi", "more", "extra"],
    "remove_item": ["hata", "remove", "nikal", "delete", "cancel item"],
    "view_order": ["dikha", "show", "order dikha", "list", "kya hai"],
    "confirm_order": [
        "confirm", "haan", "yes", "ok", "theek", "sahi",
        "done", "pakka", "bilkul",
    ],
    "cancel_order": ["cancel", "band", "ruko", "nahi", "mat"],
    "ask_price": ["price", "rate", "kitne", "kimat", "qeemat", "kya rate"],
    "ask_stock": ["available", "stock", "hai kya", "milega", "mil"],
    "complain": [
        "complain", "galat", "wrong", "problem", "issue",
        "kharab", "expire", "toota", "broken",
    ],
    "ask_delivery": ["delivery", "kab", "when", "time", "aayega", "bhejoge"],
    "ask_help": ["help", "madad", "kaise", "how", "guide"],
    "reorder": ["dobara", "repeat", "reorder", "pichla", "wahi", "same"],
}


def _keyword_classify(text: str) -> str:
    """Classify intent using keyword matching.

    Args:
        text: Normalised customer text.

    Returns:
        Intent string.
    """
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for intent, keywords in _INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                scores[intent] = scores.get(intent, 0) + 1

    if not scores:
        return "unclear"

    # Return intent with highest keyword matches
    return max(scores, key=scores.get)  # type: ignore[arg-type]


def _keyword_extract_items(text: str) -> list[ExtractedItem]:
    """Extract items using regex patterns (fallback).

    Looks for patterns like "5 strip paracetamol" or "paracetamol 10 box".

    Args:
        text: Normalised customer text.

    Returns:
        List of extracted items.
    """
    items: list[ExtractedItem] = []
    words = text.lower().split()

    i = 0
    while i < len(words):
        word = words[i]

        # Check if this word is a number
        num = normalise_roman_urdu_number(word)
        if num is not None and i + 1 < len(words):
            # Pattern: <number> <unit> <name> OR <number> <name>
            next_word = words[i + 1]
            unit = normalise_unit(next_word)
            if unit and i + 2 < len(words):
                # <number> <unit> <name...>
                name_parts = []
                j = i + 2
                while j < len(words) and not normalise_roman_urdu_number(words[j]):
                    if normalise_unit(words[j]):
                        break
                    name_parts.append(words[j])
                    j += 1
                if name_parts:
                    items.append(ExtractedItem(
                        name=" ".join(name_parts),
                        quantity=num,
                        unit=unit,
                    ))
                    i = j
                    continue
            else:
                # <number> <name...> (no explicit unit)
                name_parts = []
                j = i + 1
                while j < len(words) and not normalise_roman_urdu_number(words[j]):
                    if normalise_unit(words[j]):
                        break
                    name_parts.append(words[j])
                    j += 1
                if name_parts:
                    items.append(ExtractedItem(
                        name=" ".join(name_parts),
                        quantity=num,
                        unit=None,
                    ))
                    i = j
                    continue

        i += 1

    return items


# ═══════════════════════════════════════════════════════════════════
# MAIN NLU FUNCTIONS
# ═══════════════════════════════════════════════════════════════════


async def classify_intent(text: str) -> NLUResult:
    """Classify the intent and extract entities from a customer message.

    Uses AI provider with fallback to keyword classification.

    Args:
        text: Raw customer message text.

    Returns:
        Structured NLUResult.
    """
    clean_text = normalise_text(text)
    safe_text = sanitize_for_prompt(clean_text, max_length=AI_MAX_PROMPT_INPUT_LENGTH)

    start = time.monotonic()

    # Try AI classification
    response = await generate_text_with_fallback(
        system_prompt=SYSTEM_PROMPT_NLU,
        messages=[{"role": "user", "content": safe_text}],
        temperature=0.2,
        max_tokens=512,
    )

    latency_ms = int((time.monotonic() - start) * 1000)

    if response is not None:
        parsed = _parse_nlu_json(response.content, safe_text)
        if parsed is not None:
            logger.info(
                "nlu.classified",
                intent=parsed.intent,
                items_count=len(parsed.items),
                language=parsed.language,
                latency_ms=latency_ms,
            )
            return parsed

    # Fallback to keyword classification
    logger.warning("nlu.falling_back_to_keywords")
    intent = _keyword_classify(clean_text)
    items = _keyword_extract_items(clean_text)

    result = NLUResult(
        intent=intent,
        items=items,
        language="roman_urdu",
        sentiment="neutral",
        raw_text=safe_text,
        confidence="low",
        used_fallback=True,
    )
    logger.info(
        "nlu.keyword_classified",
        intent=result.intent,
        items_count=len(result.items),
        latency_ms=int((time.monotonic() - start) * 1000),
    )
    return result


async def analyze_sentiment(text: str) -> SentimentResult:
    """Analyze sentiment and check for escalation triggers.

    Args:
        text: Customer message text.

    Returns:
        SentimentResult with escalation flag.
    """
    safe_text = sanitize_for_prompt(text, max_length=AI_MAX_PROMPT_INPUT_LENGTH)

    response = await generate_text_with_fallback(
        system_prompt=SYSTEM_PROMPT_SENTIMENT,
        messages=[{"role": "user", "content": safe_text}],
        temperature=0.1,
        max_tokens=256,
    )

    if response is not None:
        parsed = _parse_sentiment_json(response.content)
        if parsed is not None:
            return parsed

    # Fallback: check for negative keywords
    text_lower = text.lower()
    negative_words = ["galat", "wrong", "problem", "angry", "gussa", "pagal"]
    escalation_words = ["insaan", "human", "operator", "manager", "complaint"]

    sentiment = "neutral"
    escalate = False
    if any(w in text_lower for w in negative_words):
        sentiment = "negative"
    if any(w in text_lower for w in escalation_words):
        escalate = True

    return SentimentResult(
        sentiment=sentiment,
        escalate=escalate,
        reason="keyword_fallback" if escalate else "",
    )


async def disambiguate_item(
    customer_text: str,
    candidates: list[dict],
) -> DisambiguationResult:
    """Disambiguate when fuzzy matching returns multiple candidates.

    Args:
        customer_text: What the customer said.
        candidates: List of candidate catalog items with name and details.

    Returns:
        DisambiguationResult with selected index.
    """
    prompt_content = (
        f"Customer said: \"{customer_text}\"\n\n"
        f"Candidates:\n"
    )
    for i, c in enumerate(candidates):
        prompt_content += f"{i}. {c.get('name', '')} — {c.get('details', '')}\n"

    response = await generate_text_with_fallback(
        system_prompt=SYSTEM_PROMPT_DISAMBIGUATION,
        messages=[{"role": "user", "content": prompt_content}],
        temperature=0.1,
        max_tokens=256,
    )

    if response is not None:
        parsed = _parse_disambiguation_json(response.content)
        if parsed is not None:
            return parsed

    # Fallback: select first candidate
    return DisambiguationResult(
        selected_index=0 if candidates else -1,
        confidence="low",
        reasoning="fallback_first_candidate",
    )


# ═══════════════════════════════════════════════════════════════════
# JSON PARSING HELPERS
# ═══════════════════════════════════════════════════════════════════


def _extract_json(text: str) -> str | None:
    """Extract JSON from text that may contain markdown or extra content.

    Handles nested braces so JSON with arrays-of-objects (e.g. NLU
    responses with ``items``) is extracted correctly.

    Args:
        text: Raw AI response that should contain JSON.

    Returns:
        Extracted JSON string, or None.
    """
    # Try to find JSON in code blocks
    match = re.search(r"```(?:json)?\s*(\{.+?\})\s*```", text, re.DOTALL)
    if match:
        candidate = match.group(1)
        try:
            json.loads(candidate)
            return candidate
        except (json.JSONDecodeError, TypeError):
            pass

    # Brace-depth scan — find the outermost { … } pair
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None


def _parse_nlu_json(text: str, raw_text: str) -> NLUResult | None:
    """Parse AI response into NLUResult.

    Args:
        text: Raw AI response.
        raw_text: Original customer text.

    Returns:
        NLUResult or None on parse failure.
    """
    try:
        json_str = _extract_json(text)
        if not json_str:
            return None

        data = json.loads(json_str)
        items = []
        for item_data in data.get("items", []):
            if isinstance(item_data, dict) and item_data.get("name"):
                items.append(ExtractedItem(
                    name=item_data["name"],
                    quantity=item_data.get("quantity"),
                    unit=item_data.get("unit"),
                ))

        return NLUResult(
            intent=data.get("intent", "unclear"),
            items=items,
            language=data.get("language", "roman_urdu"),
            sentiment=data.get("sentiment", "neutral"),
            raw_text=raw_text,
            confidence="high",
            used_fallback=False,
        )
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        logger.warning("nlu.json_parse_failed", error=str(exc))
        return None


def _parse_sentiment_json(text: str) -> SentimentResult | None:
    """Parse AI response into SentimentResult.

    Args:
        text: Raw AI response.

    Returns:
        SentimentResult or None.
    """
    try:
        json_str = _extract_json(text)
        if not json_str:
            return None

        data = json.loads(json_str)
        return SentimentResult(
            sentiment=data.get("sentiment", "neutral"),
            escalate=bool(data.get("escalate", False)),
            reason=data.get("reason", ""),
        )
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def _parse_disambiguation_json(text: str) -> DisambiguationResult | None:
    """Parse AI response into DisambiguationResult.

    Args:
        text: Raw AI response.

    Returns:
        DisambiguationResult or None.
    """
    try:
        json_str = _extract_json(text)
        if not json_str:
            return None

        data = json.loads(json_str)
        return DisambiguationResult(
            selected_index=int(data.get("selected_index", -1)),
            confidence=data.get("confidence", "low"),
            reasoning=data.get("reasoning", ""),
        )
    except (json.JSONDecodeError, TypeError, KeyError, ValueError):
        return None
