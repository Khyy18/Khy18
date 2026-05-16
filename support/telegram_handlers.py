"""Telegram handlers for support chatbot."""

from __future__ import annotations

import json
from typing import Any, Optional

import aiohttp

import config
from logging_config import get_logger
from support.chatbot import SupportChatbot

log = get_logger(__name__)

_chatbot: Optional[SupportChatbot] = None


def _get_chatbot() -> SupportChatbot:
    """Lazy-init singleton chatbot."""
    global _chatbot
    if _chatbot is None:
        _chatbot = SupportChatbot()
    return _chatbot


def _bot_url(method: str) -> str:
    return f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_TOKEN}/{method}"


async def _send_message(
    session: aiohttp.ClientSession,
    chat_id: int,
    text: str,
    reply_markup: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Send a message via Telegram Bot API."""
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    try:
        async with session.post(_bot_url("sendMessage"), data=payload, timeout=15) as resp:
            if resp.status != 200:
                log.warning("telegram_send_failed", status=resp.status, chat_id=chat_id)
                return None
            return await resp.json()
    except (aiohttp.ClientError, Exception) as e:
        log.error("telegram_send_error", error=str(e), chat_id=chat_id)
        return None


async def handle_support_command(
    session: aiohttp.ClientSession,
    chat_id: int,
    question: str,
) -> None:
    """Handle /support command - answer user question via chatbot."""
    if not question.strip():
        await _send_message(
            session, chat_id, "Напишите ваш вопрос после команды /support."
        )
        return

    chatbot = _get_chatbot()
    result = await chatbot.answer(session, question)

    if result["escalate"]:
        text = (
            f"<b>Поддержка:</b>\n"
            f"{result['answer']}\n\n"
            f"Оператор скоро свяжется с вами."
        )
        await _send_message(session, chat_id, text)
        # Notify admin
        if config.TELEGRAM_CHAT_ID:
            admin_text = (
                f"<b>Запрос в поддержку (эскалация):</b>\n"
                f"От: {chat_id}\n"
                f"Вопрос: {question}"
            )
            await _send_message(session, config.TELEGRAM_CHAT_ID, admin_text)
    else:
        confidence_pct = int(result["confidence"] * 100)
        text = (
            f"<b>Поддержка:</b>\n"
            f"{result['answer']}\n\n"
            f"<i>Уверенность: {confidence_pct}%</i>"
        )
        await _send_message(session, chat_id, text)


async def handle_inline_query(
    session: aiohttp.ClientSession,
    inline_query: dict[str, Any],
) -> None:
    """Handle inline query for quick FAQ answers."""
    query_text = inline_query.get("query", "").strip()
    query_id = inline_query.get("id", "")

    if not query_text:
        return

    chatbot = _get_chatbot()
    results = chatbot._kb.search(query_text, top_k=3)

    articles = []
    for i, r in enumerate(results):
        articles.append({
            "type": "article",
            "id": str(i),
            "title": r["question"],
            "input_message_content": {
                "message_text": f"<b>{r['question']}</b>\n\n{r['answer']}",
                "parse_mode": "HTML",
            },
            "description": r["answer"][:100],
        })

    payload = {
        "inline_query_id": query_id,
        "results": json.dumps(articles, ensure_ascii=False),
        "cache_time": 60,
    }

    try:
        async with session.post(
            _bot_url("answerInlineQuery"), data=payload, timeout=15
        ) as resp:
            if resp.status != 200:
                log.warning("inline_query_failed", status=resp.status)
    except (aiohttp.ClientError, Exception) as e:
        log.error("inline_query_error", error=str(e))
