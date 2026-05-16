"""SimpleRAG: in-memory TF-IDF-based retrieval.

Хранит документы как bag-of-words векторы и использует косинусное сходство
для поиска релевантных документов. Без внешних зависимостей - чистый Python.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Optional


def _tokenize(text: str) -> list[str]:
    """Простая токенизация: нижний регистр, разбиение по не-буквенным символам."""
    return re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", text.lower())


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Косинусное сходство двух sparse-векторов (dict term -> weight)."""
    if not vec_a or not vec_b:
        return 0.0

    # Скалярное произведение
    dot = 0.0
    for term, weight_a in vec_a.items():
        if term in vec_b:
            dot += weight_a * vec_b[term]

    if dot == 0.0:
        return 0.0

    # Нормы
    norm_a = math.sqrt(sum(w * w for w in vec_a.values()))
    norm_b = math.sqrt(sum(w * w for w in vec_b.values()))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


class SimpleRAG:
    """In-memory RAG с TF-IDF векторами и косинусным поиском."""

    def __init__(self) -> None:
        self._documents: dict[str, str] = {}  # doc_id -> original text
        self._vectors: dict[str, dict[str, float]] = {}  # doc_id -> tf-idf vector
        self._df: Counter = Counter()  # document frequency per term
        self._doc_count: int = 0

    def add_document(self, doc_id: str, text: str) -> None:
        """Добавить документ в индекс.

        Args:
            doc_id: уникальный идентификатор документа.
            text: текст документа.
        """
        tokens = _tokenize(text)
        if not tokens:
            return

        self._documents[doc_id] = text
        self._doc_count += 1

        # Обновить document frequency
        unique_terms = set(tokens)
        for term in unique_terms:
            self._df[term] += 1

        # Вычислить TF вектор (будем пересчитывать IDF при поиске)
        tf = Counter(tokens)
        total = len(tokens)
        self._vectors[doc_id] = {term: count / total for term, count in tf.items()}

        # Пересчитать все TF-IDF векторы (IDF обновился)
        self._recompute_tfidf()

    def _recompute_tfidf(self) -> None:
        """Пересчитать TF-IDF веса для всех документов."""
        if self._doc_count == 0:
            return

        for doc_id in list(self._vectors.keys()):
            text = self._documents[doc_id]
            tokens = _tokenize(text)
            tf = Counter(tokens)
            total = len(tokens)

            tfidf: dict[str, float] = {}
            for term, count in tf.items():
                tf_val = count / total
                idf_val = math.log(1 + self._doc_count / (1 + self._df.get(term, 0)))
                tfidf[term] = tf_val * idf_val

            self._vectors[doc_id] = tfidf

    def search(self, query: str, top_k: int = 3) -> list[str]:
        """Поиск релевантных документов по запросу.

        Args:
            query: поисковый запрос.
            top_k: количество результатов.

        Returns:
            Список текстов наиболее релевантных документов.
        """
        if not self._documents:
            return []

        tokens = _tokenize(query)
        if not tokens:
            return []

        # Построить TF-IDF вектор для запроса
        tf = Counter(tokens)
        total = len(tokens)
        query_vec: dict[str, float] = {}
        for term, count in tf.items():
            tf_val = count / total
            idf_val = math.log(1 + self._doc_count / (1 + self._df.get(term, 0)))
            query_vec[term] = tf_val * idf_val

        # Вычислить сходство с каждым документом
        scores: list[tuple[str, float]] = []
        for doc_id, doc_vec in self._vectors.items():
            sim = _cosine_similarity(query_vec, doc_vec)
            if sim > 0:
                scores.append((doc_id, sim))

        # Сортировка по убыванию сходства
        scores.sort(key=lambda x: x[1], reverse=True)

        # Вернуть тексты top_k документов
        results: list[str] = []
        for doc_id, _ in scores[:top_k]:
            results.append(self._documents[doc_id])

        return results

    @property
    def document_count(self) -> int:
        """Количество документов в индексе."""
        return self._doc_count
