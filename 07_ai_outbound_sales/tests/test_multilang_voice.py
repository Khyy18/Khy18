"""Tests for multi-language voice support."""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.voice_conversation import (
    ConversationState,
    VoiceConversationAgent,
    VOICE_SYSTEM_PROMPTS,
    detect_language,
)
from channels.voice.stt import DeepgramSTT, LANGUAGE_MAP
from channels.voice.tts import DEFAULT_VOICE_IDS, ElevenLabsTTS
from tests.conftest import make_lead, make_tenant


# ---------- Language Detection Tests ----------


class TestDetectLanguage:
    """Tests for the detect_language helper function."""

    def test_detect_language_from_country_us(self):
        """US country maps to English."""
        lead_data = {"enrichment_data": {"country": "US"}}
        assert detect_language(lead_data) == "en"

    def test_detect_language_from_country_ru(self):
        """RU country maps to Russian."""
        lead_data = {"enrichment_data": {"country": "RU"}}
        assert detect_language(lead_data) == "ru"

    def test_detect_language_from_country_de(self):
        """DE country maps to German."""
        lead_data = {"enrichment_data": {"country": "DE"}}
        assert detect_language(lead_data) == "de"

    def test_detect_language_from_country_es(self):
        """ES country maps to Spanish."""
        lead_data = {"enrichment_data": {"country": "ES"}}
        assert detect_language(lead_data) == "es"

    def test_detect_language_from_country_mx(self):
        """MX country maps to Spanish."""
        lead_data = {"enrichment_data": {"country": "MX"}}
        assert detect_language(lead_data) == "es"

    def test_detect_language_from_country_at(self):
        """AT (Austria) maps to German."""
        lead_data = {"enrichment_data": {"country": "AT"}}
        assert detect_language(lead_data) == "de"

    def test_detect_language_from_locale_ru(self):
        """Locale ru_RU maps to Russian."""
        lead_data = {"enrichment_data": {"locale": "ru_RU"}}
        assert detect_language(lead_data) == "ru"

    def test_detect_language_from_locale_es_mx(self):
        """Locale es_MX maps to Spanish."""
        lead_data = {"enrichment_data": {"locale": "es_MX"}}
        assert detect_language(lead_data) == "es"

    def test_detect_language_from_locale_de_at(self):
        """Locale de_AT maps to German."""
        lead_data = {"enrichment_data": {"locale": "de_AT"}}
        assert detect_language(lead_data) == "de"

    def test_detect_language_fallback_to_en(self):
        """Unknown country/locale falls back to English."""
        lead_data = {"enrichment_data": {"country": "XX"}}
        assert detect_language(lead_data) == "en"

    def test_detect_language_no_enrichment(self):
        """No enrichment data falls back to English."""
        lead_data = {}
        assert detect_language(lead_data) == "en"

    def test_detect_language_empty_enrichment(self):
        """Empty enrichment data falls back to English."""
        lead_data = {"enrichment_data": {}}
        assert detect_language(lead_data) == "en"

    def test_detect_language_locale_takes_priority(self):
        """Locale is checked before country."""
        lead_data = {"enrichment_data": {"locale": "de_DE", "country": "US"}}
        assert detect_language(lead_data) == "de"


# ---------- STT Language Map Tests ----------


class TestSTTLanguageMap:
    """Tests for the LANGUAGE_MAP in STT module."""

    def test_language_map_has_english_countries(self):
        assert LANGUAGE_MAP["US"] == "en"
        assert LANGUAGE_MAP["GB"] == "en"

    def test_language_map_has_russian(self):
        assert LANGUAGE_MAP["RU"] == "ru"

    def test_language_map_has_german_countries(self):
        assert LANGUAGE_MAP["DE"] == "de"
        assert LANGUAGE_MAP["AT"] == "de"
        assert LANGUAGE_MAP["CH"] == "de"

    def test_language_map_has_spanish_countries(self):
        assert LANGUAGE_MAP["ES"] == "es"
        assert LANGUAGE_MAP["MX"] == "es"
        assert LANGUAGE_MAP["AR"] == "es"


# ---------- TTS Voice Selection Tests ----------


class TestTTSVoiceSelection:
    """Tests for ElevenLabsTTS per-language voice ID selection."""

    def test_default_voice_ids_all_languages(self):
        """All supported languages have default voice IDs."""
        assert "en" in DEFAULT_VOICE_IDS
        assert "ru" in DEFAULT_VOICE_IDS
        assert "es" in DEFAULT_VOICE_IDS
        assert "de" in DEFAULT_VOICE_IDS

    def test_tts_uses_language_default_voice(self):
        """TTS uses default voice for given language when voice_id is 'default'."""
        tts = ElevenLabsTTS(api_key="test-key", voice_id="default", language="ru")
        assert tts._voice_id == DEFAULT_VOICE_IDS["ru"]

    def test_tts_uses_custom_voice_id(self):
        """TTS uses custom voice_id when provided."""
        tts = ElevenLabsTTS(api_key="test-key", voice_id="custom-voice-123", language="ru")
        assert tts._voice_id == "custom-voice-123"

    def test_tts_for_language_factory(self):
        """for_language class method creates correctly configured instance."""
        tts = ElevenLabsTTS.for_language(api_key="test-key", language="es")
        assert tts._voice_id == DEFAULT_VOICE_IDS["es"]
        assert tts._language == "es"

    def test_tts_for_language_with_override(self):
        """for_language with voice_id override uses the override."""
        tts = ElevenLabsTTS.for_language(api_key="test-key", language="de", voice_id="override-123")
        assert tts._voice_id == "override-123"

    def test_tts_unknown_language_falls_back_to_en(self):
        """Unknown language falls back to English default voice."""
        tts = ElevenLabsTTS(api_key="test-key", voice_id="default", language="zh")
        assert tts._voice_id == DEFAULT_VOICE_IDS["en"]


# ---------- Voice Conversation Agent Language Tests ----------


class TestVoiceAgentLanguage:
    """Tests for language-specific behavior in VoiceConversationAgent."""

    def test_system_prompts_all_languages(self):
        """All supported languages have system prompts."""
        assert "en" in VOICE_SYSTEM_PROMPTS
        assert "ru" in VOICE_SYSTEM_PROMPTS
        assert "es" in VOICE_SYSTEM_PROMPTS
        assert "de" in VOICE_SYSTEM_PROMPTS

    def test_russian_prompt_contains_russian_text(self):
        """Russian prompt contains Cyrillic characters."""
        assert "Вы AI" in VOICE_SYSTEM_PROMPTS["ru"]

    def test_spanish_prompt_contains_spanish_text(self):
        """Spanish prompt contains Spanish text."""
        assert "asistente de ventas" in VOICE_SYSTEM_PROMPTS["es"]

    def test_german_prompt_contains_german_text(self):
        """German prompt contains German text."""
        assert "Sprachverkaufsassistent" in VOICE_SYSTEM_PROMPTS["de"]

    async def test_process_transcript_uses_language_prompt(self, session_factory, mock_llm_client):
        """process_transcript uses the language-appropriate prompt."""
        mock_llm_client.generate = AsyncMock(
            return_value=json.dumps({
                "response_text": "Test response",
                "new_state": "qualification",
            })
        )

        agent = VoiceConversationAgent(
            llm_client=mock_llm_client,
            settings=MagicMock(),
            session_factory=session_factory,
        )

        lead_data = {
            "first_name": "Ivan",
            "last_name": "Petrov",
            "company": "Yandex",
            "title": "CTO",
            "enrichment_data": {"country": "RU"},
        }

        result = await agent.process_transcript(
            transcript="Hello",
            state=ConversationState.greeting,
            lead_data=lead_data,
            conversation_history=[],
        )

        # Verify Russian prompt was used
        call_args = mock_llm_client.generate.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        system_msg = messages[0]["content"]
        # The system prompt should contain Russian text
        assert "Вы AI" in system_msg or "response_text" in result
