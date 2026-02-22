"""Unit tests for NLU — intent classification and entity extraction.

Tests use mocked AI providers to verify parsing logic, keyword fallback,
Roman Urdu normalisation, and JSON extraction.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.ai.nlu import (
    DisambiguationResult,
    ExtractedItem,
    NLUResult,
    SentimentResult,
    _extract_json,
    _keyword_classify,
    _keyword_extract_items,
    _parse_nlu_json,
    classify_intent,
    analyze_sentiment,
    disambiguate_item,
    normalise_roman_urdu_number,
    normalise_text,
    normalise_unit,
)


# ═══════════════════════════════════════════════════════════════════
# ROMAN URDU NORMALISATION
# ═══════════════════════════════════════════════════════════════════


class TestNormaliseRomanUrduNumber:
    def test_basic_numbers(self):
        assert normalise_roman_urdu_number("ek") == 1
        assert normalise_roman_urdu_number("do") == 2
        assert normalise_roman_urdu_number("teen") == 3
        assert normalise_roman_urdu_number("das") == 10
        assert normalise_roman_urdu_number("darjan") == 12

    def test_alternate_spellings(self):
        assert normalise_roman_urdu_number("aik") == 1
        assert normalise_roman_urdu_number("chaar") == 4
        assert normalise_roman_urdu_number("paanch") == 5
        assert normalise_roman_urdu_number("sau") == 100

    def test_unknown_word(self):
        assert normalise_roman_urdu_number("paracetamol") is None
        assert normalise_roman_urdu_number("xyz") is None


class TestNormaliseUnit:
    def test_basic_units(self):
        assert normalise_unit("strip") == "strip"
        assert normalise_unit("strips") == "strip"
        assert normalise_unit("peti") == "box"
        assert normalise_unit("box") == "box"
        assert normalise_unit("darjan") == "dozen"

    def test_urdu_aliases(self):
        assert normalise_unit("patti") == "strip"
        assert normalise_unit("dabba") == "box"
        assert normalise_unit("shishi") == "vial"

    def test_unknown_unit(self):
        assert normalise_unit("paracetamol") is None


class TestNormaliseText:
    def test_strips_whitespace(self):
        assert normalise_text("  hello  world  ") == "hello world"

    def test_removes_zero_width_chars(self):
        assert normalise_text("hello\u200bworld") == "helloworld"


# ═══════════════════════════════════════════════════════════════════
# KEYWORD CLASSIFICATION (fallback)
# ═══════════════════════════════════════════════════════════════════


class TestKeywordClassify:
    def test_greet(self):
        assert _keyword_classify("assalam o alaikum") == "greet"
        assert _keyword_classify("hello bhai") == "greet"

    def test_order(self):
        assert _keyword_classify("paracetamol dedo") == "place_order"

    def test_cancel(self):
        assert _keyword_classify("cancel karo ye") == "cancel_order"

    def test_complain(self):
        assert _keyword_classify("galat medicine aayi hai") == "complain"

    def test_delivery(self):
        assert _keyword_classify("delivery kab hogi") == "ask_delivery"

    def test_unclear(self):
        assert _keyword_classify("xyz abc 123") == "unclear"

    def test_reorder(self):
        assert _keyword_classify("pichla dobara wahi dena") == "reorder"


class TestKeywordExtractItems:
    def test_number_unit_name(self):
        items = _keyword_extract_items("5 strip paracetamol")
        assert len(items) == 1
        assert items[0].name == "paracetamol"
        assert items[0].quantity == 5
        assert items[0].unit == "strip"

    def test_urdu_number(self):
        items = _keyword_extract_items("teen peti augmentin")
        assert len(items) == 1
        assert items[0].name == "augmentin"
        assert items[0].quantity == 3
        assert items[0].unit == "box"

    def test_number_without_unit(self):
        items = _keyword_extract_items("10 paracetamol")
        assert len(items) == 1
        assert items[0].name == "paracetamol"
        assert items[0].quantity == 10
        assert items[0].unit is None

    def test_no_items(self):
        items = _keyword_extract_items("hello how are you")
        assert len(items) == 0


# ═══════════════════════════════════════════════════════════════════
# JSON EXTRACTION
# ═══════════════════════════════════════════════════════════════════


class TestExtractJson:
    def test_bare_json(self):
        result = _extract_json('{"intent": "greet"}')
        assert result == '{"intent": "greet"}'

    def test_json_in_code_block(self):
        text = '```json\n{"intent": "greet"}\n```'
        result = _extract_json(text)
        assert result == '{"intent": "greet"}'

    def test_json_with_surrounding_text(self):
        text = 'Here is the result: {"intent": "greet"} end'
        result = _extract_json(text)
        assert result == '{"intent": "greet"}'

    def test_no_json(self):
        assert _extract_json("no json here") is None


class TestParseNluJson:
    def test_valid_response(self):
        ai_response = json.dumps({
            "intent": "place_order",
            "items": [{"name": "paracetamol", "quantity": 5, "unit": "strip"}],
            "language": "roman_urdu",
            "sentiment": "neutral",
        })
        result = _parse_nlu_json(ai_response, "5 strip paracetamol")
        assert result is not None
        assert result.intent == "place_order"
        assert len(result.items) == 1
        assert result.items[0].name == "paracetamol"
        assert result.items[0].quantity == 5

    def test_empty_items(self):
        ai_response = json.dumps({
            "intent": "greet",
            "items": [],
            "language": "roman_urdu",
            "sentiment": "positive",
        })
        result = _parse_nlu_json(ai_response, "hello")
        assert result is not None
        assert result.intent == "greet"
        assert len(result.items) == 0

    def test_invalid_json(self):
        result = _parse_nlu_json("not json", "test")
        assert result is None

    def test_items_without_name_ignored(self):
        ai_response = json.dumps({
            "intent": "place_order",
            "items": [{"name": "", "quantity": 5}],
            "language": "mixed",
            "sentiment": "neutral",
        })
        result = _parse_nlu_json(ai_response, "test")
        assert result is not None
        assert len(result.items) == 0  # empty name filtered out


# ═══════════════════════════════════════════════════════════════════
# AI-POWERED NLU (mocked provider)
# ═══════════════════════════════════════════════════════════════════


class TestClassifyIntent:
    """Test classify_intent with mocked AI provider."""

    @pytest.mark.asyncio
    async def test_ai_classification(self):
        """Test successful AI-powered intent classification."""
        mock_response = AsyncMock()
        mock_response.content = json.dumps({
            "intent": "place_order",
            "items": [{"name": "paracetamol", "quantity": 5, "unit": "strip"}],
            "language": "roman_urdu",
            "sentiment": "neutral",
        })
        mock_response.tokens_used_output = 50

        with patch(
            "app.ai.nlu.generate_text_with_fallback",
            return_value=mock_response,
        ):
            result = await classify_intent("5 strip paracetamol chahiye")
            assert result.intent == "place_order"
            assert len(result.items) == 1
            assert result.used_fallback is False

    @pytest.mark.asyncio
    async def test_ai_failure_falls_back_to_keywords(self):
        """Test keyword fallback when AI returns None."""
        with patch(
            "app.ai.nlu.generate_text_with_fallback",
            return_value=None,
        ):
            result = await classify_intent("assalam o alaikum")
            assert result.intent == "greet"
            assert result.used_fallback is True
            assert result.confidence == "low"

    @pytest.mark.asyncio
    async def test_ai_returns_bad_json_falls_back(self):
        """Test keyword fallback when AI returns unparseable JSON."""
        mock_response = AsyncMock()
        mock_response.content = "I'm not sure what you mean"
        mock_response.tokens_used_output = 10

        with patch(
            "app.ai.nlu.generate_text_with_fallback",
            return_value=mock_response,
        ):
            result = await classify_intent("galat medicine di hai")
            assert result.intent == "complain"
            assert result.used_fallback is True

    @pytest.mark.asyncio
    async def test_multiple_items_extraction(self):
        """Test extraction of multiple items from AI response."""
        mock_response = AsyncMock()
        mock_response.content = json.dumps({
            "intent": "place_order",
            "items": [
                {"name": "augmentin", "quantity": 3, "unit": "peti"},
                {"name": "flagyl", "quantity": 2, "unit": "strip"},
            ],
            "language": "roman_urdu",
            "sentiment": "neutral",
        })
        mock_response.tokens_used_output = 80

        with patch(
            "app.ai.nlu.generate_text_with_fallback",
            return_value=mock_response,
        ):
            result = await classify_intent("teen peti augmentin aur do strip flagyl")
            assert result.intent == "place_order"
            assert len(result.items) == 2
            assert result.items[0].name == "augmentin"
            assert result.items[1].name == "flagyl"


class TestAnalyzeSentiment:
    @pytest.mark.asyncio
    async def test_ai_sentiment(self):
        mock_response = AsyncMock()
        mock_response.content = json.dumps({
            "sentiment": "negative",
            "escalate": True,
            "reason": "Customer is frustrated",
        })

        with patch(
            "app.ai.nlu.generate_text_with_fallback",
            return_value=mock_response,
        ):
            result = await analyze_sentiment("galat medicine aayi aur koi sunta nahi")
            assert result.sentiment == "negative"
            assert result.escalate is True

    @pytest.mark.asyncio
    async def test_fallback_sentiment(self):
        with patch(
            "app.ai.nlu.generate_text_with_fallback",
            return_value=None,
        ):
            result = await analyze_sentiment("galat medicine aayi")
            assert result.sentiment == "negative"


class TestDisambiguateItem:
    @pytest.mark.asyncio
    async def test_ai_disambiguation(self):
        mock_response = AsyncMock()
        mock_response.content = json.dumps({
            "selected_index": 1,
            "confidence": "high",
            "reasoning": "Exact match for brand name",
        })

        with patch(
            "app.ai.nlu.generate_text_with_fallback",
            return_value=mock_response,
        ):
            result = await disambiguate_item(
                "augmentin",
                [
                    {"name": "Augmentin 375mg", "details": "GSK"},
                    {"name": "Augmentin 625mg", "details": "GSK"},
                ],
            )
            assert result.selected_index == 1
            assert result.confidence == "high"

    @pytest.mark.asyncio
    async def test_fallback_disambiguation(self):
        with patch(
            "app.ai.nlu.generate_text_with_fallback",
            return_value=None,
        ):
            result = await disambiguate_item("test", [{"name": "A"}, {"name": "B"}])
            assert result.selected_index == 0
            assert result.confidence == "low"
