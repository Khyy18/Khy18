"""Knowledge Base: in-memory FAQ/article storage with TF-IDF vectors and cosine similarity."""

from __future__ import annotations

import math
import re
from collections import Counter

DEFAULT_FAQ: list[dict[str, str]] = [
    {
        "id": "faq_1",
        "question": "Как начать работу с ботом?",
        "answer": "Отправьте команду /start и следуйте инструкциям. Бот проведёт вас через настройку.",
    },
    {
        "id": "faq_2",
        "question": "Как подключить биржу?",
        "answer": "Перейдите в настройки, выберите биржу и введите API-ключ и секрет. Убедитесь что ключ имеет права на торговлю.",
    },
    {
        "id": "faq_3",
        "question": "Какие биржи поддерживаются?",
        "answer": "Поддерживаются Bybit и OKX. Работа ведётся через официальные API.",
    },
    {
        "id": "faq_4",
        "question": "Как изменить риск на сделку?",
        "answer": "Используйте команду /settings и укажите новый процент риска. По умолчанию 1% на сделку.",
    },
    {
        "id": "faq_5",
        "question": "Что делать если бот не отвечает?",
        "answer": "Проверьте статус бота командой /status. Если проблема сохраняется, перезапустите бота или обратитесь в поддержку.",
    },
    {
        "id": "faq_6",
        "question": "Как отключить торговлю?",
        "answer": "Отправьте команду /stop или включите DRY_RUN режим в настройках.",
    },
    {
        "id": "faq_7",
        "question": "Сколько стоит подписка?",
        "answer": "Актуальные тарифы доступны по команде /pricing. Есть бесплатный пробный период.",
    },
    {
        "id": "faq_8",
        "question": "Как получить реферальную ссылку?",
        "answer": "Используйте команду /referral. Пригласите друга и получите бонус при его первой оплате.",
    },
]


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase words."""
    return re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", text.lower())


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Cosine similarity between two sparse vectors."""
    if not vec_a or not vec_b:
        return 0.0

    dot = 0.0
    for term, weight_a in vec_a.items():
        if term in vec_b:
            dot += weight_a * vec_b[term]

    if dot == 0.0:
        return 0.0

    norm_a = math.sqrt(sum(w * w for w in vec_a.values()))
    norm_b = math.sqrt(sum(w * w for w in vec_b.values()))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


class KnowledgeBase:
    """In-memory knowledge base with TF-IDF vectors and cosine search."""

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, str]] = {}  # entry_id -> {question, answer}
        self._vectors: dict[str, dict[str, float]] = {}  # entry_id -> tfidf vector
        self._df: Counter = Counter()
        self._doc_count: int = 0

    def add_entry(self, entry_id: str, question: str, answer: str) -> None:
        """Add a FAQ entry to the knowledge base."""
        text = f"{question} {answer}"
        tokens = _tokenize(text)
        if not tokens:
            return

        self._entries[entry_id] = {"question": question, "answer": answer}
        self._doc_count += 1

        unique_terms = set(tokens)
        for term in unique_terms:
            self._df[term] += 1

        self._recompute_tfidf()

    def _recompute_tfidf(self) -> None:
        """Recompute TF-IDF vectors for all entries."""
        if self._doc_count == 0:
            return

        for entry_id, entry in self._entries.items():
            text = f"{entry['question']} {entry['answer']}"
            tokens = _tokenize(text)
            tf = Counter(tokens)
            total = len(tokens)

            tfidf: dict[str, float] = {}
            for term, count in tf.items():
                tf_val = count / total
                idf_val = math.log(1 + self._doc_count / (1 + self._df.get(term, 0)))
                tfidf[term] = tf_val * idf_val

            self._vectors[entry_id] = tfidf

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """Search for relevant entries.

        Returns:
            List of dicts with {question, answer, similarity}.
        """
        if not self._entries:
            return []

        tokens = _tokenize(query)
        if not tokens:
            return []

        tf = Counter(tokens)
        total = len(tokens)
        query_vec: dict[str, float] = {}
        for term, count in tf.items():
            tf_val = count / total
            idf_val = math.log(1 + self._doc_count / (1 + self._df.get(term, 0)))
            query_vec[term] = tf_val * idf_val

        scores: list[tuple[str, float]] = []
        for entry_id, doc_vec in self._vectors.items():
            sim = _cosine_similarity(query_vec, doc_vec)
            if sim > 0:
                scores.append((entry_id, sim))

        scores.sort(key=lambda x: x[1], reverse=True)

        results: list[dict] = []
        for entry_id, sim in scores[:top_k]:
            entry = self._entries[entry_id]
            results.append({
                "question": entry["question"],
                "answer": entry["answer"],
                "similarity": sim,
            })

        return results

    @property
    def entry_count(self) -> int:
        """Number of entries in knowledge base."""
        return self._doc_count

    def preload_defaults(self) -> None:
        """Load default FAQ entries."""
        for item in DEFAULT_FAQ:
            self.add_entry(item["id"], item["question"], item["answer"])
