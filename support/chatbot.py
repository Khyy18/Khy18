"""AI Support Chatbot with RAG-based knowledge retrieval."""

from __future__ import annotations

import aiohttp

import ai_router
from logging_config import get_logger
from support.knowledge_base import KnowledgeBase

log = get_logger(__name__)


class SupportChatbot:
    """Chatbot that answers user questions using KB context + LLM."""

    def __init__(self, kb: KnowledgeBase | None = None) -> None:
        if kb is None:
            self._kb = KnowledgeBase()
            self._kb.preload_defaults()
        else:
            self._kb = kb

    async def answer(self, session: aiohttp.ClientSession, user_question: str) -> dict:
        """Answer a user question.

        Returns:
            dict with {answer: str, confidence: float, escalate: bool}
        """
        results = self._kb.search(user_question, top_k=3)

        if not results:
            return {
                "answer": "Соединяю вас с оператором поддержки.",
                "confidence": 0.0,
                "escalate": True,
            }

        top_similarity = results[0]["similarity"]

        if top_similarity < 0.3:
            log.info("support_escalate", question=user_question, similarity=top_similarity)
            return {
                "answer": "Соединяю вас с оператором поддержки.",
                "confidence": top_similarity,
                "escalate": True,
            }

        context_parts = []
        for r in results:
            context_parts.append(f"Q: {r['question']}\nA: {r['answer']}")
        context = "\n\n".join(context_parts)

        prompt = (
            f"Ты - помощник службы поддержки. Ответь на вопрос пользователя, "
            f"используя контекст из базы знаний.\n\n"
            f"Контекст:\n{context}\n\n"
            f"Вопрос пользователя: {user_question}\n\n"
            f"Дай краткий и полезный ответ на русском языке."
        )

        llm_answer = await ai_router.call_llm_text(
            session, prompt, max_output_tokens=256, temperature=0.3
        )

        if not llm_answer:
            # Fallback to KB answer directly
            llm_answer = results[0]["answer"]

        if top_similarity >= 0.7:
            confidence = top_similarity
        else:
            # Middle ground: LLM answers but with lower confidence
            confidence = top_similarity

        log.info(
            "support_answer",
            question=user_question,
            confidence=confidence,
            similarity=top_similarity,
        )

        return {
            "answer": llm_answer,
            "confidence": confidence,
            "escalate": False,
        }
