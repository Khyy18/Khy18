"""Webhook retry queue with exponential backoff and persistent Dead Letter Queue.

Retries failed webhook calls up to 5 times with backoff: 1s, 2s, 4s, 8s, 16s.
After exhausting attempts, moves to a SQLite-backed DLQ for later inspection.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import aiohttp

from logging_config import get_logger

log = get_logger(__name__)

MAX_ATTEMPTS = 5
BASE_DELAY_SEC = 1.0  # 1, 2, 4, 8, 16

DLQ_DB_PATH = os.getenv("WEBHOOK_DLQ_DB_PATH", "webhook_dlq.db")


def _init_dlq_db(db_path: str = "") -> None:
    """Create DLQ table if not exists."""
    path = db_path or DLQ_DB_PATH
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dead_letter_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payload_json TEXT NOT NULL,
            callback_url TEXT NOT NULL,
            last_error TEXT NOT NULL DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            added_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _save_to_dlq(item: "WebhookPayload", db_path: str = "") -> None:
    """Persist a failed webhook item to the DLQ SQLite table."""
    path = db_path or DLQ_DB_PATH
    _init_dlq_db(path)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        INSERT INTO dead_letter_queue (payload_json, callback_url, last_error, attempts, created_at, added_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            json.dumps(item.payload, ensure_ascii=False, default=str),
            item.callback_url,
            item.last_error,
            item.attempt,
            item.created_at,
            time.time(),
        ),
    )
    conn.commit()
    conn.close()


def get_dlq_items(db_path: str = "", limit: int = 100) -> list[dict]:
    """Retrieve items from the DLQ for inspection."""
    path = db_path or DLQ_DB_PATH
    _init_dlq_db(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM dead_letter_queue ORDER BY added_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@dataclass
class WebhookPayload:
    """Элемент очереди на повтор."""

    payload: dict[str, Any]
    callback_url: str
    attempt: int = 0
    created_at: float = field(default_factory=time.time)
    last_error: str = ""


class WebhookRetryQueue:
    """Очередь повторных попыток для вебхук-уведомлений."""

    def __init__(self, dlq_db_path: str = "") -> None:
        self._queue: list[WebhookPayload] = []
        self._dlq_db_path = dlq_db_path or DLQ_DB_PATH

    def enqueue(self, payload: dict[str, Any], callback_url: str) -> None:
        """Добавить вебхук в очередь на отправку."""
        item = WebhookPayload(payload=payload, callback_url=callback_url)
        self._queue.append(item)
        log.info("webhook_enqueued", url=callback_url)

    def get_backoff_delay(self, attempt: int) -> float:
        """Вычислить задержку для попытки: 1, 2, 4, 8, 16 сек."""
        return BASE_DELAY_SEC * (2 ** attempt)

    async def _send_webhook(
        self,
        session: aiohttp.ClientSession,
        item: WebhookPayload,
    ) -> bool:
        """Отправить вебхук. Возвращает True при успехе (2xx)."""
        try:
            async with session.post(
                item.callback_url,
                json=item.payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if 200 <= resp.status < 300:
                    log.info(
                        "webhook_sent",
                        url=item.callback_url,
                        attempt=item.attempt + 1,
                    )
                    return True
                item.last_error = f"HTTP {resp.status}"
                log.warning(
                    "webhook_failed",
                    url=item.callback_url,
                    status=resp.status,
                    attempt=item.attempt + 1,
                )
                return False
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            item.last_error = str(e)
            log.warning(
                "webhook_error",
                url=item.callback_url,
                error=str(e),
                attempt=item.attempt + 1,
            )
            return False

    async def process_one(
        self, session: aiohttp.ClientSession, item: WebhookPayload
    ) -> bool:
        """Обработать один элемент очереди с retry logic."""
        while item.attempt < MAX_ATTEMPTS:
            if item.attempt > 0:
                delay = self.get_backoff_delay(item.attempt - 1)
                await asyncio.sleep(delay)

            success = await self._send_webhook(session, item)
            if success:
                return True
            item.attempt += 1

        # Exhausted all attempts - persist to SQLite DLQ.
        _save_to_dlq(item, self._dlq_db_path)
        log.error(
            "webhook_to_dlq",
            url=item.callback_url,
            last_error=item.last_error,
            attempts=MAX_ATTEMPTS,
        )
        return False

    async def process_all(self, session: aiohttp.ClientSession) -> dict[str, int]:
        """Обработать все элементы в очереди. Возвращает статистику."""
        results = {"success": 0, "dlq": 0}
        while self._queue:
            item = self._queue.pop(0)
            success = await self.process_one(session, item)
            if success:
                results["success"] += 1
            else:
                results["dlq"] += 1
        return results

    @property
    def pending_count(self) -> int:
        """Количество элементов в ожидании."""
        return len(self._queue)

    @property
    def dlq_count(self) -> int:
        """Количество элементов в persistent DLQ."""
        items = get_dlq_items(self._dlq_db_path)
        return len(items)
