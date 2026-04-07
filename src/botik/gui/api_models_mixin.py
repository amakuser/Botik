"""
ModelsMixin — model registry reading and get_models() public API.

Depends on: DbMixin (via MRO), api_helpers constants.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .api_helpers import ACTIVE_MODELS_PATH


class ModelsMixin:
    """Mixin providing ML model reading methods to DashboardAPI."""

    # ── Manifest ──────────────────────────────────────────────

    def _read_active_models_pointer(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "manifest_status": "missing",
            "manifest_path": str(ACTIVE_MODELS_PATH),
            "loaded_at": "-",
            "active_spot_model": "unknown",
            "active_futures_model": "unknown",
            "spot_checkpoint_path": "",
            "futures_checkpoint_path": "",
        }
        if not ACTIVE_MODELS_PATH.exists():
            return out
        try:
            raw = yaml.safe_load(ACTIVE_MODELS_PATH.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                out["manifest_status"] = "failed"
                return out
            out["active_spot_model"]      = str(raw.get("active_spot_model") or "unknown").strip() or "unknown"
            out["active_futures_model"]   = str(raw.get("active_futures_model") or "unknown").strip() or "unknown"
            out["spot_checkpoint_path"]   = str(raw.get("spot_checkpoint_path") or "").strip()
            out["futures_checkpoint_path"] = str(raw.get("futures_checkpoint_path") or "").strip()
            out["loaded_at"] = datetime.fromtimestamp(
                float(ACTIVE_MODELS_PATH.stat().st_mtime)
            ).strftime("%Y-%m-%d %H:%M:%S")
            out["manifest_status"] = "loaded"
            return out
        except Exception as exc:
            out["manifest_status"] = "failed"
            out["error"] = str(exc)
            return out

    # ── Training runs ─────────────────────────────────────────

    def _read_training_runs(self, conn: sqlite3.Connection, limit: int = 12) -> list[dict[str, Any]]:
        try:
            if not self._table_exists(conn, "ml_training_runs"):  # type: ignore[attr-defined]
                return []
            columns = self._table_columns(conn, "ml_training_runs")  # type: ignore[attr-defined]
            select_sql = ", ".join([
                self._column_expr(columns, ("run_id",), "run_id", default_sql="''"),
                self._column_expr(columns, ("model_scope",), "model_scope", default_sql="''"),
                self._column_expr(columns, ("model_version",), "model_version", default_sql="''"),
                self._column_expr(columns, ("mode",), "mode", default_sql="''"),
                self._column_expr(columns, ("status",), "status", default_sql="''"),
                self._column_expr(columns, ("epoch",), "epoch"),
                self._column_expr(columns, ("max_epochs",), "max_epochs"),
                self._column_expr(columns, ("loss",), "loss"),
                self._column_expr(columns, ("accuracy",), "accuracy"),
                self._column_expr(columns, ("sharpe_ratio",), "sharpe_ratio"),
                self._column_expr(columns, ("trade_count",), "trade_count"),
                self._column_expr(columns, ("is_trained",), "is_trained", default_sql="0"),
                self._column_expr(columns, ("trained_at_utc",), "trained_at_utc", default_sql="''"),
                self._column_expr(columns, ("started_at_utc",), "started_at_utc", default_sql="''"),
                self._column_expr(columns, ("finished_at_utc",), "finished_at_utc", default_sql="''"),
                self._column_expr(columns, ("notes",), "notes", default_sql="''"),
            ])
            order_parts: list[str] = []
            for col in ("started_at_utc", "finished_at_utc", "trained_at_utc"):
                if col in columns:
                    order_parts.append(f"COALESCE({col}, '') DESC")
            if "run_id" in columns:
                order_parts.append("run_id DESC")
            order_sql = ", ".join(order_parts) if order_parts else "1 DESC"
            rows = conn.execute(
                f"SELECT {select_sql} FROM ml_training_runs ORDER BY {order_sql} LIMIT ?",
                (max(int(limit), 1),),
            ).fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                payload = dict(row)
                payload["model_scope"] = self._normalize_model_scope(  # type: ignore[attr-defined]
                    payload.get("model_scope"), payload.get("model_version"),
                )
                payload["is_trained"] = bool(self._safe_int(payload.get("is_trained")) or 0)  # type: ignore[attr-defined]
                out.append(payload)
            return out
        except Exception:
            return []

    # ── Model stats ───────────────────────────────────────────

    def _read_model_stats_rows(self, conn: sqlite3.Connection, limit: int = 64) -> list[dict[str, Any]]:
        try:
            if not self._table_exists(conn, "model_stats"):  # type: ignore[attr-defined]
                return []
            columns = self._table_columns(conn, "model_stats")  # type: ignore[attr-defined]
            select_sql = ", ".join([
                self._column_expr(columns, ("model_id", "model_name"), "model_id", default_sql="''"),
                self._column_expr(columns, ("model_scope",), "model_scope", default_sql="''"),
                self._column_expr(columns, ("accuracy",), "accuracy"),
                self._column_expr(columns, ("sharpe_ratio",), "sharpe_ratio"),
                self._column_expr(columns, ("trade_count",), "trade_count"),
                self._column_expr(columns, ("status",), "status", default_sql="''"),
                self._column_expr(columns, ("created_at_utc",), "created_at_utc", default_sql="''"),
                self._column_expr(columns, ("ts_ms",), "ts_ms"),
                self._column_expr(columns, ("win_rate",), "win_rate"),
                self._column_expr(columns, ("fill_rate",), "fill_rate"),
                self._column_expr(columns, ("net_edge_mean",), "net_edge_mean"),
            ])
            order_parts: list[str] = []
            if "ts_ms" in columns:
                order_parts.append("COALESCE(ts_ms, 0) DESC")
            if "created_at_utc" in columns:
                order_parts.append("COALESCE(created_at_utc, '') DESC")
            id_col = self._first_existing_column(columns, "model_id", "model_name")  # type: ignore[attr-defined]
            if id_col:
                order_parts.append(f"{id_col} DESC")
            order_sql = ", ".join(order_parts) if order_parts else "1 DESC"
            rows = conn.execute(
                f"SELECT {select_sql} FROM model_stats ORDER BY {order_sql} LIMIT ?",
                (max(int(limit), 1),),
            ).fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                payload = dict(row)
                payload["model_scope"] = self._normalize_model_scope(  # type: ignore[attr-defined]
                    payload.get("model_scope"), payload.get("model_id"),
                )
                out.append(payload)
            return out
        except Exception:
            return []

    # ── Card builder ──────────────────────────────────────────

    def _build_model_scope_card(
        self,
        scope: str,
        pointer: dict[str, Any],
        training_runs: list[dict[str, Any]],
        stats_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        is_spot = scope == "spot"
        active_key     = "active_spot_model"     if is_spot else "active_futures_model"
        checkpoint_key = "spot_checkpoint_path"  if is_spot else "futures_checkpoint_path"

        active_model    = str(pointer.get(active_key) or "unknown").strip() or "unknown"
        checkpoint_path = str(pointer.get(checkpoint_key) or "").strip()
        checkpoint_name = Path(checkpoint_path).name if checkpoint_path else ""
        has_active_model = active_model.lower() not in {"", "unknown", "none", "null"}

        scope_runs = [
            r for r in training_runs
            if self._normalize_model_scope(r.get("model_scope"), r.get("model_version")) == scope  # type: ignore[attr-defined]
        ]
        latest_run = scope_runs[0] if scope_runs else {}

        scope_stats = [
            r for r in stats_rows
            if self._normalize_model_scope(r.get("model_scope"), r.get("model_id")) == scope  # type: ignore[attr-defined]
        ]
        selected_stats = None
        if has_active_model:
            selected_stats = next(
                (r for r in scope_stats if self._model_ids_match(active_model, r.get("model_id"))),  # type: ignore[attr-defined]
                None,
            )
        if selected_stats is None:
            selected_stats = next(
                (r for r in scope_stats if str(r.get("status") or "").strip().lower()
                 in {"active", "ready", "trained", "completed"}),
                None,
            )
        if selected_stats is None and scope_stats:
            selected_stats = scope_stats[0]

        run_status  = str(latest_run.get("status") or "").strip().lower()
        run_mode    = str(latest_run.get("mode") or "").strip().lower()
        stats_status = str((selected_stats or {}).get("status") or "").strip().lower()
        trained_ready = bool(latest_run.get("is_trained")) or stats_status in {
            "active", "ready", "trained", "completed",
        }

        if has_active_model and trained_ready:
            state = "active"
        elif trained_ready:
            state = "ready"
        elif run_status in {"running", "training", "in_progress", "pending", "started"}:
            state = "training"
        elif run_mode == "bootstrap" or checkpoint_path:
            state = "bootstrap"
        elif has_active_model:
            state = "idle"
        else:
            state = "missing"

        state_map = {
            "active":   ("tag-active",  "ACTIVE"),
            "ready":    ("tag-active",  "READY"),
            "training": ("tag-loading", "TRAINING"),
            "bootstrap":("tag-loading", "BOOTSTRAP"),
            "idle":     ("tag-idle",    "IDLE"),
            "missing":  ("tag-risk",    "MISSING"),
        }
        tag_class, tag_text = state_map.get(state, ("tag-idle", "IDLE"))

        epoch      = self._safe_int(latest_run.get("epoch"))       # type: ignore[attr-defined]
        max_epochs = self._safe_int(latest_run.get("max_epochs"))  # type: ignore[attr-defined]
        if epoch is not None and max_epochs and max_epochs > 0:
            progress_pct   = max(4, min(100, int(round(epoch * 100 / max_epochs))))
            progress_label = "Прогресс обучения"
        elif state in {"active", "ready"}:
            progress_pct   = 100
            progress_label = "Готовность"
        elif state == "training":
            progress_pct   = 60
            progress_label = "Прогресс обучения"
        elif state == "bootstrap":
            progress_pct   = 35 if checkpoint_path else 20
            progress_label = "Bootstrap"
        elif has_active_model:
            progress_pct   = 15
            progress_label = "Ожидание проверки"
        else:
            progress_pct   = 0
            progress_label = "Нет данных"

        accuracy    = self._safe_float((selected_stats or {}).get("accuracy"))    # type: ignore[attr-defined]
        sharpe      = self._safe_float((selected_stats or {}).get("sharpe_ratio"))# type: ignore[attr-defined]
        trade_count = self._safe_int((selected_stats or {}).get("trade_count"))   # type: ignore[attr-defined]
        win_rate    = self._safe_float((selected_stats or {}).get("win_rate"))     # type: ignore[attr-defined]
        fill_rate   = self._safe_float((selected_stats or {}).get("fill_rate"))    # type: ignore[attr-defined]
        net_edge    = self._safe_float((selected_stats or {}).get("net_edge_mean"))# type: ignore[attr-defined]

        updated_at = str(
            latest_run.get("finished_at_utc")
            or latest_run.get("trained_at_utc")
            or latest_run.get("started_at_utc")
            or (selected_stats or {}).get("created_at_utc")
            or "—"
        )

        return {
            "scope":            scope,
            "scope_label":      "Спот" if is_spot else "Фьючерсы",
            "active_model":     active_model,
            "has_active_model": has_active_model,
            "checkpoint_name":  checkpoint_name,
            "state":            state,
            "tag_class":        tag_class,
            "tag_text":         tag_text,
            "accuracy":         accuracy,
            "sharpe_ratio":     sharpe,
            "trade_count":      trade_count,
            "win_rate":         win_rate,
            "fill_rate":        fill_rate,
            "net_edge_mean":    net_edge,
            "updated_at":       updated_at,
            "progress_pct":     progress_pct,
            "progress_label":   progress_label,
            "latest_notes":     str(latest_run.get("notes") or ""),
        }

    # ── Payload builder ───────────────────────────────────────

    def _build_models_payload(self, conn: sqlite3.Connection | None) -> dict[str, Any]:
        pointer       = self._read_active_models_pointer()
        training_runs = self._read_training_runs(conn, limit=16) if conn else []
        stats_rows    = self._read_model_stats_rows(conn, limit=64) if conn else []

        cards = [
            self._build_model_scope_card("spot",    pointer, training_runs, stats_rows),
            self._build_model_scope_card("futures", pointer, training_runs, stats_rows),
        ]

        ready_scopes         = sum(1 for c in cards if c.get("state") in {"active", "ready"})
        active_declared_count = sum(1 for c in cards if c.get("has_active_model"))
        latest_run           = training_runs[0] if training_runs else {}
        latest_run_scope     = self._normalize_model_scope(  # type: ignore[attr-defined]
            latest_run.get("model_scope"), latest_run.get("model_version"),
        ) if latest_run else ""

        recent_runs: list[dict[str, Any]] = []
        for row in training_runs:
            recent_runs.append({
                "scope":        self._normalize_model_scope(row.get("model_scope"), row.get("model_version")),  # type: ignore[attr-defined]
                "version":      str(row.get("model_version") or "—"),
                "mode":         str(row.get("mode") or "—"),
                "status":       str(row.get("status") or "—"),
                "epoch":        self._safe_int(row.get("epoch")),    # type: ignore[attr-defined]
                "max_epochs":   self._safe_int(row.get("max_epochs")),# type: ignore[attr-defined]
                "accuracy":     self._safe_float(row.get("accuracy")),# type: ignore[attr-defined]
                "sharpe_ratio": self._safe_float(row.get("sharpe_ratio")),# type: ignore[attr-defined]
                "trade_count":  self._safe_int(row.get("trade_count")),# type: ignore[attr-defined]
                "is_trained":   bool(row.get("is_trained")),
                "updated_at":   str(
                    row.get("finished_at_utc")
                    or row.get("trained_at_utc")
                    or row.get("started_at_utc")
                    or "—"
                ),
            })

        has_training_table = bool(conn and self._table_exists(conn, "ml_training_runs"))  # type: ignore[attr-defined]
        has_stats_table    = bool(conn and self._table_exists(conn, "model_stats"))        # type: ignore[attr-defined]
        sources = [
            {
                "name":   "active_models.yaml",
                "status": str(pointer.get("manifest_status") or "missing"),
                "detail": str(pointer.get("loaded_at") or "-"),
            },
            {
                "name":   "ml_training_runs",
                "status": "ok" if recent_runs else ("empty" if has_training_table else "missing"),
                "detail": f"rows={len(recent_runs)}",
            },
            {
                "name":   "model_stats",
                "status": "ok" if stats_rows else ("empty" if has_stats_table else "missing"),
                "detail": f"rows={len(stats_rows)}",
            },
        ]

        notes: list[str] = []
        if str(pointer.get("manifest_status") or "") == "missing":
            notes.append("Не найден `active_models.yaml`; активные модели не объявлены.")
        if conn is None:
            notes.append("База данных недоступна; показан только статус manifest-файла.")
        elif not recent_runs and not stats_rows:
            notes.append("В БД пока нет истории `ml_training_runs` и `model_stats`.")

        return {
            "summary": {
                "ready_scopes":           ready_scopes,
                "total_scopes":           len(cards),
                "active_declared_count":  active_declared_count,
                "training_runtime_state": self._ml_process.state,       # type: ignore[attr-defined]
                "latest_run_scope":       latest_run_scope,
                "latest_run_status":      str(latest_run.get("status") or ""),
                "latest_run_mode":        str(latest_run.get("mode") or ""),
                "manifest_status":        str(pointer.get("manifest_status") or "missing"),
                "manifest_loaded_at":     str(pointer.get("loaded_at") or "-"),
                "db_available":           conn is not None,
            },
            "cards":       cards,
            "recent_runs": recent_runs,
            "sources":     sources,
            "notes":       notes,
            "ml_training": self._read_ml_training_status(conn) if conn else {},
        }

    # ── ML training status (compact) ─────────────────────────

    def _read_ml_training_status(self, conn: sqlite3.Connection) -> dict[str, Any]:
        runs = self._read_training_runs(conn, limit=1)
        if runs:
            row = runs[0]
            return {
                "scope":      row.get("model_scope"),
                "mode":       row.get("mode"),
                "status":     row.get("status"),
                "epoch":      self._safe_int(row.get("epoch")),   # type: ignore[attr-defined]
                "max_epochs": self._safe_int(row.get("max_epochs")),# type: ignore[attr-defined]
                "loss":       self._safe_float(row.get("loss")),  # type: ignore[attr-defined]
                "accuracy":   self._safe_float(row.get("accuracy")),# type: ignore[attr-defined]
                "ts":         row.get("finished_at_utc") or row.get("trained_at_utc") or row.get("started_at_utc"),
            }
        stats_rows = self._read_model_stats_rows(conn, limit=1)
        if stats_rows:
            row = stats_rows[0]
            return {
                "scope":      row.get("model_scope"),
                "mode":       "registry",
                "status":     row.get("status"),
                "epoch":      None,
                "max_epochs": None,
                "loss":       None,
                "accuracy":   self._safe_float(row.get("accuracy")),# type: ignore[attr-defined]
                "ts":         row.get("created_at_utc"),
            }
        return {}

    # ── Per-model cards (M5) ──────────────────────────────────

    #: Static description for each model type
    _MODEL_DESCRIPTIONS: dict[str, str] = {
        "historian":  "Паттерны price_history — когда входить в позицию",
        "predictor":  "Вероятность направления движения цены",
        "outcome":    "OutcomeLearner — адаптирует пороги по реальным сделкам",
    }

    #: Russian display labels for model names
    _MODEL_LABELS: dict[str, str] = {
        "historian": "Историк",
        "predictor": "Предиктор",
        "outcome":   "Outcome-обучение",
    }

    def _build_per_model_card(
        self,
        scope: str,
        name: str,
        scope_runs: list[dict],
    ) -> dict:
        """
        Build one card dict for a (scope, name) model combination.

        Checks model files on disk and latest training run accuracy.
        """
        from src.botik.ml.registry import MODELS_DIR

        # ── Disk presence ──
        files = sorted(MODELS_DIR.glob(f"{scope}_{name}_v*.joblib"))
        has_file    = bool(files)
        latest_file = files[-1].name if files else ""
        version_str = ("v" + files[-1].stem.rsplit("v", 1)[-1]) if files else "—"

        # ── Latest training accuracy (per scope; outcome has no run) ──
        latest_run = scope_runs[0] if scope_runs else {}
        accuracy   = (
            self._safe_float(latest_run.get("accuracy"))  # type: ignore[attr-defined]
            if name != "outcome" else None
        )
        is_trained = bool(latest_run.get("is_trained")) if name != "outcome" else has_file
        updated_at = str(
            latest_run.get("finished_at_utc")
            or latest_run.get("trained_at_utc")
            or "—"
        )

        # Determine card state
        run_status = str(latest_run.get("status") or "").strip().lower()

        if name == "outcome":
            # OutcomeLearner has no training_runs; file presence = learned from trades
            state = "active" if has_file else "missing"
        elif has_file and is_trained:
            state = "active"
        elif has_file:
            state = "ready"
        elif run_status in {"running", "training", "in_progress", "pending", "started"}:
            state = "training"
        elif scope_runs:
            state = "idle"
        else:
            state = "missing"

        state_map = {
            "active":   ("tag-active",  "ACTIVE"),
            "ready":    ("tag-active",  "READY"),
            "training": ("tag-loading", "TRAINING"),
            "idle":     ("tag-idle",    "NO FILE"),
            "missing":  ("tag-risk",    "MISSING"),
        }
        tag_class, tag_text = state_map[state]

        return {
            "scope":        scope,
            "name":         name,
            "scope_label":  "Фьючерсы" if scope == "futures" else "Спот",
            "model_label":  self._MODEL_LABELS.get(name, name.capitalize()),
            "description":  self._MODEL_DESCRIPTIONS.get(name, name),
            "version":      version_str,
            "has_file":     has_file,
            "latest_file":  latest_file,
            "state":        state,
            "tag_class":    tag_class,
            "tag_text":     tag_text,
            "accuracy":     accuracy,
            "is_trained":   is_trained,
            "updated_at":   updated_at,
        }

    def _get_data_readiness(self, conn) -> dict[str, bool]:
        """
        Returns whether each scope has enough candles to start training.

        Checks symbol_registry for candle_count per category:
          - category "linear" → futures
          - category "spot"   → spot
        """
        result: dict[str, bool] = {"futures": False, "spot": False}
        if not conn:
            return result
        try:
            if not self._table_exists(conn, "symbol_registry"):  # type: ignore[attr-defined]
                return result

            # Threshold: at least one symbol with candle_count >= 100 per scope.
            # 100 candles → ~71 label windows (with MIN_CANDLES=25, FORWARD=5),
            # well above MIN_SAMPLES_TO_FIT=50.  We check MAX so even a single
            # ready symbol unlocks the Start button for that scope.
            rows = conn.execute(
                "SELECT category, MAX(candle_count) as max_count "
                "FROM symbol_registry GROUP BY category"
            ).fetchall()
            for row in rows:
                cat   = str(row[0] or "").lower()
                count = int(row[1] or 0)
                if ("linear" in cat or "future" in cat) and count >= 100:
                    result["futures"] = True
                elif "spot" in cat and count >= 100:
                    result["spot"] = True

        except Exception:
            pass
        return result

    def _read_process_stats(self, pid: int | None) -> dict:
        """Return RAM / CPU stats for a single pid via psutil (if available)."""
        empty: dict = {"pid": pid, "ram_mb": None, "cpu_pct": None, "gpu_pct": None}
        if not pid:
            return empty
        try:
            import psutil
            p = psutil.Process(pid)
            mem  = p.memory_info()
            cpu  = p.cpu_percent(interval=0.1)
            return {
                "pid":     pid,
                "ram_mb":  round(mem.rss / 1024 / 1024, 1),
                "cpu_pct": round(cpu, 1),
                "gpu_pct": None,   # GPU needs pynvml — not required as dependency
            }
        except Exception:
            return empty

    def _read_ml_process_resources(self) -> dict:
        """Return per-process resource stats for all ML training processes."""
        scopes: dict[str, dict] = {}
        for scope, proc_attr in (
            ("futures", "_ml_futures_process"),
            ("spot",    "_ml_spot_process"),
        ):
            proc = getattr(self, proc_attr, None)  # type: ignore[attr-defined]
            pid  = proc.pid if proc else None
            scopes[scope] = self._read_process_stats(pid)

        # System-wide GPU (nvidia-smi fallback — no new dependency)
        gpu_pct = gpu_mem_mb = None
        try:
            import subprocess
            out = subprocess.check_output(
                ["nvidia-smi",
                 "--query-gpu=utilization.gpu,memory.used",
                 "--format=csv,noheader,nounits"],
                timeout=2, text=True,
            )
            parts = out.strip().split(",")
            if len(parts) >= 2:
                gpu_pct    = float(parts[0].strip())
                gpu_mem_mb = float(parts[1].strip())
        except Exception:
            pass

        return {"scopes": scopes, "gpu_pct": gpu_pct, "gpu_mem_mb": gpu_mem_mb}

    def get_model_cards(self) -> str:
        """
        Returns JSON with 6 per-model cards:
        (historian / predictor / outcome) × (futures / spot).
        Also includes per-scope training states and data readiness.
        """
        import json
        from .api_helpers import _load_yaml, _resolve_db_path

        raw_cfg = _load_yaml()
        db_path = _resolve_db_path(raw_cfg)
        conn    = self._db_connect(db_path)  # type: ignore[attr-defined]
        try:
            training_runs = self._read_training_runs(conn, limit=20) if conn else []
            data_ready    = self._get_data_readiness(conn)
        finally:
            if conn:
                conn.close()

        cards: list[dict] = []
        for scope in ("futures", "spot"):
            scope_runs = [
                r for r in training_runs
                if self._normalize_model_scope(r.get("model_scope")) == scope  # type: ignore[attr-defined]
            ]
            for name in ("historian", "predictor", "outcome"):
                cards.append(self._build_per_model_card(scope, name, scope_runs))

        process_resources = self._read_ml_process_resources()  # type: ignore[attr-defined]

        return json.dumps({
            "cards": cards,
            "training_states": {
                "futures": self._ml_futures_process.state,  # type: ignore[attr-defined]
                "spot":    self._ml_spot_process.state,     # type: ignore[attr-defined]
            },
            "data_ready": data_ready,
            "process_resources": process_resources,
        }, default=str)

    def get_model_logs(self, scope: str) -> str:
        """
        Returns last 30 log lines from app_logs channel=ml_{scope}.
        Used by the per-scope logs panel on the Models page.
        """
        import json
        from .api_helpers import _load_yaml, _resolve_db_path

        scope = str(scope).strip().lower()
        if scope not in ("futures", "spot"):
            return json.dumps({"logs": []})

        raw_cfg = _load_yaml()
        db_path = _resolve_db_path(raw_cfg)
        conn    = self._db_connect(db_path)  # type: ignore[attr-defined]
        if not conn:
            return json.dumps({"logs": []})

        logs: list[dict] = []
        try:
            if self._table_exists(conn, "app_logs"):  # type: ignore[attr-defined]
                rows = conn.execute(
                    "SELECT level, message, created_at_utc FROM app_logs "
                    "WHERE channel=? ORDER BY created_at_utc DESC LIMIT 30",
                    (f"ml_{scope}",),
                ).fetchall()
                logs = [
                    {"level": str(r[0]), "msg": str(r[1]), "ts": str(r[2])}
                    for r in reversed(rows)
                ]
        except Exception:
            pass
        finally:
            conn.close()

        return json.dumps({"logs": logs}, default=str)

    # ── Public API ────────────────────────────────────────────

    def get_models(self) -> str:
        """Returns JSON model registry data."""
        import json
        from .api_helpers import _load_yaml, _resolve_db_path
        raw_cfg = _load_yaml()
        db_path = _resolve_db_path(raw_cfg)
        conn    = self._db_connect(db_path)  # type: ignore[attr-defined]
        try:
            payload = self._build_models_payload(conn)
            return json.dumps(payload, default=str)
        finally:
            if conn:
                conn.close()
