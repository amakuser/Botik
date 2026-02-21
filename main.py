# -*- coding: utf-8 -*-
"""
Точка входа торгового бота (Python 3.10+).

Загружает конфиг, создаёт реестр стратегий, OrderManager и Executor (sync/async),
подключает WebSocket Bybit и запускает основной цикл. Остановка: Ctrl+C.
"""
import logging
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH для импортов
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_config, get_daily_limits, get_bybit_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("main")


def main() -> None:
    """Загрузка конфига, инициализация компонентов, запуск executor."""
    config = load_config()
    limits = get_daily_limits(config)
    bybit_settings = get_bybit_settings(config)
    mode = config.get("execution_mode", "sync")  # "sync" или "async"
    dry_run = config.get("dry_run", True)  # True = без реальных ордеров (paper trading)

    log.info("Config loaded. execution_mode=%s dry_run=%s", mode, dry_run)
    log.info("Daily limits: %s", limits)

    # Реестр стратегий: имя -> класс (добавление новых стратегий без правок ядра)
    from core.registry import StrategyRegistry
    from core.order_manager import OrderManager
    from core.executor import get_executor

    registry = StrategyRegistry()
    from strategies.ma_strategy import MAStrategy
    registry.register("MAStrategy", MAStrategy)

    # Создаём экземпляры стратегий из конфига (символ, таймфрейм, параметры)
    strategies_config = config.get("strategies", [])
    strategy_instances = []
    for sc in strategies_config:
        name = sc.get("name")
        if not name or name not in registry:
            log.warning("Unknown strategy: %s", name)
            continue
        cls = registry.get(name)
        instance = cls(
            symbol=sc.get("symbol", "BTCUSDT"),
            timeframe=sc.get("timeframe", "15"),
            params=sc.get("params") or {},
        )
        strategy_instances.append(instance)

    # База статистики (сделки, дневные лимиты, ML)
    db_path = (config.get("stats") or {}).get("db_path", "data/stats.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    order_manager = OrderManager(
        config=config,
        daily_limits=limits,
        bybit_settings=bybit_settings,
        db_path=db_path,
        dry_run=dry_run,
    )

    # Выбор однопоточного (sync) или асинхронного (async) исполнения
    executor = get_executor(
        mode=mode,
        strategies=strategy_instances,
        order_manager=order_manager,
        config=config,
    )

    # Клиент Bybit: REST + WebSocket в отдельном потоке
    from core.bybit_client import BybitClient
    client = BybitClient(**bybit_settings)
    order_manager.set_client(client)

    # Подписка на тикеры и свечи по символам/таймфреймам стратегий
    symbols = list({s.symbol for s in strategy_instances}) or ["BTCUSDT"]
    timeframes = list({s.timeframe for s in strategy_instances}) or ["15"]
    if hasattr(executor, "feed"):  # SyncExecutor поддерживает feed / feed_klines
        def on_klines(sym: str, interval: str, lst: list) -> None:
            if hasattr(executor, "feed_klines"):
                executor.feed_klines(sym, interval, lst)
        client.start_ws(
            symbols=symbols,
            timeframes=timeframes,
            on_ticker=executor.feed,
            on_klines=on_klines,
        )

    try:
        executor.run()  # Блокирующий цикл до остановки
    except KeyboardInterrupt:
        log.info("Stopping...")
    finally:
        executor.stop()
        client.stop_ws()


if __name__ == "__main__":
    main()
