"""key_manager.py — runtime API-key override manager.

Ключи хранятся в `keys_override.json` (рядом с этим файлом, не коммитится в git).
При загрузке они записываются в os.environ — остальной код читает их через
os.getenv как обычно. Replit-секреты остаются fallback: если override-файла нет,
ничего не меняется.

Управляемые переменные (можно менять через Telegram):
  OKX_API_KEY, OKX_API_SECRET, OKX_PASSPHRASE
  BYBIT_API_KEY, BYBIT_API_SECRET
  GROQ_API_KEY, NEWS_API_KEY

НЕ управляются здесь (граница безопасности):
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID — менять их значит рубить ветку,
  по которой приходят команды; задаются только через Replit secrets.

Смена ключей вступает в силу немедленно (os.environ) и сохраняется
между перезапусками (keys_override.json).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_OVERRIDE_FILE = Path(__file__).parent / "keys_override.json"

MANAGEABLE_KEYS: tuple[str, ...] = (
    "OKX_API_KEY",
    "OKX_API_SECRET",
    "OKX_PASSPHRASE",
    "BYBIT_API_KEY",
    "BYBIT_API_SECRET",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "GATE_API_KEY",
    "GATE_API_SECRET",
    "BITGET_API_KEY",
    "BITGET_API_SECRET",
    "BITGET_PASSPHRASE",
    "MEXC_API_KEY",
    "MEXC_API_SECRET",
    "HTX_API_KEY",
    "HTX_API_SECRET",
    "BINGX_API_KEY",
    "BINGX_API_SECRET",
    "GROQ_API_KEY",
    "NEWS_API_KEY",
)

_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("OKX",            ("OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE")),
    ("Bybit",          ("BYBIT_API_KEY", "BYBIT_API_SECRET")),
    ("Binance",        ("BINANCE_API_KEY", "BINANCE_API_SECRET")),
    ("Gate.io",        ("GATE_API_KEY", "GATE_API_SECRET")),
    ("Bitget",         ("BITGET_API_KEY", "BITGET_API_SECRET", "BITGET_PASSPHRASE")),
    ("MEXC",           ("MEXC_API_KEY", "MEXC_API_SECRET")),
    ("HTX",            ("HTX_API_KEY", "HTX_API_SECRET")),
    ("BingX",          ("BINGX_API_KEY", "BINGX_API_SECRET")),
    ("Groq / NewsAPI", ("GROQ_API_KEY", "NEWS_API_KEY")),
)


def load_overrides() -> dict[str, str]:
    """Загрузить оверрайды из файла и применить к os.environ.

    Вызывается один раз при старте main() — до validate_config().
    Возвращает dict загруженных пар {KEY: value}.
    """
    if not _OVERRIDE_FILE.exists():
        return {}
    try:
        data: dict[str, str] = json.loads(_OVERRIDE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[key_manager] Ошибка чтения {_OVERRIDE_FILE.name}: {exc}")
        return {}
    applied: dict[str, str] = {}
    for k, v in data.items():
        if k in MANAGEABLE_KEYS and isinstance(v, str) and v:
            os.environ[k] = v
            applied[k] = v
    if applied:
        print(f"[key_manager] Загружено {len(applied)} оверрайд(ов): {', '.join(applied)}")
    return applied


def set_key(name: str, value: str) -> None:
    """Сохранить оверрайд ключа и применить к текущему процессу.

    Raises ValueError для неизвестных имён или пустых значений.
    """
    if name not in MANAGEABLE_KEYS:
        raise ValueError(
            f"Ключ «{name}» не в списке управляемых.\n"
            f"Доступны: {', '.join(MANAGEABLE_KEYS)}"
        )
    value = value.strip()
    if not value:
        raise ValueError("Значение не может быть пустым.")

    try:
        existing: dict[str, str] = (
            json.loads(_OVERRIDE_FILE.read_text(encoding="utf-8"))
            if _OVERRIDE_FILE.exists()
            else {}
        )
    except Exception:  # noqa: BLE001
        existing = {}

    existing[name] = value
    _OVERRIDE_FILE.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.environ[name] = value


def delete_key(name: str) -> bool:
    """Удалить оверрайд (Replit-секрет снова станет активным).

    Возвращает True если ключ был найден и удалён.
    """
    if not _OVERRIDE_FILE.exists():
        return False
    try:
        existing: dict[str, str] = json.loads(
            _OVERRIDE_FILE.read_text(encoding="utf-8")
        )
        if name not in existing:
            return False
        del existing[name]
        _OVERRIDE_FILE.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.environ.pop(name, None)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[key_manager] Ошибка удаления ключа {name}: {exc}")
        return False


def _mask(val: str) -> str:
    """Показать последние 4 символа, остальное заменить точками."""
    if not val:
        return "❌ не задан"
    if len(val) <= 6:
        return "•" * len(val)
    return "•" * (len(val) - 4) + val[-4:]


def get_status_report() -> str:
    """Форматировать маскированный статус всех управляемых ключей."""
    overrides: set[str] = set()
    if _OVERRIDE_FILE.exists():
        try:
            overrides = set(
                json.loads(_OVERRIDE_FILE.read_text(encoding="utf-8")).keys()
            )
        except Exception:  # noqa: BLE001
            pass

    lines = ["🔑 <b>API-ключи (статус)</b>", ""]
    for group_name, keys in _GROUPS:
        lines.append(f"<b>{group_name}:</b>")
        for k in keys:
            val = os.getenv(k, "")
            src = " <i>(override)</i>" if k in overrides else " <i>(Replit secret)</i>"
            lines.append(f"  <code>{k}</code>: {_mask(val)}{src}")
        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        "<b>Сменить ключ:</b>",
        "<code>/setkey ИМЯ значение</code>",
        "",
        "Пример:",
        "<code>/setkey OKX_API_KEY abc123xyz</code>",
        "",
        "<b>Сбросить к Replit-секрету:</b>",
        "<code>/delkey ИМЯ</code>",
        "",
        "⚠️ <b>Сразу удалите сообщение с ключом из чата!</b>",
        "Смена вступает в силу немедленно, без перезапуска.",
    ]
    return "\n".join(lines)
