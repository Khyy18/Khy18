"""Тесты key_manager: encrypt/decrypt, set_key/delete_key/load."""

import os
from pathlib import Path

import pytest


@pytest.fixture
def tmp_key_files(monkeypatch, tmp_path):
    """Перенаправить пути override-файлов в tmp."""
    import key_manager as km
    plain = tmp_path / "keys_override.json"
    enc = tmp_path / "keys_override.enc"
    monkeypatch.setattr(km, "_OVERRIDE_FILE_PLAIN", plain)
    monkeypatch.setattr(km, "_OVERRIDE_FILE_ENC", enc)
    yield km, plain, enc


def test_encrypt_decrypt_roundtrip(tmp_key_files, monkeypatch):
    km, _, _ = tmp_key_files
    monkeypatch.setenv("MASTER_KEY", "this_is_a_long_master_key_xx")
    payload = b'{"BYBIT_API_KEY": "secret_value_123"}'
    master = km._master_key()
    blob = km._encrypt(payload, master)
    assert blob != payload  # действительно зашифровано
    decrypted = km._decrypt(blob, master)
    assert decrypted == payload


def test_decrypt_with_wrong_key_returns_none(tmp_key_files, monkeypatch):
    km, _, _ = tmp_key_files
    monkeypatch.setenv("MASTER_KEY", "this_is_a_long_master_key_xx")
    master = km._master_key()
    blob = km._encrypt(b"secret", master)

    monkeypatch.setenv("MASTER_KEY", "this_is_a_DIFFERENT_master_key")
    wrong = km._master_key()
    assert km._decrypt(blob, wrong) is None  # MAC не совпал


def test_decrypt_tampered_blob_returns_none(tmp_key_files, monkeypatch):
    km, _, _ = tmp_key_files
    monkeypatch.setenv("MASTER_KEY", "this_is_a_long_master_key_xx")
    master = km._master_key()
    blob = bytearray(km._encrypt(b"secret", master))
    # Подменим один байт ciphertext.
    blob[-1] ^= 0xFF
    assert km._decrypt(bytes(blob), master) is None


def test_set_key_writes_plain_when_no_master(tmp_key_files, monkeypatch):
    km, plain, enc = tmp_key_files
    monkeypatch.delenv("MASTER_KEY", raising=False)
    km.set_key("BYBIT_API_KEY", "abc123")
    assert plain.exists()
    assert not enc.exists()
    assert "abc123" in plain.read_text()


def test_set_key_writes_encrypted_when_master_set(tmp_key_files, monkeypatch):
    km, plain, enc = tmp_key_files
    monkeypatch.setenv("MASTER_KEY", "this_is_a_long_master_key_xx")
    km.set_key("BYBIT_API_KEY", "abc123")
    assert enc.exists()
    assert not plain.exists()
    raw = enc.read_bytes()
    assert b"abc123" not in raw  # не plaintext


def test_load_overrides_applies_to_environ(tmp_key_files, monkeypatch):
    km, _, _ = tmp_key_files
    monkeypatch.delenv("BYBIT_API_KEY", raising=False)
    monkeypatch.delenv("MASTER_KEY", raising=False)
    km.set_key("BYBIT_API_KEY", "loaded_value")
    monkeypatch.delenv("BYBIT_API_KEY", raising=False)  # симулируем фреш-старт
    km.load_overrides()
    assert os.environ.get("BYBIT_API_KEY") == "loaded_value"


def test_set_key_rejects_unknown(tmp_key_files):
    km, _, _ = tmp_key_files
    with pytest.raises(ValueError, match="не в списке"):
        km.set_key("NOT_A_KEY", "x")


def test_set_key_rejects_empty_value(tmp_key_files):
    km, _, _ = tmp_key_files
    with pytest.raises(ValueError, match="не может быть пустым"):
        km.set_key("BYBIT_API_KEY", "")


def test_delete_key_removes_from_storage(tmp_key_files, monkeypatch):
    km, _, _ = tmp_key_files
    monkeypatch.delenv("MASTER_KEY", raising=False)
    km.set_key("BYBIT_API_KEY", "x")
    assert km.delete_key("BYBIT_API_KEY") is True
    assert km.delete_key("BYBIT_API_KEY") is False  # уже нет


def test_master_key_too_short_treated_as_disabled(tmp_key_files, monkeypatch):
    km, _, _ = tmp_key_files
    monkeypatch.setenv("MASTER_KEY", "short")
    assert km._master_key() is None  # < 16 символов
