"""Smart symbol curation — анализ funding_snapshots за N дней и фильтр символов.

Самостоятельный CLI-скрипт. Не запускается из main.py. Назначение —
по накопленной истории funding_snapshots отобрать "хорошие" символы:
стабильные funding-выплаты, без свежих спайков, достаточно данных.

Запуск:
    python3 curate_symbols.py --days 30
    python3 curate_symbols.py --days 30 --save-best .env.curated --min-apr 0.08

Метод: для каждого символа считаем агрегаты по ВСЕМ записям за окно
(объединяя биржи, потому что funding-edge — кросс-биржевая величина).

  mean_apr        — средний APR за период
  std_funding     — стандартное отклонение funding_rate
  cv              — coefficient of variation = std / |mean_funding_rate|
  n_spike_events_7d — сколько раз anti-spike сработал бы за последние
                      7 дней (текущий APR > 2.5× mean APR за окно)
  n_obs           — количество записей

Критерий допуска (PASS):
  mean_apr > min_apr (default 0.08 = 8% годовых)
  cv < max_cv (default 0.50)
  n_spike_events_7d == 0
  n_obs >= 200

Все вычисления — pure-SQLite + stdlib. Результат — моноширинная таблица
в stdout. По флагу --save-best PATH пишет .env-файл с ARB_ALLOWED_SYMBOLS.
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import config
import memory


# --- Параметры по умолчанию (сами лежат в _parse_args) ---------------

DEFAULT_DAYS = 30
DEFAULT_MIN_APR = 0.08
DEFAULT_MAX_CV = 0.50
DEFAULT_TOP = 20
DEFAULT_MIN_OBS = 200
SPIKE_RATIO = 2.5
SPIKE_LOOKBACK_DAYS = 7


# --- Структуры данных -----------------------------------------------

@dataclass
class _SymbolStats:
    """Агрегированные метрики по одному символу за окно."""

    symbol: str
    n_obs: int
    mean_apr: float
    std_funding: float
    cv: float
    n_spike_events_7d: int
    verdict: str  # 'PASS' или 'REJECT: <причина>'


# --- Загрузка истории ------------------------------------------------

def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_ts(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _load_per_symbol_rows(
    db_path: str,
    days: int,
) -> dict[str, list[tuple[datetime, float, float]]]:
    """Загрузить все snapshots за окно и сгруппировать по символу.

    Возвращает {symbol: [(ts, funding_rate, apr), ...]}. Сортировка
    внутри каждого символа — по ts asc.

    На свежей БД (нет таблицы) возвращаем пустой dict без exception.
    """
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat(
        timespec="seconds"
    )
    out: dict[str, list[tuple[datetime, float, float]]] = {}
    try:
        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='funding_snapshots'"
            ).fetchone()
            if not row:
                return {}
            rows = conn.execute(
                "SELECT symbol, ts, rate, apr FROM funding_snapshots "
                "WHERE ts >= ? ORDER BY symbol ASC, ts ASC",
                (cutoff,),
            ).fetchall()
    except sqlite3.Error as exc:
        print(f"[CURATE] Ошибка чтения БД: {exc}", file=sys.stderr)
        return {}

    for r in rows:
        try:
            sym = str(r["symbol"])
            ts = _parse_ts(str(r["ts"]))
            rate = float(r["rate"] or 0.0)
            apr = float(r["apr"] or 0.0)
        except (TypeError, ValueError):
            continue
        out.setdefault(sym, []).append((ts, rate, apr))
    return out


# --- Расчёт метрик ---------------------------------------------------

def _compute_symbol_stats(
    symbol: str,
    rows: list[tuple[datetime, float, float]],
    min_apr: float,
    max_cv: float,
    min_obs: int,
) -> _SymbolStats:
    """По списку (ts, rate, apr) посчитать агрегаты и вердикт.

    Метрики:
      mean_apr        — усреднение по всем записям;
      std_funding     — stdev funding_rate;
      cv              — std / |mean_rate| (защита от деления на 0);
      n_spike_events_7d — кол-во записей за последние SPIKE_LOOKBACK_DAYS,
                          у которых apr > SPIKE_RATIO * |mean_apr|.

    Вердикт: PASS, если все 4 критерия выполнены, иначе REJECT с самой
    важной причиной (по приоритету: insufficient_data > low_apr > unstable >
    spikes).
    """
    n = len(rows)
    if n == 0:
        return _SymbolStats(
            symbol=symbol, n_obs=0, mean_apr=0.0, std_funding=0.0,
            cv=0.0, n_spike_events_7d=0,
            verdict="REJECT: no_data",
        )

    rates = [r[1] for r in rows]
    aprs = [r[2] for r in rows]
    mean_apr = sum(aprs) / n
    mean_rate = sum(rates) / n

    if n > 1:
        try:
            std_funding = statistics.stdev(rates)
        except statistics.StatisticsError:
            std_funding = 0.0
    else:
        std_funding = 0.0

    cv = std_funding / abs(mean_rate) if abs(mean_rate) > 1e-12 else math.inf

    # Спайки: текущий APR > SPIKE_RATIO * |mean_apr| за последние 7 дней.
    cutoff_7d = datetime.now(tz=timezone.utc) - timedelta(days=SPIKE_LOOKBACK_DAYS)
    threshold = SPIKE_RATIO * abs(mean_apr)
    n_spike_events_7d = 0
    if threshold > 0:
        for ts, _rate, apr in rows:
            if ts < cutoff_7d:
                continue
            if abs(apr) > threshold:
                n_spike_events_7d += 1

    # Проверка вердикта по приоритету.
    if n < min_obs:
        verdict = f"REJECT: n_obs={n}<{min_obs}"
    elif mean_apr <= min_apr:
        verdict = f"REJECT: mean_apr={mean_apr*100:.1f}%<{min_apr*100:.1f}%"
    elif cv >= max_cv:
        cv_str = "inf" if math.isinf(cv) else f"{cv:.2f}"
        verdict = f"REJECT: cv={cv_str}>={max_cv:.2f}"
    elif n_spike_events_7d > 0:
        verdict = f"REJECT: spikes_7d={n_spike_events_7d}>0"
    else:
        verdict = "PASS"

    return _SymbolStats(
        symbol=symbol,
        n_obs=n,
        mean_apr=mean_apr,
        std_funding=std_funding,
        cv=cv,
        n_spike_events_7d=n_spike_events_7d,
        verdict=verdict,
    )


def curate(
    db_path: str,
    days: int,
    min_apr: float,
    max_cv: float,
    min_obs: int = DEFAULT_MIN_OBS,
) -> list[_SymbolStats]:
    """Прогнать курирование по всей истории и вернуть отсортированный список.

    Сортировка: сначала PASS-символы по убыванию mean_apr, затем
    REJECT-символы (тоже по убыванию mean_apr) — для удобной отладки.
    """
    grouped = _load_per_symbol_rows(db_path, days)
    if not grouped:
        return []

    out: list[_SymbolStats] = []
    for sym, rows in grouped.items():
        out.append(_compute_symbol_stats(sym, rows, min_apr, max_cv, min_obs))

    # PASS сначала, REJECT в конце; внутри — по убыванию mean_apr.
    out.sort(key=lambda s: (s.verdict != "PASS", -s.mean_apr))
    return out


# --- Вывод и сохранение ---------------------------------------------

def _format_table(results: list[_SymbolStats], top: int) -> str:
    """Моноширинная таблица: symbol, mean_apr, cv, spikes_7d, n_obs, verdict."""
    header = (
        f"{'symbol':<12} {'mean_apr':>10} {'cv':>7} "
        f"{'spikes_7d':>10} {'n_obs':>7}  verdict"
    )
    lines = [header, "-" * len(header)]
    for s in results[: max(1, top)]:
        cv_str = "inf" if math.isinf(s.cv) else f"{s.cv:.2f}"
        lines.append(
            f"{s.symbol:<12} {s.mean_apr*100:>9.2f}% {cv_str:>7} "
            f"{s.n_spike_events_7d:>10d} {s.n_obs:>7d}  {s.verdict}"
        )
    return "\n".join(lines)


def _save_best(path: str, pass_symbols: list[str]) -> None:
    """Записать ARB_ALLOWED_SYMBOLS=A,B,C в .env-формате.

    Если pass_symbols пуст — пишем закомментированную строку с пояснением,
    чтобы пользователь понимал, что курирование не нашло ни одного PASS.
    """
    if pass_symbols:
        body = ",".join(pass_symbols)
        env_line = f"ARB_ALLOWED_SYMBOLS={body}"
    else:
        body = ""
        env_line = "# ARB_ALLOWED_SYMBOLS=  # курирование не нашло PASS-символов"

    lines = [
        "# Сгенерировано curate_symbols.py — отобранные стабильные символы",
        "# (mean_apr > min_apr, cv < max_cv, без спайков за 7 дней, n_obs >= 200)",
        env_line,
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# --- CLI -------------------------------------------------------------

def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="curate_symbols.py",
        description=(
            "Анализ funding_snapshots в SQLite за окно дней и отбор стабильных "
            "символов для funding-арбитража."
        ),
    )
    p.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"Сколько дней истории брать (default {DEFAULT_DAYS}).",
    )
    p.add_argument(
        "--min-apr",
        type=float,
        default=DEFAULT_MIN_APR,
        help=f"Минимум mean_apr для PASS (default {DEFAULT_MIN_APR}).",
    )
    p.add_argument(
        "--max-cv",
        type=float,
        default=DEFAULT_MAX_CV,
        help=f"Максимум coefficient of variation (default {DEFAULT_MAX_CV}).",
    )
    p.add_argument(
        "--save-best",
        type=str,
        default=None,
        help="Записать список PASS-символов в .env-файл по этому пути.",
    )
    p.add_argument(
        "--db",
        type=str,
        default=None,
        help="Путь к SQLite (по умолчанию memory.DB_PATH).",
    )
    p.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP,
        help=f"Сколько строк показать в таблице (default {DEFAULT_TOP}).",
    )
    p.add_argument(
        "--min-obs",
        type=int,
        default=DEFAULT_MIN_OBS,
        help=f"Минимум наблюдений для PASS (default {DEFAULT_MIN_OBS}).",
    )
    p.add_argument(
        "--use-ml",
        action="store_true",
        help=(
            "Использовать ML-модель curator_model.json для дополнительной "
            "фильтрации rule-based PASS-символов."
        ),
    )
    p.add_argument(
        "--ml-model",
        type=str,
        default="curator_model.json",
        help="Путь к JSON-файлу с обученной моделью (default curator_model.json).",
    )
    p.add_argument(
        "--ml-threshold",
        type=float,
        default=0.6,
        help="Порог P(PASS) для ML-фильтра (default 0.6).",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    db_path = args.db or memory.DB_PATH

    results = curate(
        db_path=db_path,
        days=args.days,
        min_apr=args.min_apr,
        max_cv=args.max_cv,
        min_obs=args.min_obs,
    )

    if not results:
        print(
            "[CURATE] funding_snapshots пуст или таблица не существует. "
            "Запустите бота на несколько дней, чтобы накопить историю."
        )
        if args.save_best:
            # Всё равно записываем пустой файл — для consistency с CI.
            _save_best(args.save_best, [])
            print(f"[CURATE] Пустой результат записан в {args.save_best}")
        return 0

    pass_symbols = [s.symbol for s in results if s.verdict == "PASS"]
    n_total = len(results)
    n_pass = len(pass_symbols)

    # ML-фильтр поверх rule-based PASS (опционально).
    if getattr(args, "use_ml", False):
        try:
            import ml_curator
        except ImportError as exc:
            print(f"[CURATE] ml_curator import fail: {exc}, ML отключён.")
        else:
            model = ml_curator.load_model(args.ml_model)
            if model is None:
                print(
                    f"[CURATE] ML-модель {args.ml_model} не найдена, "
                    "использую только rule-based."
                )
            else:
                print(
                    f"[CURATE] Применяю ML-фильтр (threshold={args.ml_threshold})."
                )
                # Перезагружаем сырые rows (не агрегаты) для каждого PASS.
                grouped = _load_per_symbol_rows(db_path, args.days)
                ml_pass: list[str] = []
                for s in results:
                    if s.verdict != "PASS":
                        continue
                    features = ml_curator.extract_features(grouped.get(s.symbol, []))
                    if features is None:
                        # Слишком мало данных для ML — оставляем как есть, но
                        # прозрачно сообщаем.
                        print(f"  {s.symbol}: ml_features=None (мало данных)")
                        ml_pass.append(s.symbol)
                        continue
                    prob = ml_curator.predict(features, model)
                    print(f"  {s.symbol}: ml_prob={prob:.3f}")
                    if prob >= args.ml_threshold:
                        ml_pass.append(s.symbol)
                # Финальные PASS = пересечение rule_pass и ml_pass.
                for s in results:
                    if s.verdict == "PASS" and s.symbol not in ml_pass:
                        s.verdict = f"REJECT: ml_prob<{args.ml_threshold}"
                pass_symbols = [s.symbol for s in results if s.verdict == "PASS"]
                n_pass = len(pass_symbols)

    print(
        f"[CURATE] Проанализировано {n_total} символов за {args.days} дней. "
        f"PASS: {n_pass}, REJECT: {n_total - n_pass}."
    )
    print()
    print(_format_table(results, args.top))
    print()

    if pass_symbols:
        print(f"PASS-символы ({n_pass}): {', '.join(pass_symbols)}")
    else:
        print(
            "Ни один символ не прошёл фильтр. Попробуйте снизить --min-apr "
            "или собрать больше истории."
        )

    if args.save_best:
        _save_best(args.save_best, pass_symbols)
        print(f"[CURATE] Список сохранён в {args.save_best}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
