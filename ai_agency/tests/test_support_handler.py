"""Tests for AI support handler: question detection, FAQ matching, LLM answers."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import support_handler


@pytest.mark.asyncio
class TestSupportHandler:

    async def test_detect_question_with_question_mark(self):
        """Text with '?' returns True."""
        assert support_handler.detect_question("Сколько стоит услуга?") is True
        assert support_handler.detect_question("Это вопрос?") is True
        assert support_handler.detect_question("? ") is True

    async def test_detect_question_with_trigger_words(self):
        """Text starting with trigger words returns True."""
        assert support_handler.detect_question("как платить за услуги") is True
        assert support_handler.detect_question("что за бот такой") is True
        assert support_handler.detect_question("сколько стоит копирайтинг") is True
        assert support_handler.detect_question("когда будет готово") is True
        assert support_handler.detect_question("Почему так дорого") is True

    async def test_detect_question_non_question(self):
        """Regular text without question markers returns False."""
        assert support_handler.detect_question("Привет всем") is False
        assert support_handler.detect_question("Отлично работает") is False
        assert support_handler.detect_question("Хочу заказать текст") is False
        assert support_handler.detect_question("") is False

    async def test_answer_question_from_faq(self):
        """Question matching FAQ returns answer without LLM call."""
        answer, confident = await support_handler.answer_question("как платить за услуги")

        assert confident is True
        assert "YooKassa" in answer or "оплат" in answer.lower()

    async def test_answer_question_via_llm(self, monkeypatch):
        """Question not in FAQ triggers LLM call."""
        # Ensure llm_router is mocked
        mock_llm = AsyncMock(return_value="AI-ответ на ваш вопрос")
        monkeypatch.setattr(support_handler, "llm_router", MagicMock())
        monkeypatch.setattr(support_handler.llm_router, "generate", mock_llm)

        answer, confident = await support_handler.answer_question(
            "расскажи про ваш уникальный алгоритм обработки"
        )

        assert answer == "AI-ответ на ваш вопрос"
        assert confident is True
        mock_llm.assert_called_once()

    async def test_answer_question_uncertainty_detected(self, monkeypatch):
        """LLM answer with uncertainty markers gives is_confident=False."""
        mock_llm = AsyncMock(return_value="Не уверен, но возможно это так")
        monkeypatch.setattr(support_handler, "llm_router", MagicMock())
        monkeypatch.setattr(support_handler.llm_router, "generate", mock_llm)

        answer, confident = await support_handler.answer_question(
            "расскажи про ваш новый продукт xyz123"
        )

        assert "не уверен" in answer.lower()
        assert confident is False
