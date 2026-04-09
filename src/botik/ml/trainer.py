"""
ModelTrainer — управляет обучением всех трёх моделей.

Режимы:
  bootstrap   — первый запуск, обрабатывает ВСЮ историю
                использует ~50% CPU, сохраняет checkpoint каждые 1000 шагов
                можно прерывать и продолжать

  incremental — быстрое дообучение на новых данных (N сделок)
                запускается автоматически каждые 50 закрытых сделок

  evaluate    — валидация без сохранения, сравнение версий

Запуск bootstrap:
  python -m src.botik.ml.trainer --mode bootstrap --scope futures

Запуск incremental:
  python -m src.botik.ml.trainer --mode incremental --scope futures
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np

from src.botik.ml.historian import Historian
from src.botik.ml.predictor import Predictor
from src.botik.ml.outcome_learner import OutcomeLearner
from src.botik.ml.labeler import Labeler
from src.botik.ml.registry import ModelRegistry

log = logging.getLogger("botik.ml.trainer")

BOOTSTRAP_SYMBOLS_DEFAULT = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
CHECKPOINT_EVERY = 1000    # шаг checkpoint при bootstrap
MIN_ACCURACY_TO_DEPLOY = 0.52


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_app_log(msg: str, channel: str = "ml") -> None:
    try:
        from src.botik.storage.db import get_db
        db = get_db()
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO app_logs (channel, level, message, created_at_utc) "
                "VALUES (?, 'INFO', ?, ?)",
                (channel, msg, _utc_now()),
            )
    except Exception:
        pass


class ModelTrainer:
    """
    Координирует обучение Historian + Predictor + OutcomeLearner.

    Жизненный цикл:
      1. bootstrap() — собираем всё из price_history, labeler генерирует метки
      2. fit_all()   — обучаем historian + predictor
      3. evaluate()  — проверяем accuracy
      4. deploy()    — если accuracy ок → сохраняем в registry + is_trained=True
      5. incremental() — вызывается автоматически при накоплении новых сделок
    """

    def __init__(self, model_scope: str = "futures") -> None:
        self.model_scope = model_scope
        self.registry = ModelRegistry()
        self.labeler = Labeler(model_scope=model_scope)
        self.historian = Historian(model_scope=model_scope)
        self.predictor = Predictor(model_scope=model_scope)
        self.outcome_learner = OutcomeLearner(model_scope=model_scope)
        self._run_id = str(uuid.uuid4())

        # Загружаем существующие модели если есть
        self._try_load_models()

    # ── Публичный API ─────────────────────────────────────────

    def bootstrap(
        self,
        symbols: list[str] | None = None,
        interval: str = "1",
        limit_per_symbol: int = 40000,
    ) -> dict[str, Any]:
        """
        Первый запуск: размечаем историю, обучаем все модели.
        Может занять минуты-часы в зависимости от объёма данных.
        """
        syms = symbols or BOOTSTRAP_SYMBOLS_DEFAULT
        log.info("Bootstrap start: scope=%s symbols=%s", self.model_scope, syms)
        _write_app_log(f"Bootstrap start: {syms}")

        start_ts = time.monotonic()

        # Шаг 1: генерируем labeled_samples из price_history
        total_samples = 0
        for sym in syms:
            n = self.labeler.run(sym, interval=interval, limit=limit_per_symbol)
            total_samples += n
            log.info("Labeled %s: %d samples", sym, n)
            _write_app_log(f"Labeled {sym}: {n} samples")

        if total_samples < self.historian.min_trades:
            msg = f"Bootstrap: недостаточно данных ({total_samples} образцов). Соберите больше OHLCV."
            log.warning(msg)
            _write_app_log(f"WARNING: {msg}")
            return {"ok": False, "reason": msg, "samples": total_samples}

        # Шаг 2: загружаем датасет
        X, y, weights = self.labeler.load_dataset(limit=50000)
        log.info("Dataset: %d samples, %d positive", len(X), int(np.sum(y)))

        if len(X) < self.historian.min_trades:
            return {"ok": False, "reason": "dataset too small", "samples": len(X)}

        # Шаг 3: обучаем Historian
        log.info("Training Historian...")
        _write_app_log("Training Historian...")
        h_result = self.historian.fit(X, y, sample_weight=weights)
        log.info("Historian: accuracy=%.3f", h_result.accuracy)

        # Шаг 4: обучаем Predictor
        log.info("Training Predictor...")
        _write_app_log("Training Predictor...")
        p_result = self.predictor.fit(X, y, sample_weight=weights)
        log.info("Predictor: accuracy=%.3f", p_result.accuracy)

        # Шаг 5: оцениваем и деплоим
        elapsed = round(time.monotonic() - start_ts, 1)
        results = self._maybe_deploy(h_result, p_result, mode="bootstrap")
        results["elapsed_sec"] = elapsed
        results["samples"] = len(X)

        _write_app_log(
            f"Bootstrap done: samples={len(X)} "
            f"historian_acc={h_result.accuracy:.3f} "
            f"predictor_acc={p_result.accuracy:.3f} "
            f"deployed={results.get('deployed', False)} "
            f"elapsed={elapsed}s"
        )
        return results

    def incremental(self) -> dict[str, Any]:
        """
        Дообучение на новых данных. Быстро (секунды-минуты).
        Вызывается автоматически при накоплении новых сделок.
        """
        log.info("Incremental training: scope=%s", self.model_scope)

        X, y, weights = self.labeler.load_dataset(limit=5000)
        if len(X) < self.predictor.min_trades:
            return {"ok": False, "reason": "not enough data"}

        h_result = self.historian.fit(X, y, sample_weight=weights)
        p_result = self.predictor.fit(X, y, sample_weight=weights)

        # OutcomeLearner обновляет пороги
        self.outcome_learner.load_from_db()
        new_threshold = self.outcome_learner.suggest_threshold(self.predictor.entry_threshold)
        if new_threshold != self.predictor.entry_threshold:
            log.info("Threshold updated: %.2f → %.2f", self.predictor.entry_threshold, new_threshold)
            self.predictor.entry_threshold = new_threshold

        results = self._maybe_deploy(h_result, p_result, mode="incremental")
        _write_app_log(
            f"Incremental: samples={len(X)} "
            f"historian_acc={h_result.accuracy:.3f} "
            f"predictor_acc={p_result.accuracy:.3f} "
            f"threshold={self.predictor.entry_threshold:.2f}"
        )
        return results

    def get_predict_fn(self):
        """
        Возвращает функцию предсказания для FuturesSpikeReversalStrategy.

        Комбинирует Historian.predict() + Predictor.predict().
        Если модели не обучены → возвращает None (стратегия работает по правилам).
        """
        if not self.predictor.is_ready():
            return None

        historian = self.historian
        predictor = self.predictor

        def predict_fn(features: "np.ndarray") -> float:
            pattern_score = historian.predict(features)
            return predictor.predict(features) * 0.7 + pattern_score * 0.3

        return predict_fn

    # ── Internal ──────────────────────────────────────────────

    def _maybe_deploy(
        self,
        h_result: Any,
        p_result: Any,
        mode: str,
    ) -> dict[str, Any]:
        """Сохраняет модели если accuracy достаточна."""
        h_ok = h_result.accuracy >= MIN_ACCURACY_TO_DEPLOY
        p_ok = p_result.accuracy >= MIN_ACCURACY_TO_DEPLOY
        deploy = h_ok and p_ok

        if deploy:
            scope = self.model_scope
            v = self.registry.next_version(scope, "historian")

            self.registry.save(
                model_obj=self.historian.get_model_object(),
                scope=scope, name="historian", version=v,
                accuracy=h_result.accuracy,
                trade_count=h_result.trade_count,
                is_trained=True,
            )
            self.registry.save(
                model_obj=self.predictor.get_model_object(),
                scope=scope, name="predictor", version=v,
                accuracy=p_result.accuracy,
                trade_count=p_result.trade_count,
                is_trained=True,
            )
            log.info("Models deployed: %s v%d (hist=%.3f pred=%.3f)",
                     scope, v, h_result.accuracy, p_result.accuracy)
        else:
            log.info("Deploy skipped: hist_acc=%.3f pred_acc=%.3f (min=%.2f)",
                     h_result.accuracy, p_result.accuracy, MIN_ACCURACY_TO_DEPLOY)

        return {
            "ok": True,
            "deployed": deploy,
            "historian_accuracy": h_result.accuracy,
            "predictor_accuracy": p_result.accuracy,
            "mode": mode,
        }

    def _try_load_models(self) -> None:
        """Пытается загрузить существующие модели из registry."""
        scope = self.model_scope

        h = self.registry.load(scope, "historian")
        if h:
            self.historian.set_model_object(*h)
            log.info("Historian loaded (acc=%.3f, trades=%d)", h[1], h[2])

        p = self.registry.load(scope, "predictor")
        if p:
            self.predictor.set_model_object(*p)
            log.info("Predictor loaded (acc=%.3f, trades=%d)", p[1], p[2])

        self.outcome_learner.load_from_db()


# ── CLI entry point ───────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path

    _ROOT = Path(__file__).resolve().parents[4]
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))

    from src.botik.storage.schema import bootstrap_db

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Botik ML Trainer")
    parser.add_argument("--mode", choices=["bootstrap", "incremental"], default="bootstrap")
    parser.add_argument("--scope", choices=["futures", "spot"], default="futures")
    parser.add_argument("--symbols", default="")
    args = parser.parse_args()

    bootstrap_db()
    trainer = ModelTrainer(model_scope=args.scope)

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()] or None

    if args.mode == "bootstrap":
        result = trainer.bootstrap(symbols=symbols)
    else:
        result = trainer.incremental()

    print(result)
