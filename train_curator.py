"""CLI для тренировки ML-curator на собственной истории funding_snapshots.

Запуск:
    python3 train_curator.py --train-window 60 --target-window 30 \\
                             --output curator_model.json

Идея: разделить накопленную историю на train (старая часть) и target
(последние target-window дней). Для каждого символа:
  features  = вычислены по train-окну;
  label     = 1, если в target-окне символ дал бы PASS (mean_apr > min_apr,
              spikes==0), иначе 0.

Получившийся dataset обучаем lr-моделью из ml_curator.train(). Результат
сохраняется JSON-ом — позже curate_symbols.py --use-ml использует его
как доп. фильтр поверх rule-based PASS.

Если истории мало (<5 размеченных примеров) — печатаем предупреждение
и выходим с кодом 0 (не падаем, чтобы CI/cron не считал это ошибкой).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import memory
import ml_curator


def _load_per_symbol(db_path: str, days_total: int) -> dict[str, list]:
    """Загрузить funding_snapshots за days_total дней, сгруппировать по символу."""
    cutoff = (
        datetime.now(tz=timezone.utc) - timedelta(days=days_total)
    ).isoformat(timespec="seconds")
    out: dict[str, list] = {}
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            r = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='funding_snapshots'"
            ).fetchone()
            if not r:
                return {}
            rows = conn.execute(
                "SELECT symbol, ts, rate, apr FROM funding_snapshots "
                "WHERE ts >= ? ORDER BY ts",
                (cutoff,),
            ).fetchall()
    except sqlite3.Error:
        return {}

    for row in rows:
        sym = str(row["symbol"])
        try:
            ts = datetime.fromisoformat(str(row["ts"]))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            rate = float(row["rate"] or 0)
            apr = float(row["apr"] or 0)
        except (TypeError, ValueError):
            continue
        out.setdefault(sym, []).append((ts, rate, apr))
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="train_curator.py")
    p.add_argument("--train-window", type=int, default=60,
                   help="Сколько дней истории брать в features (default 60).")
    p.add_argument("--target-window", type=int, default=30,
                   help="Сколько дней брать в target/label (default 30).")
    p.add_argument("--output", type=str, default="curator_model.json",
                   help="Куда сохранить обученную модель.")
    p.add_argument("--db", type=str, default=None,
                   help="Путь к SQLite (по умолчанию memory.DB_PATH).")
    p.add_argument("--min-apr", type=float, default=0.08,
                   help="Порог mean_apr в target-окне для label=1.")
    args = p.parse_args(argv)

    db = args.db or memory.DB_PATH
    total_days = args.train_window + args.target_window
    grouped = _load_per_symbol(db, total_days)
    if not grouped:
        print("[TRAIN] funding_snapshots пуст или таблица не существует.")
        return 0

    cutoff_target_start = datetime.now(tz=timezone.utc) - timedelta(days=args.target_window)

    training_data: list = []
    for sym, rows in grouped.items():
        train_rows = [r for r in rows if r[0] < cutoff_target_start]
        target_rows = [r for r in rows if r[0] >= cutoff_target_start]
        if len(train_rows) < 10 or len(target_rows) < 10:
            continue

        features = ml_curator.extract_features(train_rows)
        if features is None:
            continue

        # Target: 1 если за target window mean_apr > min_apr И spikes == 0.
        target_aprs = [r[2] for r in target_rows]
        mean_target_apr = sum(target_aprs) / len(target_aprs)
        cutoff_7d = datetime.now(tz=timezone.utc) - timedelta(days=7)
        spike_threshold = 2.5 * abs(mean_target_apr)
        n_spikes = sum(
            1 for ts, _r, apr in target_rows
            if ts >= cutoff_7d and abs(apr) > spike_threshold
        )
        target = 1 if (mean_target_apr > args.min_apr and n_spikes == 0) else 0

        training_data.append((features, target))

    if len(training_data) < 5:
        print(
            f"[TRAIN] Недостаточно training-примеров ({len(training_data)}), "
            "нужно >= 5."
        )
        return 0

    model = ml_curator.train(training_data)
    print(
        f"[TRAIN] Обучена модель: accuracy={model['accuracy']:.3f} "
        f"на {len(training_data)} примерах."
    )
    print(f"[TRAIN] Weights: {[round(w, 4) for w in model['weights']]}")
    print(f"[TRAIN] Bias: {model['bias']:.4f}")

    ml_curator.save_model(model, args.output)
    print(f"[TRAIN] Модель сохранена в {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
