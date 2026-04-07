"""
ModelRegistry — сохранение, загрузка и версионирование моделей.

Хранит веса в data/models/*.joblib (joblib быстрее и безопаснее для sklearn).
Версии и метрики пишет в ml_training_runs (БД).
При загрузке берёт последнюю версию с is_trained=True.

Структура файлов:
  data/models/futures_historian_v3.joblib
  data/models/futures_predictor_v3.joblib
  data/models/futures_outcome_v1.joblib
  data/models/checkpoints/futures_historian_step_1000.joblib
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("botik.ml.registry")

MODELS_DIR = Path(__file__).resolve().parents[4] / "data" / "models"
CHECKPOINTS_DIR = MODELS_DIR / "checkpoints"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _model_path(scope: str, name: str, version: int) -> Path:
    return MODELS_DIR / f"{scope}_{name}_v{version}.joblib"


def _checkpoint_path(scope: str, name: str, step: int) -> Path:
    return CHECKPOINTS_DIR / f"{scope}_{name}_step_{step}.joblib"


class ModelRegistry:
    """
    Управляет версиями моделей на диске и в БД.

    Использование:
      registry = ModelRegistry()
      registry.save(model, run_id, version=2)
      model = registry.load(Historian, scope='futures', name='historian')
    """

    def __init__(self) -> None:
        pass

    # ── Сохранение ────────────────────────────────────────────

    def save(
        self,
        model_obj: Any,         # sklearn объект
        scope: str,
        name: str,
        version: int,
        accuracy: float,
        trade_count: int,
        run_id: str | None = None,
        is_trained: bool = False,
        extra: dict | None = None,
    ) -> Path:
        """Сохраняет модель на диск и обновляет БД."""
        try:
            import joblib
        except ImportError:
            log.error("joblib не установлен: pip install joblib")
            raise

        path = _model_path(scope, name, version)
        payload = {
            "model": model_obj,
            "accuracy": accuracy,
            "trade_count": trade_count,
            "scope": scope,
            "name": name,
            "version": version,
            "saved_at": _utc_now(),
        }
        if extra:
            payload["extra"] = extra

        joblib.dump(payload, path)
        log.info("Saved model %s/%s v%d → %s (acc=%.3f)", scope, name, version, path, accuracy)

        self._write_db(
            run_id=run_id or str(uuid.uuid4()),
            scope=scope,
            name=name,
            version=version,
            accuracy=accuracy,
            trade_count=trade_count,
            is_trained=is_trained,
        )
        return path

    def save_checkpoint(
        self,
        model_obj: Any,
        scope: str,
        name: str,
        step: int,
    ) -> Path:
        """Сохраняет checkpoint (промежуточное состояние при heavy bootstrap)."""
        try:
            import joblib
        except ImportError:
            return Path()
        path = _checkpoint_path(scope, name, step)
        joblib.dump({"model": model_obj, "step": step, "ts": _utc_now()}, path)
        log.debug("Checkpoint %s/%s step=%d", scope, name, step)
        return path

    # ── Загрузка ──────────────────────────────────────────────

    def load(
        self,
        scope: str,
        name: str,
    ) -> tuple[Any, float, int] | None:
        """
        Загружает последнюю версию модели с is_trained=True.
        Возвращает (model_obj, accuracy, trade_count) или None.
        """
        version = self._get_latest_version(scope, name)
        if version is None:
            log.info("Нет обученной модели %s/%s в БД", scope, name)
            return None

        path = _model_path(scope, name, version)
        if not path.exists():
            log.warning("Файл модели не найден: %s", path)
            return None

        try:
            import joblib
            payload = joblib.load(path)
            model_obj = payload["model"]
            accuracy  = float(payload.get("accuracy", 0.0))
            tc        = int(payload.get("trade_count", 0))
            log.info("Loaded model %s/%s v%d (acc=%.3f)", scope, name, version, accuracy)
            return model_obj, accuracy, tc
        except Exception as exc:
            log.error("Ошибка загрузки модели %s/%s: %s", scope, name, exc)
            return None

    def load_checkpoint(self, scope: str, name: str) -> tuple[Any, int] | None:
        """Загружает последний checkpoint для возобновления bootstrap."""
        checkpoints = sorted(CHECKPOINTS_DIR.glob(f"{scope}_{name}_step_*.joblib"))
        if not checkpoints:
            return None
        latest = checkpoints[-1]
        try:
            import joblib
            payload = joblib.load(latest)
            log.info("Resume checkpoint %s step=%d", name, payload.get("step", 0))
            return payload["model"], int(payload.get("step", 0))
        except Exception:
            return None

    def get_version(self, scope: str, name: str) -> int:
        v = self._get_latest_version(scope, name)
        return v or 0

    def next_version(self, scope: str, name: str) -> int:
        return self.get_version(scope, name) + 1

    # ── DB ────────────────────────────────────────────────────

    def _write_db(
        self,
        run_id: str,
        scope: str,
        name: str,
        version: int,
        accuracy: float,
        trade_count: int,
        is_trained: bool,
    ) -> None:
        try:
            from src.botik.storage.db import get_db
            db = get_db()
            now = _utc_now()
            model_version = f"v{version}"
            with db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO ml_training_runs
                      (run_id, model_scope, model_version, mode, status,
                       accuracy, trade_count, is_trained,
                       trained_at_utc, started_at_utc, finished_at_utc)
                    VALUES (?, ?, ?, 'train', 'completed', ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                      accuracy=excluded.accuracy,
                      trade_count=excluded.trade_count,
                      is_trained=excluded.is_trained,
                      finished_at_utc=excluded.finished_at_utc
                    """,
                    (run_id, scope, model_version, accuracy, trade_count,
                     1 if is_trained else 0, now, now, now),
                )
                # Добавляем запись в model_stats (append-only лог)
                conn.execute(
                    """
                    INSERT INTO model_stats
                      (model_id, model_scope,
                       accuracy, trade_count, status, created_at_utc)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (f"{scope}_{name}_{model_version}", scope,
                     accuracy, trade_count,
                     "active" if is_trained else "training", now),
                )
        except Exception as exc:
            log.warning("registry._write_db: %s", exc)

    def _get_latest_version(self, scope: str, name: str) -> int | None:
        # Сначала ищем файл на диске (самый надёжный источник)
        files = sorted(MODELS_DIR.glob(f"{scope}_{name}_v*.joblib"))
        if files:
            v_str = files[-1].stem.split("_v")[-1]
            if v_str.isdigit():
                return int(v_str)
        # Fallback: ищем в БД (model_version хранится как "v1", "v2", ...)
        try:
            from src.botik.storage.db import get_db
            db = get_db()
            with db.connect() as conn:
                row = conn.execute(
                    """
                    SELECT model_version FROM ml_training_runs
                    WHERE model_scope=? AND is_trained=1
                    ORDER BY finished_at_utc DESC LIMIT 1
                    """,
                    (scope,),
                ).fetchone()
            if row:
                v_str = str(row[0]).lstrip("v")
                return int(v_str) if v_str.isdigit() else None
        except Exception:
            pass
        return None
