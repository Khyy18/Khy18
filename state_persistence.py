"""Сохранение/загрузка state["global"] в SQLite.

Раз в STATE_PERSIST_INTERVAL_SEC (default 60с) main вызывает persist(state).
При старте main вызывает load() и мёржит с _build_state().

Graceful shutdown: при SIGTERM/SIGINT main ловит сигнал, вызывает persist(),
потом exit(0). Это гарантирует, что cooldown'ы и blacklist'ы не теряются.

Формат: одна строка в SQLite-таблице kv_state: key="global", value=JSON.
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import sys
import tempfile
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

import memory

_TABLE = "kv_state"

# Ключи, которые мёржим при восстановлении из БД.
_MERGE_KEYS = frozenset({
    "funding_alert_seen",
    "rebalance_alert_seen",
    "lending_alert_seen",
    "anomaly_alert_seen",
    "seen_announcements",
    "announcement_blacklist",
    "last_funding_scan_epoch",
    "last_arb_exec_epoch",
    "last_heartbeat_epoch",
    "last_rebalance_check_epoch",
    "last_lending_check_epoch",
    "last_announcement_check_epoch",
    "last_anomaly_check_epoch",
    "last_persist_epoch",
    "daily_anchor_iso",
    "weekly_anchor_iso",
})

# Ключи, которые НЕ мёржим (всегда берём из _build_state).
_SKIP_KEYS = frozenset({
    "bot_running",
    "kill_switch_state",
    "funding_snapshot",
})


def _db_path() -> str:
    """Путь к SQLite — тот же trades.db что использует memory.py."""
    return memory.DB_PATH


def init_db() -> None:
    """CREATE TABLE IF NOT EXISTS для kv_state."""
    try:
        with sqlite3.connect(_db_path()) as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_TABLE} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_ts TEXT NOT NULL
                )
                """
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[STATE] Ошибка init_db: {exc}")


def _json_serializer(obj: Any) -> Any:
    """Кастомный serializer для типов, не поддерживаемых json.dumps.

    set → list, deque → list, datetime → isoformat.
    """
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, deque):
        return list(obj)
    if isinstance(obj, datetime):
        return obj.isoformat(timespec="seconds")
    # Для всего остального — str fallback.
    return str(obj)


def persist(state: dict[str, Any]) -> None:
    """Сохранить state["global"] в SQLite. Идемпотентно.

    Сериализуем только JSON-safe ключи (для set → list, для deque → list).
    """
    g = state.get("global")
    if not g:
        return
    try:
        payload = json.dumps(g, ensure_ascii=False, default=_json_serializer)
    except (TypeError, ValueError) as exc:
        print(f"[STATE] Ошибка сериализации: {exc}")
        return
    now_iso = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    try:
        with sqlite3.connect(_db_path()) as conn:
            conn.execute(
                f"""
                INSERT INTO {_TABLE} (key, value, updated_ts) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_ts=excluded.updated_ts
                """,
                ("global", payload, now_iso),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[STATE] Ошибка persist: {exc}")


def load() -> Optional[dict[str, Any]]:
    """Загрузить state["global"] из SQLite или None если нет."""
    try:
        with sqlite3.connect(_db_path()) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"SELECT value FROM {_TABLE} WHERE key = ?", ("global",)
            ).fetchone()
            if not row:
                return None
            return json.loads(row["value"])
    except (sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"[STATE] Ошибка load: {exc}")
        return None


def merge_into_state(state: dict[str, Any], saved: dict[str, Any]) -> None:
    """Мёржим saved поверх state["global"], но не переписываем структурные ключи.

    Мёржим: cooldown'ы (funding_alert_seen, rebalance_alert_seen, lending_alert_seen,
    anomaly_alert_seen, seen_announcements, announcement_blacklist),
    last_*_epoch, daily_anchor_iso, weekly_anchor_iso.
    НЕ мёржим: bot_running (всегда True на старте), kill_switch_state,
    funding_snapshot (стартует пустой — пересканит через 30с).
    """
    g = state.get("global")
    if not g or not saved:
        return
    for key, value in saved.items():
        # Пропускаем ключи, которые НЕ мёржим.
        if key in _SKIP_KEYS:
            continue
        # Мёржим только из белого списка + любые last_*_epoch ключи.
        if key in _MERGE_KEYS or key.startswith("last_") and key.endswith("_epoch"):
            g[key] = value


def setup_graceful_shutdown(state: dict[str, Any]) -> None:
    """Зарегистрировать SIGTERM/SIGINT handler → persist + exit."""

    def _handler(signum: int, frame: Any) -> None:
        sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
        print(f"[STATE] Получен {sig_name}, сохраняю state и завершаюсь...")
        try:
            persist(state)
        except Exception as exc:  # noqa: BLE001
            print(f"[STATE] Ошибка при graceful persist: {exc}")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


# ─── JSON file-based atomic persistence ────────────────────────────────

def _get_state_path() -> str:
    """Path to JSON state file."""
    return os.getenv("STATE_DB_PATH", "/app/data/state.json")


def save_state(state: dict) -> None:
    """Atomic save: write to tmp file, then os.replace (atomic on POSIX)."""
    path = _get_state_path()
    dir_name = os.path.dirname(path) or "."
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f, ensure_ascii=False, default=_json_serializer)
        os.replace(tmp_path, path)  # atomic on POSIX
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_state() -> dict | None:
    """Load state from JSON file. Returns None if file missing or corrupt."""
    path = _get_state_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[STATE] Error loading state from {path}: {exc}")
        return None
