"""key_manager.py — runtime API-key override manager с опциональным шифрованием.

Ключи хранятся в `keys_override.json` (или `.enc` если шифрование вкл.).
При загрузке записываются в os.environ — остальной код читает через os.getenv.

Шифрование (опциональное):
  Если задана переменная окружения MASTER_KEY (≥ 16 символов) — файл
  шифруется. Используется stdlib-only: PBKDF2-HMAC-SHA256 для KDF +
  HMAC-SHA256 stream cipher (XOR с keystream от counter-mode HMAC).
  Это обеспечивает confidentiality + authenticity (HMAC-MAC).
  Без MASTER_KEY работает в plaintext-режиме (как раньше) — для обратной
  совместимости.

  ВАЖНО: для production-grade шифрования установите `cryptography` и
  используйте Fernet. Stdlib-режим защищает от случайного чтения файла,
  но не от целевой криптоатаки на сервер.

Управляемые переменные (можно менять через Telegram /setkey):
  Все API-ключи бирж (см. MANAGEABLE_KEYS).

НЕ управляются здесь (граница безопасности):
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID — рубят канал управления.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Optional

_OVERRIDE_FILE_PLAIN = Path(__file__).parent / "keys_override.json"
_OVERRIDE_FILE_ENC = Path(__file__).parent / "keys_override.enc"

MANAGEABLE_KEYS: tuple[str, ...] = (
    "OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE",
    "BYBIT_API_KEY", "BYBIT_API_SECRET",
    "BINANCE_API_KEY", "BINANCE_API_SECRET",
    "GATE_API_KEY", "GATE_API_SECRET",
    "BITGET_API_KEY", "BITGET_API_SECRET", "BITGET_PASSPHRASE",
    "MEXC_API_KEY", "MEXC_API_SECRET",
    "HTX_API_KEY", "HTX_API_SECRET",
    "BINGX_API_KEY", "BINGX_API_SECRET",
)

_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("OKX",     ("OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE")),
    ("Bybit",   ("BYBIT_API_KEY", "BYBIT_API_SECRET")),
    ("Binance", ("BINANCE_API_KEY", "BINANCE_API_SECRET")),
    ("Gate.io", ("GATE_API_KEY", "GATE_API_SECRET")),
    ("Bitget",  ("BITGET_API_KEY", "BITGET_API_SECRET", "BITGET_PASSPHRASE")),
    ("MEXC",    ("MEXC_API_KEY", "MEXC_API_SECRET")),
    ("HTX",     ("HTX_API_KEY", "HTX_API_SECRET")),
    ("BingX",   ("BINGX_API_KEY", "BINGX_API_SECRET")),
)


# --- Encryption (stdlib only) ---------------------------------------

_KDF_ITERATIONS = 200_000
_SALT_LEN = 16
_NONCE_LEN = 16
_MAC_LEN = 32


def _master_key() -> Optional[bytes]:
    raw = os.getenv("MASTER_KEY", "").strip()
    if len(raw) < 16:
        return None
    return raw.encode("utf-8")


def _derive(master: bytes, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", master, salt, _KDF_ITERATIONS, dklen=64)


def _xor_stream(key: bytes, nonce: bytes, data: bytes) -> bytes:
    """HMAC-SHA256 в counter-mode → keystream → XOR."""
    out = bytearray(len(data))
    block = 0
    pos = 0
    while pos < len(data):
        ks = hmac.new(
            key,
            nonce + block.to_bytes(8, "big"),
            hashlib.sha256,
        ).digest()
        end = min(pos + len(ks), len(data))
        for i in range(end - pos):
            out[pos + i] = data[pos + i] ^ ks[i]
        pos = end
        block += 1
    return bytes(out)


def _encrypt(plaintext: bytes, master: bytes) -> bytes:
    """layout: salt(16) | nonce(16) | mac(32) | ciphertext"""
    salt = secrets.token_bytes(_SALT_LEN)
    nonce = secrets.token_bytes(_NONCE_LEN)
    derived = _derive(master, salt)
    enc_key, mac_key = derived[:32], derived[32:64]
    ct = _xor_stream(enc_key, nonce, plaintext)
    mac = hmac.new(mac_key, salt + nonce + ct, hashlib.sha256).digest()
    return salt + nonce + mac + ct


def _decrypt(blob: bytes, master: bytes) -> Optional[bytes]:
    if len(blob) < _SALT_LEN + _NONCE_LEN + _MAC_LEN:
        return None
    salt = blob[:_SALT_LEN]
    nonce = blob[_SALT_LEN:_SALT_LEN + _NONCE_LEN]
    mac = blob[_SALT_LEN + _NONCE_LEN:_SALT_LEN + _NONCE_LEN + _MAC_LEN]
    ct = blob[_SALT_LEN + _NONCE_LEN + _MAC_LEN:]
    derived = _derive(master, salt)
    enc_key, mac_key = derived[:32], derived[32:64]
    expected = hmac.new(mac_key, salt + nonce + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        return None  # tampered or wrong key
    return _xor_stream(enc_key, nonce, ct)


# --- Load / Save ----------------------------------------------------

def _read_overrides() -> dict[str, str]:
    """Прочитать оверрайды (encrypted приоритетно, plain fallback)."""
    master = _master_key()

    if _OVERRIDE_FILE_ENC.exists() and master:
        try:
            blob = _OVERRIDE_FILE_ENC.read_bytes()
            plain = _decrypt(blob, master)
            if plain is None:
                print(
                    "[key_manager] keys_override.enc tampered or wrong MASTER_KEY"
                )
                return {}
            return json.loads(plain.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"[key_manager] Ошибка чтения encrypted: {exc}")
            return {}

    if _OVERRIDE_FILE_PLAIN.exists():
        try:
            data: dict[str, str] = json.loads(
                _OVERRIDE_FILE_PLAIN.read_text(encoding="utf-8")
            )
            if master:
                # MASTER_KEY задан, а файл plain — мигрируем при первой
                # записи (см. _write_overrides).
                print(
                    "[key_manager] MASTER_KEY задан, но keys_override.json plain. "
                    "Будет мигрировано при следующем /setkey."
                )
            return data
        except Exception as exc:  # noqa: BLE001
            print(f"[key_manager] Ошибка чтения plain: {exc}")
            return {}
    return {}


def _write_overrides(data: dict[str, str]) -> None:
    """Записать оверрайды. Если MASTER_KEY задан — encrypted, иначе plain."""
    master = _master_key()
    payload = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")

    if master:
        blob = _encrypt(payload, master)
        _OVERRIDE_FILE_ENC.write_bytes(blob)
        # Удаляем plain если был — миграция.
        if _OVERRIDE_FILE_PLAIN.exists():
            try:
                _OVERRIDE_FILE_PLAIN.unlink()
                print("[key_manager] keys_override.json (plain) удалён после миграции в .enc")
            except OSError:
                pass
    else:
        _OVERRIDE_FILE_PLAIN.write_text(
            payload.decode("utf-8"), encoding="utf-8"
        )


def load_overrides() -> dict[str, str]:
    """Загрузить оверрайды и применить к os.environ. Вызывается на старте."""
    data = _read_overrides()
    applied: dict[str, str] = {}
    for k, v in data.items():
        if k in MANAGEABLE_KEYS and isinstance(v, str) and v:
            os.environ[k] = v
            applied[k] = v
    if applied:
        master_label = "ENCRYPTED" if _master_key() else "PLAIN"
        print(
            f"[key_manager] Загружено {len(applied)} оверрайд(ов) "
            f"[{master_label}]: {', '.join(applied)}"
        )
    return applied


def set_key(name: str, value: str) -> None:
    """Сохранить оверрайд и применить."""
    if name not in MANAGEABLE_KEYS:
        raise ValueError(
            f"Ключ «{name}» не в списке управляемых.\n"
            f"Доступны: {', '.join(MANAGEABLE_KEYS)}"
        )
    value = value.strip()
    if not value:
        raise ValueError("Значение не может быть пустым.")

    existing = _read_overrides()
    existing[name] = value
    _write_overrides(existing)
    os.environ[name] = value


def delete_key(name: str) -> bool:
    """Удалить оверрайд."""
    existing = _read_overrides()
    if name not in existing:
        return False
    del existing[name]
    _write_overrides(existing)
    os.environ.pop(name, None)
    return True


def _mask(val: str) -> str:
    if not val:
        return "❌ не задан"
    if len(val) <= 6:
        return "•" * len(val)
    return "•" * (len(val) - 4) + val[-4:]


def get_status_report() -> str:
    """Маскированный статус всех ключей."""
    overrides_set: set[str] = set(_read_overrides().keys())
    enc_status = "ENCRYPTED ✓" if _master_key() else "plain (set MASTER_KEY for encryption)"

    lines = ["🔑 <b>API-ключи (статус)</b>", f"<i>Хранилище: {enc_status}</i>", ""]
    for group_name, keys in _GROUPS:
        lines.append(f"<b>{group_name}:</b>")
        for k in keys:
            val = os.getenv(k, "")
            src = " <i>(override)</i>" if k in overrides_set else " <i>(env)</i>"
            lines.append(f"  <code>{k}</code>: {_mask(val)}{src}")
        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        "<b>Сменить:</b> <code>/setkey ИМЯ значение</code>",
        "<b>Сбросить:</b> <code>/delkey ИМЯ</code>",
        "",
        "⚠️ <b>Сразу удалите сообщение с ключом из чата!</b>",
    ]
    return "\n".join(lines)
