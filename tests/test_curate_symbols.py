"""Тесты smart symbol curation (curate_symbols.py).

Проверяем:
  - test_curate_with_synthetic_data — стабильный BTC PASS, нестабильный JTO REJECT.
  - test_curate_handles_empty_db — пустая БД → пустой список без exception.
  - test_save_best_writes_env_format — --save-best пишет
    ARB_ALLOWED_SYMBOLS=BTCUSDT,ETHUSDT в env-формате.
"""

from __future__ import annotations

import math
import random
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest


# --- Фикстуры --------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """SQLite в tmp_path вместо рабочего trades.db."""
    db_path = tmp_path / "test_trades.db"
    import memory
    import funding_history as fh
    monkeypatch.setattr(memory, "DB_PATH", str(db_path))
    fh.init_db()
    return str(db_path)


def _seed_symbol_history(
    db_path: str,
    symbol: str,
    mean_apr: float,
    cv: float,
    n_ticks: int = 250,
    tick_minutes: int = 60,
    exchange: str = "bybit",
    seed: int = 42,
) -> int:
    """Записать n_ticks снимков для символа с заданными mean_apr и cv.

    Логика: rate имеет mean = mean_apr / (24/8 * 365) = mean_apr / 1095.
    std = cv * |mean|. APR на каждый тик = rate * 1095.

    Используем Random с фиксированным seed, чтобы тест был детерминированным.
    """
    rnd = random.Random(seed)
    mean_rate = mean_apr / 1095.0  # APR -> per-8h rate
    std_rate = cv * abs(mean_rate)
    now = datetime.now(tz=timezone.utc)

    rows: list[tuple] = []
    for i in range(n_ticks):
        ts = (now - timedelta(minutes=tick_minutes * (n_ticks - 1 - i))).isoformat(
            timespec="seconds"
        )
        rate = rnd.gauss(mean_rate, std_rate)
        apr = rate * 1095.0
        rows.append((exchange, symbol, ts, rate, apr, 30000.0, 8.0))

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO funding_snapshots "
            "(exchange, symbol, ts, rate, apr, mark_price, interval_hours) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    return len(rows)


# --- Тесты -----------------------------------------------------------

def test_curate_with_synthetic_data(tmp_db):
    """BTCUSDT (mean 12% APR, cv 0.20) → PASS.
    JTOUSDT (mean 12% APR, cv 0.80) → REJECT по cv.
    """
    import curate_symbols

    _seed_symbol_history(
        tmp_db, "BTCUSDT", mean_apr=0.12, cv=0.20, n_ticks=250, seed=1,
    )
    _seed_symbol_history(
        tmp_db, "JTOUSDT", mean_apr=0.12, cv=0.80, n_ticks=250, seed=2,
    )

    results = curate_symbols.curate(
        db_path=tmp_db,
        days=30,
        min_apr=0.08,
        max_cv=0.50,
        min_obs=200,
    )

    by_symbol = {s.symbol: s for s in results}
    assert "BTCUSDT" in by_symbol
    assert "JTOUSDT" in by_symbol

    btc = by_symbol["BTCUSDT"]
    jto = by_symbol["JTOUSDT"]

    # BTC: cv 0.2, 250 obs, mean 12% — должен PASS.
    assert btc.verdict == "PASS", (
        f"BTC ожидался PASS, got {btc.verdict} (cv={btc.cv:.2f}, "
        f"mean_apr={btc.mean_apr*100:.1f}%, n_obs={btc.n_obs})"
    )
    assert btc.cv < 0.50
    assert btc.n_obs >= 200

    # JTO: cv 0.8 → REJECT по cv.
    assert "REJECT" in jto.verdict, f"JTO ожидался REJECT, got {jto.verdict}"
    assert "cv" in jto.verdict.lower()


def test_curate_handles_empty_db(tmp_db):
    """Пустая funding_snapshots → curate() возвращает [] без exception."""
    import curate_symbols

    results = curate_symbols.curate(
        db_path=tmp_db,
        days=30,
        min_apr=0.08,
        max_cv=0.50,
        min_obs=200,
    )
    assert results == []


def test_curate_main_handles_empty_db(tmp_db, capsys):
    """main() с пустой БД печатает сообщение и выходит с кодом 0."""
    import curate_symbols

    rc = curate_symbols.main(["--days", "30", "--db", tmp_db])
    captured = capsys.readouterr()
    assert rc == 0
    assert "пуст" in captured.out.lower() or "не существует" in captured.out


def test_save_best_writes_env_format(tmp_path):
    """_save_best() пишет ARB_ALLOWED_SYMBOLS в .env-формате."""
    import curate_symbols

    out_path = tmp_path / "curated.env"
    curate_symbols._save_best(str(out_path), ["BTCUSDT", "ETHUSDT"])

    text = out_path.read_text(encoding="utf-8")
    lines = text.strip().split("\n")

    # Главная KEY=VALUE строка.
    assert "ARB_ALLOWED_SYMBOLS=BTCUSDT,ETHUSDT" in lines, (
        f"ожидался ARB_ALLOWED_SYMBOLS=BTCUSDT,ETHUSDT, получено:\n{text}"
    )
    # Заголовочные комментарии.
    assert any(line.startswith("#") for line in lines)


def test_save_best_writes_env_with_three_symbols(tmp_path):
    """Sanity: 3 символа в правильном порядке через запятую без пробелов."""
    import curate_symbols

    out_path = tmp_path / "curated3.env"
    curate_symbols._save_best(str(out_path), ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    text = out_path.read_text(encoding="utf-8")
    assert "ARB_ALLOWED_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT" in text


def test_save_best_handles_empty_pass_list(tmp_path):
    """Если PASS-список пуст, файл всё равно создаётся, но строка
    закомментирована — это сигнал, что курирование не нашло символов.
    """
    import curate_symbols

    out_path = tmp_path / "empty.env"
    curate_symbols._save_best(str(out_path), [])
    text = out_path.read_text(encoding="utf-8")
    # Не должно быть активной строки ARB_ALLOWED_SYMBOLS=value.
    for line in text.strip().split("\n"):
        if line.startswith("ARB_ALLOWED_SYMBOLS="):
            pytest.fail(
                f"при пустом списке не должно быть активной строки, got: {line}"
            )
    # Должен быть комментарий-объяснение.
    assert "#" in text


def test_curate_rejects_symbol_with_few_observations(tmp_db):
    """Символ с n_obs < 200 → REJECT по n_obs независимо от cv/mean."""
    import curate_symbols

    _seed_symbol_history(
        tmp_db, "DOGEUSDT", mean_apr=0.12, cv=0.10, n_ticks=50, seed=3,
    )

    results = curate_symbols.curate(
        db_path=tmp_db,
        days=30,
        min_apr=0.08,
        max_cv=0.50,
        min_obs=200,
    )
    assert len(results) == 1
    s = results[0]
    assert s.symbol == "DOGEUSDT"
    assert "REJECT" in s.verdict
    assert "n_obs" in s.verdict
