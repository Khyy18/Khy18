"""Парсер биржевых announcement'ов для детекции delisting/maintenance.

Использует regex-классификацию вместо LLM, чтобы:
1. не таскать модель на VPS;
2. поведение оставалось предсказуемым (rule-based);
3. при ошибках в API биржи graceful fallback к [].

Если категория CRITICAL (delisting) — символ добавляется в
state['announcement_blacklist']. evaluate_and_open проверяет blacklist
и пропускает кандидата, у которого хотя бы одна нога находится в
blacklist'е соответствующей биржи.
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any, Awaitable, Callable, Optional

import config


# Регулярка для извлечения символов вида BTCUSDT, ETH-USDT, 1000PEPE/USDT и т.п.
# Берёт base длиной 2-10 (включая префиксы вроде "1000") и quote USDT/USD.
_SYMBOL_RE = re.compile(r"\b([A-Z0-9]{2,10}?)[/-]?(USDT?)\b")


# Регулярки для классификации анонса. Порядок важен — берём первую совпавшую.
_PATTERNS: dict[str, list[str]] = {
    "delisting": [
        r"\b(delist|delisting|removal|remove|removed|discontinue|terminat)\w*\b",
    ],
    "maintenance": [
        r"\b(maintenance|system upgrade|planned downtime|scheduled outage)\b",
    ],
    "leverage_reduction": [
        r"\b(reduce leverage|leverage tier|max leverage|tier change)\b",
    ],
    "fee_change": [
        r"\b(fee adjustment|fee schedule|new fee)\b",
    ],
}


# Severity-уровни для категорий: critical триггерит blacklist.
_SEVERITY: dict[str, str] = {
    "delisting": "critical",
    "maintenance": "warning",
    "leverage_reduction": "warning",
    "fee_change": "info",
    "other": "info",
}


def classify_announcement(title: str, body: str = "") -> dict[str, Any]:
    """Классифицировать анонс и извлечь упомянутые символы.

    Возвращает словарь с ключами:
      - severity: 'critical' | 'warning' | 'info'
      - category: 'delisting' | 'maintenance' | 'leverage_reduction' |
                  'fee_change' | 'other'
      - symbols: список нормализованных символов вида ['BTCUSDT', ...].
    """
    text = (title + " " + body).lower()
    category = "other"
    for cat, patterns in _PATTERNS.items():
        if any(re.search(p, text) for p in patterns):
            category = cat
            break

    # Извлекаем символы из ОРИГИНАЛЬНОГО (не lowered) текста — они в верхнем регистре.
    raw = title + " " + body
    matches = _SYMBOL_RE.findall(raw)
    symbols: list[str] = []
    for base, quote in matches:
        # Нормализация: BTC-USDT → BTCUSDT, BTC/USDT → BTCUSDT.
        if len(base) >= 2 and quote.upper() in ("USDT", "USD"):
            sym = base.upper() + "USDT"
            if sym not in symbols:
                symbols.append(sym)

    return {
        "severity": _SEVERITY.get(category, "info"),
        "category": category,
        "symbols": symbols,
    }


# Конфиги fetcher'ов для бирж. Все эндпоинты публичные, без auth.
# Если биржа поменяет схему ответа — extract вернёт [], и тик уйдёт молча.
_FETCHERS: dict[str, dict[str, Any]] = {
    "bybit": {
        "url": "https://api.bybit.com/v5/announcements/index?locale=en-US&limit=20",
        "extract": lambda d: ((d.get("result") or {}).get("list") or []),
        "title_key": "title",
        "url_key": "url",
        "ts_key": "publishTime",
    },
    "binance": {
        "url": (
            "https://www.binance.com/bapi/composite/v1/public/cms/article/"
            "all/query?type=1&pageSize=20"
        ),
        "extract": (
            lambda d: (
                ((((d.get("data") or {}).get("articles") or [{}])[0]).get("articles") or [])
                if isinstance(d, dict) else []
            )
        ),
        "title_key": "title",
        "url_key": "code",
        "ts_key": "releaseDate",
    },
    "okx": {
        "url": (
            "https://www.okx.com/api/v5/support/announcements"
            "?annType=announcements-new-listings"
        ),
        "extract": (
            lambda d: ((d.get("data") or [{}])[0].get("details") or [])
            if isinstance(d, dict) else []
        ),
        "title_key": "title",
        "url_key": "url",
        "ts_key": "pTime",
    },
}


async def fetch_announcements(session: Any, exchange: str) -> list[dict[str, Any]]:
    """Дёрнуть announcement-feed одной биржи. Возвращает [] при любой ошибке.

    Возвращает список нормализованных dict'ов: {title, url, ts, raw}.
    """
    cfg = _FETCHERS.get(exchange.lower())
    if not cfg:
        return []
    try:
        async with session.get(cfg["url"], timeout=15) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
    except Exception as exc:  # noqa: BLE001
        print(f"[ANNOUNCE] {exchange}: fetch fail: {exc}")
        return []

    try:
        items = cfg["extract"](data)
    except Exception as exc:  # noqa: BLE001
        print(f"[ANNOUNCE] {exchange}: extract fail: {exc}")
        return []

    out: list[dict[str, Any]] = []
    for it in (items or [])[:20]:
        try:
            title = str(it.get(cfg["title_key"], ""))
            url = str(it.get(cfg["url_key"], ""))
            ts = int(it.get(cfg["ts_key"], 0) or 0)
            out.append({"title": title, "url": url, "ts": ts, "raw": it})
        except (TypeError, ValueError, AttributeError):
            continue
    return out


def _hash_announcement(item: dict[str, Any]) -> str:
    """Стабильный хэш анонса для дедупликации между тиками."""
    key = (item.get("title") or "") + "|" + (item.get("url") or "")
    return hashlib.sha256(key.encode("utf-8", errors="ignore")).hexdigest()[:16]


async def check_and_alert(
    session: Any,
    adapters: dict[str, Any],
    notify: Optional[Callable[[str], Awaitable[None]]],
    state: dict[str, Any],
) -> Optional[list[dict[str, Any]]]:
    """Один проход монитора: пробежать по биржам, классифицировать новые анонсы.

    Алерты отправляются для new critical/warning; blacklist обновляется
    для critical (delisting). Возвращает список новых alert-словарей
    или None, если ничего не нашли.

    Сохраняем в ``state``:
      - ``seen_announcements`` — список хешей уже виденных анонсов
        (последние 500, чтобы не разрастался);
      - ``announcement_blacklist`` — словарь
        ``{f"{exchange}:{symbol}": expires_ms}``.
    """
    seen: set[str] = set(state.get("seen_announcements") or [])
    blacklist: dict[str, int] = dict(state.get("announcement_blacklist") or {})

    new_alerts: list[dict[str, Any]] = []
    blacklist_hours = float(getattr(config, "ANNOUNCE_BLACKLIST_HOURS", 72) or 72)
    expires_ms = int(time.time() * 1000) + int(blacklist_hours * 3600 * 1000)

    for ex in adapters.keys():
        items = await fetch_announcements(session, ex)
        for it in items:
            h = _hash_announcement(it)
            if h in seen:
                continue
            seen.add(h)
            cls = classify_announcement(it.get("title", ""), "")
            if cls["category"] == "other":
                continue
            alert = {
                "exchange": ex,
                "title": str(it.get("title", ""))[:200],
                "category": cls["category"],
                "severity": cls["severity"],
                "symbols": cls["symbols"],
            }
            new_alerts.append(alert)

            # Blacklist для critical (delisting).
            if cls["severity"] == "critical":
                for sym in cls["symbols"]:
                    blacklist[f"{ex}:{sym}"] = expires_ms

    # Ограничим память на seen — храним только последние 500 хешей.
    state["seen_announcements"] = list(seen)[-500:]
    state["announcement_blacklist"] = blacklist

    if not new_alerts:
        return None

    # Один сводный алерт.
    lines = ["📢 <b>Биржевые анонсы</b>", ""]
    for a in new_alerts[:10]:
        emoji = "🚨" if a["severity"] == "critical" else "⚠️"
        syms = (", ".join(a["symbols"])) if a["symbols"] else "-"
        lines.append(
            f"{emoji} {a['exchange']}: {a['category']} ({syms})\n"
            f"   {a['title']}"
        )
    if any(a["severity"] == "critical" for a in new_alerts):
        lines.append("")
        lines.append(f"Символы добавлены в blacklist на {int(blacklist_hours)}ч.")

    if notify is not None:
        try:
            await notify("\n".join(lines))
        except Exception as exc:  # noqa: BLE001
            print(f"[ANNOUNCE] notify fail: {exc}")

    return new_alerts


def is_blacklisted(exchange: str, symbol: str, state: dict[str, Any]) -> bool:
    """Проверка blacklist'а для evaluate_and_open.

    Возвращает True, если по ключу ``f"{exchange}:{symbol}"`` есть запись
    с expires_ms в будущем. Регистр биржи нормализуется к нижнему,
    регистр символа сохраняется как пришёл (символы у нас всегда
    в верхнем регистре).
    """
    if not isinstance(state, dict):
        return False
    bl = state.get("announcement_blacklist") or {}
    key = f"{exchange.lower()}:{symbol}"
    try:
        expires = int(bl.get(key, 0))
    except (TypeError, ValueError):
        return False
    if expires <= 0:
        return False
    return int(time.time() * 1000) < expires
