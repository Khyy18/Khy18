"""SQLite-хранилище реферальной системы.

Таблицы:
  - referral_codes: код реферера (один код на пользователя).
  - referrals: связь реферер -> приглашённый, статус.
  - referral_bonuses: бонусы, начисленные рефереру за оплату приглашённых.

Путь к БД настраивается через REFERRAL_DB_PATH (по умолчанию referrals.db).
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional


DB_PATH: str = os.getenv("REFERRAL_DB_PATH", "referrals.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    """Создать таблицы реферальной системы. Идемпотентно."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS referral_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_tg_id INTEGER UNIQUE NOT NULL,
                referral_code TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_tg_id INTEGER NOT NULL,
                referred_tg_id INTEGER UNIQUE NOT NULL,
                referral_code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS referral_bonuses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_tg_id INTEGER NOT NULL,
                bonus_type TEXT NOT NULL,
                granted_at TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()


def create_referral_code(tg_id: int) -> str:
    """Сгенерировать уникальный реферальный код для пользователя.

    Если у пользователя уже есть код, возвращается существующий.
    """
    existing = get_referral_code(tg_id)
    if existing:
        return existing
    code = uuid.uuid4().hex[:8]
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO referral_codes (referrer_tg_id, referral_code, created_at)
            VALUES (?, ?, ?)
            """,
            (int(tg_id), code, _now_iso()),
        )
        conn.commit()
    return code


def get_referral_code(tg_id: int) -> Optional[str]:
    """Получить существующий реферальный код пользователя (или None)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT referral_code FROM referral_codes WHERE referrer_tg_id = ?",
            (int(tg_id),),
        ).fetchone()
        return row["referral_code"] if row else None


def register_referral(code: str, new_user_tg_id: int) -> bool:
    """Привязать нового пользователя к рефереру по коду.

    Возвращает True при успешной регистрации, False если код не найден
    или пользователь уже был приглашён.
    """
    with _connect() as conn:
        # Проверяем, не был ли этот пользователь уже приглашён
        already = conn.execute(
            "SELECT id FROM referrals WHERE referred_tg_id = ?",
            (int(new_user_tg_id),),
        ).fetchone()
        if already:
            return False

        # Находим владельца кода
        code_row = conn.execute(
            "SELECT referrer_tg_id FROM referral_codes WHERE referral_code = ?",
            (str(code),),
        ).fetchone()
        if not code_row:
            return False

        referrer_tg_id = code_row["referrer_tg_id"]

        # Нельзя пригласить самого себя
        if referrer_tg_id == int(new_user_tg_id):
            return False

        # Создаём запись реферала
        conn.execute(
            """
            INSERT INTO referrals (referrer_tg_id, referred_tg_id, referral_code, created_at, status)
            VALUES (?, ?, ?, ?, 'registered')
            """,
            (referrer_tg_id, int(new_user_tg_id), str(code), _now_iso()),
        )
        conn.commit()
    return True


def grant_bonus_on_payment(referred_tg_id: int) -> Optional[dict]:
    """Начислить бонус рефереру при первой оплате приглашённого.

    Возвращает информацию о бонусе или None если реферер не найден
    или бонус уже был начислен.
    """
    with _connect() as conn:
        # Находим запись реферала со статусом 'registered'
        ref_row = conn.execute(
            """
            SELECT id, referrer_tg_id FROM referrals
            WHERE referred_tg_id = ? AND status = 'registered'
            LIMIT 1
            """,
            (int(referred_tg_id),),
        ).fetchone()
        if not ref_row:
            return None

        referrer_tg_id = ref_row["referrer_tg_id"]

        # Начисляем бонус
        granted_at = _now_iso()
        conn.execute(
            """
            INSERT INTO referral_bonuses (referrer_tg_id, bonus_type, granted_at, used)
            VALUES (?, 'free_order', ?, 0)
            """,
            (referrer_tg_id, granted_at),
        )

        # Обновляем статус реферала
        conn.execute(
            "UPDATE referrals SET status = 'paid' WHERE id = ?",
            (ref_row["id"],),
        )
        conn.commit()

    return {
        "referrer_tg_id": referrer_tg_id,
        "bonus_type": "free_order",
        "granted_at": granted_at,
    }


def get_referral_stats(tg_id: int) -> dict:
    """Статистика рефералов пользователя: приглашённые, бонусы, ожидающие."""
    with _connect() as conn:
        # Количество приглашённых
        invited_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM referrals WHERE referrer_tg_id = ?",
            (int(tg_id),),
        ).fetchone()
        invited = invited_row["cnt"] if invited_row else 0

        # Количество оплативших (статус 'paid')
        paid_row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM referrals
            WHERE referrer_tg_id = ? AND status = 'paid'
            """,
            (int(tg_id),),
        ).fetchone()
        paid = paid_row["cnt"] if paid_row else 0

        # Ожидающие оплаты
        pending_row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM referrals
            WHERE referrer_tg_id = ? AND status = 'registered'
            """,
            (int(tg_id),),
        ).fetchone()
        pending = pending_row["cnt"] if pending_row else 0

        # Бонусы заработанные
        bonuses_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM referral_bonuses WHERE referrer_tg_id = ?",
            (int(tg_id),),
        ).fetchone()
        bonuses = bonuses_row["cnt"] if bonuses_row else 0

    return {
        "invited": invited,
        "paid": paid,
        "pending": pending,
        "bonuses_earned": bonuses,
    }
