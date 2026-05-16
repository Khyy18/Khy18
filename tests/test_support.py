"""Tests for the support module: KnowledgeBase and SupportChatbot."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from support.chatbot import SupportChatbot
from support.knowledge_base import KnowledgeBase


class TestKnowledgeBase:
    """Tests for KnowledgeBase."""

    def test_add_entry_increases_count(self):
        kb = KnowledgeBase()
        assert kb.entry_count == 0
        kb.add_entry("1", "How to start?", "Use the /start command.")
        assert kb.entry_count == 1

    def test_search_returns_relevant(self):
        kb = KnowledgeBase()
        kb.add_entry("1", "How to start the bot?", "Send /start command.")
        kb.add_entry("2", "What is the price?", "Plans start at $10/month.")
        kb.add_entry("3", "How to stop trading?", "Use /stop command.")

        results = kb.search("start bot", top_k=2)
        assert len(results) > 0
        assert results[0]["question"] == "How to start the bot?"

    def test_search_returns_similarity(self):
        kb = KnowledgeBase()
        kb.add_entry("1", "How to configure API keys?", "Go to settings and enter keys.")

        results = kb.search("configure API keys", top_k=1)
        assert len(results) == 1
        assert "similarity" in results[0]
        assert 0 <= results[0]["similarity"] <= 1.0

    def test_search_empty_kb(self):
        kb = KnowledgeBase()
        results = kb.search("anything")
        assert results == []

    def test_search_empty_query(self):
        kb = KnowledgeBase()
        kb.add_entry("1", "Test", "Answer")
        results = kb.search("")
        assert results == []

    def test_preload_defaults(self):
        kb = KnowledgeBase()
        kb.preload_defaults()
        assert kb.entry_count > 0

    def test_search_top_k_limit(self):
        kb = KnowledgeBase()
        for i in range(10):
            kb.add_entry(str(i), f"Question {i} about topic", f"Answer {i}")
        results = kb.search("question topic", top_k=3)
        assert len(results) <= 3


class TestSupportChatbot:
    """Tests for SupportChatbot."""

    @pytest.mark.asyncio
    async def test_answer_with_high_similarity(self):
        kb = KnowledgeBase()
        kb.add_entry("1", "Как начать работу с ботом?", "Отправьте /start.")
        chatbot = SupportChatbot(kb=kb)

        with patch("ai_router.call_llm_text", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Для начала отправьте команду /start."
            result = await chatbot.answer(AsyncMock(), "Как начать работу с ботом?")

        assert "answer" in result
        assert "confidence" in result
        assert "escalate" in result
        assert result["escalate"] is False
        assert result["answer"] == "Для начала отправьте команду /start."

    @pytest.mark.asyncio
    async def test_escalation_on_low_similarity(self):
        kb = KnowledgeBase()
        kb.add_entry("1", "Как подключить биржу?", "Введите API ключ.")
        chatbot = SupportChatbot(kb=kb)

        # Query completely unrelated to KB
        result = await chatbot.answer(AsyncMock(), "xyzzy foobar baz qux plugh")

        assert result["escalate"] is True
        assert result["confidence"] < 0.3

    @pytest.mark.asyncio
    async def test_answer_with_llm_failure_fallback(self):
        kb = KnowledgeBase()
        kb.add_entry("1", "Как начать работу?", "Отправьте /start.")
        chatbot = SupportChatbot(kb=kb)

        with patch("ai_router.call_llm_text", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ""
            result = await chatbot.answer(AsyncMock(), "Как начать работу?")

        # Should fallback to KB answer
        assert "answer" in result
        assert result["escalate"] is False

    @pytest.mark.asyncio
    async def test_answer_empty_kb_escalates(self):
        kb = KnowledgeBase()
        chatbot = SupportChatbot(kb=kb)

        result = await chatbot.answer(AsyncMock(), "Any question")
        assert result["escalate"] is True
