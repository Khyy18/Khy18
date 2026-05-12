"""Синхронный загрузчик исторических 1m-свечей Binance.

Источник - публичный архив Binance Vision:
  https://data.binance.vision/data/spot/monthly/klines/<SYM>/1m/<SYM>-1m-YYYY-MM.zip

Загрузка выполняется через stdlib (`urllib.request` + `zipfile`): в отличие
от лайв-контура бот-а (aiohttp) здесь нам нужен простой блокирующий код,
который не требует event loop и легко поддаётся unit-тестам на CSV-срезах.

Все сетевые ошибки глушим с русским предупреждением в stdout - бэктестер
должен уметь запускаться из синтетики, даже если сеть недоступна.
"""

from __future__ import annotations

import csv
import datetime
import os
import urllib.error
import urllib.request
import zipfile
from typing import Optional


_BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"


def _build_url(symbol: str, year: int, month: int) -> str:
    tag = f"{symbol}-1m-{year:04d}-{month:02d}"
    return f"{_BASE_URL}/{symbol}/1m/{tag}.zip"


def download_binance_month(
    symbol: str,
    year: int,
    month: int,
    cache_dir: str,
) -> Optional[str]:
    """Скачать и распаковать месячный архив 1m-свечей Binance.

    Возвращает путь к распакованному CSV. Если CSV уже лежит в кэше,
    сразу возвращаем его (без обращения к сети). При любой сетевой
    ошибке пишем русское предупреждение и возвращаем None.
    """
    os.makedirs(cache_dir, exist_ok=True)
    tag = f"{symbol}-1m-{year:04d}-{month:02d}"
    csv_path = os.path.join(cache_dir, f"{tag}.csv")
    zip_path = os.path.join(cache_dir, f"{tag}.zip")

    if os.path.exists(csv_path):
        return csv_path

    url = _build_url(symbol, year, month)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = resp.read()
        with open(zip_path, "wb") as f:
            f.write(data)
    except urllib.error.HTTPError as exc:
        print(f"[DATA] HTTP {exc.code} для {url}: пропускаем месяц")
        return None
    except urllib.error.URLError as exc:
        print(f"[DATA] Сетевая ошибка Binance {url}: {exc.reason}")
        return None
    except OSError as exc:
        print(f"[DATA] Не удалось записать {zip_path}: {exc}")
        return None

    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = zf.namelist()
            if not members:
                print(f"[DATA] Пустой архив {zip_path}")
                return None
            # Архивы Binance содержат один CSV с тем же базовым именем.
            inner = members[0]
            with zf.open(inner) as src, open(csv_path, "wb") as dst:
                dst.write(src.read())
    except (zipfile.BadZipFile, OSError) as exc:
        print(f"[DATA] Повреждённый ZIP {zip_path}: {exc}")
        return None

    return csv_path


def load_csv(path: str) -> list[dict]:
    """Распарсить CSV Binance (12 колонок) в список словарей-свечей.

    Формат колонок:
        open_time, open, high, low, close, volume, close_time,
        quote_volume, trades, taker_buy_base, taker_buy_quote, ignore
    Строки с битыми значениями пропускаются.
    """
    out: list[dict] = []
    try:
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                try:
                    candle = {
                        "ts": int(row[0]),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]),
                    }
                except (IndexError, ValueError):
                    continue
                out.append(candle)
    except OSError as exc:
        print(f"[DATA] Не удалось открыть CSV {path}: {exc}")
        return []
    out.sort(key=lambda c: c["ts"])
    return out


def _month_iter(date_from: datetime.date, date_to: datetime.date):
    """Генератор (year, month), от date_from до date_to включительно."""
    y, m = date_from.year, date_from.month
    end_y, end_m = date_to.year, date_to.month
    while (y, m) <= (end_y, end_m):
        yield y, m
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1


def load_range(
    symbol: str,
    date_from: str,
    date_to: str,
    cache_dir: str,
) -> list[dict]:
    """Загрузить 1m-свечи за интервал [date_from, date_to] включительно.

    Для каждого месяца: если CSV отсутствует, пытаемся скачать.
    Итоговый список обрезается по границам интервала (ms epoch) и сортируется.
    При полном отсутствии данных выводим предупреждение и возвращаем [].
    """
    try:
        d_from = datetime.date.fromisoformat(date_from)
        d_to = datetime.date.fromisoformat(date_to)
    except ValueError as exc:
        print(f"[DATA] Неверный формат даты: {exc}")
        return []
    if d_from > d_to:
        print("[DATA] date_from позже date_to, диапазон пуст")
        return []

    ts_from = int(
        datetime.datetime(d_from.year, d_from.month, d_from.day).timestamp() * 1000
    )
    ts_to_exclusive = int(
        datetime.datetime(d_to.year, d_to.month, d_to.day).timestamp() * 1000
    ) + 24 * 60 * 60 * 1000  # включительно по date_to: + 1 сутки

    collected: list[dict] = []
    for (y, m) in _month_iter(d_from, d_to):
        csv_path = os.path.join(cache_dir, f"{symbol}-1m-{y:04d}-{m:02d}.csv")
        if not os.path.exists(csv_path):
            csv_path = download_binance_month(symbol, y, m, cache_dir) or ""
        if csv_path and os.path.exists(csv_path):
            collected.extend(load_csv(csv_path))

    if not collected:
        print(f"[DATA] Пусто: {symbol} {date_from}..{date_to}")
        return []

    filtered = [c for c in collected if ts_from <= c["ts"] < ts_to_exclusive]
    filtered.sort(key=lambda c: c["ts"])
    return filtered
