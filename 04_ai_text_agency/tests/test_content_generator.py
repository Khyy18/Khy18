"""Тесты для модуля Content Generator."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


# --- Тесты ContentGenerator ---


@pytest.mark.asyncio
async def test_generate_case_study():
    """ContentGenerator.generate_case_study с мок-LLM."""
    from content_generator.generator import ContentGenerator

    mock_text = "Кейс: Разработка бота для интернет-магазина. Проблема: ..."

    with patch("ai_router.call_llm_text", new_callable=AsyncMock, return_value=mock_text):
        gen = ContentGenerator()
        session = AsyncMock()
        result = await gen.generate_case_study(
            session,
            {"title": "Bot project", "description": "Ecommerce bot", "result": "Done"},
        )

    assert result == mock_text
    assert "Кейс" in result


@pytest.mark.asyncio
async def test_generate_channel_post():
    """ContentGenerator.generate_channel_post с мок-LLM."""
    from content_generator.generator import ContentGenerator

    mock_text = "Пост: Telegram-боты для бизнеса. Автоматизируйте!"

    with patch("ai_router.call_llm_text", new_callable=AsyncMock, return_value=mock_text):
        gen = ContentGenerator()
        session = AsyncMock()
        result = await gen.generate_channel_post(session, "Telegram боты")

    assert result == mock_text


@pytest.mark.asyncio
async def test_generate_seo_text():
    """ContentGenerator.generate_seo_text с мок-LLM."""
    from content_generator.generator import ContentGenerator

    mock_text = "SEO-текст о Python-разработке и автоматизации процессов."

    with patch("ai_router.call_llm_text", new_callable=AsyncMock, return_value=mock_text):
        gen = ContentGenerator()
        session = AsyncMock()
        result = await gen.generate_seo_text(session, ["python", "разработка"], length=200)

    assert result == mock_text


@pytest.mark.asyncio
async def test_generate_case_study_empty_on_failure():
    """ContentGenerator возвращает пустую строку при ошибке LLM."""
    from content_generator.generator import ContentGenerator

    with patch("ai_router.call_llm_text", new_callable=AsyncMock, return_value=""):
        gen = ContentGenerator()
        session = AsyncMock()
        result = await gen.generate_case_study(
            session,
            {"title": "Test", "description": "Test", "result": "Test"},
        )

    assert result == ""


# --- Тесты SimpleRAG ---


def test_rag_add_and_search():
    """SimpleRAG: добавление документов и поиск."""
    from content_generator.rag import SimpleRAG

    rag = SimpleRAG()
    rag.add_document("doc1", "Python разработка Telegram ботов для бизнеса")
    rag.add_document("doc2", "SEO оптимизация сайтов и контент маркетинг")
    rag.add_document("doc3", "Разработка API и backend на Python Django")

    results = rag.search("Python бот Telegram", top_k=2)
    assert len(results) > 0
    # First result should be most relevant to Python + Telegram + бот
    assert "Telegram" in results[0] or "Python" in results[0]


def test_rag_cosine_similarity():
    """Проверка косинусного сходства: идентичный запрос = высокий score."""
    from content_generator.rag import SimpleRAG

    rag = SimpleRAG()
    rag.add_document("exact", "machine learning artificial intelligence")
    rag.add_document("unrelated", "cooking recipes dinner pasta")

    results = rag.search("machine learning AI", top_k=2)
    assert len(results) >= 1
    assert "machine learning" in results[0]


def test_rag_empty_search():
    """SimpleRAG: поиск в пустом индексе."""
    from content_generator.rag import SimpleRAG

    rag = SimpleRAG()
    results = rag.search("test query")
    assert results == []


def test_rag_document_count():
    """SimpleRAG: подсчет документов."""
    from content_generator.rag import SimpleRAG

    rag = SimpleRAG()
    assert rag.document_count == 0

    rag.add_document("d1", "first document")
    rag.add_document("d2", "second document")
    assert rag.document_count == 2


def test_rag_top_k_limit():
    """SimpleRAG: top_k ограничивает количество результатов."""
    from content_generator.rag import SimpleRAG

    rag = SimpleRAG()
    for i in range(10):
        rag.add_document(f"doc{i}", f"python development project number {i}")

    results = rag.search("python development", top_k=3)
    assert len(results) <= 3
