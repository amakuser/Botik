"""
ML-сервис: отдельный процесс. Запуск: из корня проекта python -m ml_service.run_loop [--config config.yaml]
- Online-аналитика: каждые N сек статистики за последние M минут (доля прибыльных котировок, средний спред, adverse selection) -> summary в БД/JSON.
- Offline-обучение: по расписанию/по накоплению — dataset из metrics + fills, метка y, walk-forward, гейт через model_registry.
Торговый процесс может опционально читать активную модель и использовать score как фильтр; RiskManager остаётся последней инстанцией.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Добавляем корень проекта в path для импорта src.botik
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.botik.config import load_config
from src.botik.storage.sqlite_store import get_connection, get_active_model, upsert_model_registry
from src.botik.utils.logging import setup_logging
from src.botik.utils.retention import run_retention

from ml_service.dataset import get_feature_matrix_and_labels
from ml_service.evaluate import is_better_than_current
from ml_service.train import train_model

logger = logging.getLogger(__name__)


def run_online_analytics(conn, config, interval_sec: int = 60, window_minutes: int = 5) -> None:
    """
    Считает за последние window_minutes: доля «хороших» метрик (например spread >= min_spread),
    средний спред, простая статистика. Пишет summary в JSON/файл или в отдельную таблицу.
    Упрощённо: агрегат по metrics_1s за последние N минут.
    """
    from src.botik.utils.time import utc_now_iso
    # Выбираем метрики за последние window_minutes (упрощённо — по ts_utc)
    cutoff = (datetime.now(timezone.utc).replace(tzinfo=timezone.utc)).strftime("%Y-%m-%d")
    cur = conn.execute(
        """SELECT symbol, AVG(spread_ticks) as avg_spread, COUNT(*) as cnt
           FROM metrics_1s WHERE ts_utc >= ? GROUP BY symbol""",
        (cutoff,),
    )
    rows = cur.fetchall()
    summary = {
        "ts": utc_now_iso(),
        "window_minutes": window_minutes,
        "symbols": {r[0]: {"avg_spread_ticks": r[1], "count": r[2]} for r in rows},
    }
    logger.info("Online analytics: %s", json.dumps(summary, ensure_ascii=False))
    # Можно записать в таблицу или в data/ml_summary.json
    out_path = Path("data/ml_summary.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def run_offline_training(conn, config, model_dir: str = "data/models") -> None:
    """Обучает модель по данным из БД; если лучше текущей — записывает в model_registry как активную."""
    for symbol in config.symbols:
        X, y = get_feature_matrix_and_labels(conn, symbol, limit=50000)
        if len(X) < 500:
            logger.warning("Мало данных для %s: %d", symbol, len(X))
            continue
        model_id, path, metrics = train_model(X, y, model_dir=model_dir)
        if not model_id:
            continue
        active = get_active_model(conn)
        current_json = active["metrics_json"] if active else None
        if is_better_than_current(metrics, current_json):
            upsert_model_registry(
                conn,
                model_id=model_id,
                path_or_payload=path,
                metrics_json=json.dumps(metrics),
                created_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                is_active=True,
            )
            logger.info("Новая модель активирована: %s", model_id)
        else:
            upsert_model_registry(
                conn,
                model_id=model_id,
                path_or_payload=path,
                metrics_json=json.dumps(metrics),
                created_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                is_active=False,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="ML service (отдельный процесс)")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--online-interval", type=int, default=60)
    parser.add_argument("--train-once", action="store_true", help="Один запуск обучения без цикла")
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(
        log_dir=config.logging.dir,
        max_bytes=config.logging.max_bytes,
        backup_count=config.logging.backup_count,
    )
    conn = get_connection(config.storage.path)

    if args.train_once:
        run_offline_training(conn, config)
        conn.close()
        return

    last_train_day: list[int] = [-1]  # mutable to allow update in closure

    async def loop() -> None:
        while True:
            run_online_analytics(conn, config, interval_sec=args.online_interval, window_minutes=5)
            today = datetime.now(timezone.utc).date().toordinal()
            if today != last_train_day[0]:
                last_train_day[0] = today
                run_offline_training(conn, config)
                run_retention(
                    conn,
                    config.storage.path,
                    retention_days=config.retention_days,
                    max_size_gb=config.retention_max_db_size_gb,
                    run_vacuum=True,
                )
            await asyncio.sleep(args.online_interval)

    asyncio.run(loop())


# --- Как проверить: python -m ml_service.run_loop --train-once при наличии данных в БД.
# --- Частые ошибки: запускать в одном процессе с торговлей (нагрузка); не проверять гейт перед активацией модели.
# --- Что улучшить позже: расписание обучения (cron); расчёт y по fills и horizon_seconds; запись summary в БД.

if __name__ == "__main__":
    main()

# --- Как проверить: python -m ml_service.run_loop --train-once при наличии metrics_1s в БД; проверить data/models и model_registry.
# --- Частые ошибки: запускать в одном процессе с торговлей; не задать PYTHONPATH/запуск не из корня — импорт src.botik падает.
# --- Что улучшить позже: расчёт метки y по fills и horizon_seconds; использование активной модели в торговом цикле как фильтра.
