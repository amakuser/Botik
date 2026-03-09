"""
Lifecycle ML service process.

Modes:
- bootstrap: stats + autocalibration + gated training on closed lifecycle dataset
- train: incremental training on closed lifecycle dataset
- predict: score latest signals with active model
- online: train and predict in the same loop
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ml_service.dataset import load_lifecycle_dataset
from ml_service.evaluate import is_better_than_current
from ml_service.train import load_model_bundle, predict_batch, train_lifecycle_models
from src.botik.config import load_config
from src.botik.storage.lifecycle_store import ensure_lifecycle_schema, insert_model_stats
from src.botik.storage.sqlite_store import get_active_model, get_connection, upsert_model_registry
from src.botik.utils.logging import setup_logging
from src.botik.utils.retention import run_retention

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_training_paused(flag_path: Path) -> bool:
    return flag_path.exists()


def _count_closed_signals(conn) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0])


def _latest_policy_context(conn) -> tuple[str, str]:
    row = conn.execute(
        """
        SELECT COALESCE(policy_used, ''), COALESCE(profile_id, '')
        FROM signals
        ORDER BY ts_signal_ms DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return "", ""
    return str(row[0] or ""), str(row[1] or "")


def _compute_training_metrics(conn, window: int = 200) -> dict[str, float]:
    rows = conn.execute(
        """
        SELECT COALESCE(net_edge_bps, 0.0), COALESCE(was_profitable, 0)
        FROM outcomes
        ORDER BY closed_at_utc DESC
        LIMIT ?
        """,
        (max(int(window), 1),),
    ).fetchall()
    if rows:
        clipped_edges = [max(min(float(r[0] or 0.0), 5000.0), -5000.0) for r in rows]
        net_edge_mean = float(sum(clipped_edges) / len(clipped_edges))
        win_rate = float(sum(int(r[1] or 0) for r in rows) / len(rows))
    else:
        net_edge_mean = 0.0
        win_rate = 0.0

    fill_row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_signals,
            SUM(
                CASE
                    WHEN EXISTS (
                        SELECT 1 FROM executions_raw e
                        WHERE e.signal_id = s.signal_id
                    ) THEN 1
                    ELSE 0
                END
            ) AS filled_signals
        FROM (
            SELECT signal_id
            FROM signals
            ORDER BY ts_signal_ms DESC
            LIMIT ?
        ) s
        """,
        (max(int(window), 1),),
    ).fetchone()
    total_signals = int(fill_row[0] or 0) if fill_row else 0
    filled_signals = int(fill_row[1] or 0) if fill_row else 0
    fill_rate = float(filled_signals / total_signals) if total_signals > 0 else 0.0
    return {
        "net_edge_mean": net_edge_mean,
        "win_rate": win_rate,
        "fill_rate": fill_rate,
    }


def _append_model_stats(conn, model_id: str, metrics: dict[str, float]) -> None:
    insert_model_stats(
        conn,
        model_id=model_id or "bootstrap",
        ts_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        net_edge_mean=float(metrics.get("net_edge_mean", 0.0)),
        win_rate=float(metrics.get("win_rate", 0.0)),
        fill_rate=float(metrics.get("fill_rate", 0.0)),
    )


def run_bootstrap_stats(conn) -> dict[str, Any]:
    stats = {
        "signals_total": int(conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]),
        "outcomes_total": int(conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]),
        "executions_total": int(conn.execute("SELECT COUNT(*) FROM executions_raw").fetchone()[0]),
        "signals_with_profile": int(
            conn.execute("SELECT COUNT(*) FROM signals WHERE profile_id IS NOT NULL AND profile_id <> ''").fetchone()[0]
        ),
    }
    logger.info("ML bootstrap stats: %s", stats)
    return stats


def run_autocalibration(
    conn,
    *,
    min_fills: int,
    safety_buffer_bps: float,
    target_edge_bps: float,
    out_path: Path,
) -> dict[str, Any] | None:
    fills = conn.execute(
        """
        SELECT fee_rate
        FROM executions_raw
        WHERE fee_rate IS NOT NULL AND fee_rate > 0
        ORDER BY exec_time_ms DESC
        LIMIT ?
        """,
        (max(min_fills * 5, min_fills),),
    ).fetchall()
    fee_rates = [_safe_float(row[0]) for row in fills if _safe_float(row[0]) > 0]
    if len(fee_rates) < min_fills:
        logger.info("Autocalibration skipped: not enough fills with fee_rate (%s/%s).", len(fee_rates), min_fills)
        return None

    fee_rate_med = statistics.median(fee_rates[: max(min_fills, 1)])
    fee_bps = fee_rate_med * 10000.0

    slips_rows = conn.execute(
        """
        SELECT s.entry_price, o.entry_vwap
        FROM outcomes o
        JOIN signals s ON s.signal_id = o.signal_id
        WHERE s.entry_price IS NOT NULL
          AND s.entry_price > 0
          AND o.entry_vwap IS NOT NULL
          AND o.entry_vwap > 0
        ORDER BY o.closed_at_utc DESC
        LIMIT ?
        """,
        (max(min_fills * 3, min_fills),),
    ).fetchall()
    slippages = []
    for entry_price, entry_vwap in slips_rows:
        p0 = _safe_float(entry_price)
        p1 = _safe_float(entry_vwap)
        if p0 <= 0 or p1 <= 0:
            continue
        slippages.append(abs((p1 - p0) / p0) * 10000.0)

    if len(slippages) < min_fills:
        logger.info("Autocalibration skipped: not enough realized slippage samples (%s/%s).", len(slippages), min_fills)
        return None

    slip_med = statistics.median(slippages[: max(min_fills, 1)])
    total_slippage_bps = slip_med * 2.0
    min_required_spread_bps = (
        fee_bps
        + fee_bps
        + total_slippage_bps
        + float(max(safety_buffer_bps, 0.0))
        + float(max(target_edge_bps, 0.0))
    )

    payload = {
        "ts_utc": _utc_now_iso(),
        "sample_fills": len(fee_rates),
        "sample_slippage": len(slippages),
        "fee_rate_median": fee_rate_med,
        "fee_bps_median": fee_bps,
        "slippage_one_side_bps_median": slip_med,
        "slippage_total_bps_median": total_slippage_bps,
        "recommended_fee_entry_bps": fee_bps,
        "recommended_fee_exit_bps": fee_bps,
        "recommended_total_slippage_bps": total_slippage_bps,
        "recommended_min_required_spread_bps": min_required_spread_bps,
    }
    _write_json(out_path, payload)
    logger.info("Autocalibration updated: %s", payload)
    return payload


def run_train_once(
    conn,
    *,
    target_edge_bps: float,
    limit_rows: int,
    min_closed_trades: int,
    batch_size: int,
    model_dir: str,
) -> dict[str, Any] | None:
    dataset = load_lifecycle_dataset(
        conn,
        target_edge_bps=target_edge_bps,
        limit=limit_rows,
        closed_only=True,
    )
    rows = int(dataset["X"].shape[0])
    if rows < min_closed_trades:
        logger.info(
            "Training skipped: closed trades %s < min_closed_trades_to_train %s",
            rows,
            min_closed_trades,
        )
        return None

    model_id, model_path, metrics = train_lifecycle_models(
        dataset["X"],
        dataset["y_open"],
        dataset["y_edge"],
        batch_size=batch_size,
        model_dir=model_dir,
    )
    if not model_id:
        logger.warning("Training returned empty model_id.")
        return None
    metrics = dict(metrics)
    if "training_loss" not in metrics:
        open_acc = _safe_float(metrics.get("open_accuracy"), default=0.0)
        metrics["training_loss"] = max(0.0, 1.0 - open_acc)

    active = get_active_model(conn)
    current_metrics_json = active["metrics_json"] if active else None
    activate = is_better_than_current(metrics, current_metrics_json)
    upsert_model_registry(
        conn,
        model_id=model_id,
        path_or_payload=model_path,
        metrics_json=json.dumps(metrics),
        created_at_utc=_utc_now_iso(),
        is_active=activate,
    )
    logger.info(
        "ML train done: model_id=%s rows=%s activate=%s metrics=%s",
        model_id,
        rows,
        activate,
        metrics,
    )
    return {"model_id": model_id, "model_path": model_path, "metrics": metrics, "activated": activate}


def run_predict_once(
    conn,
    *,
    target_edge_bps: float,
    predict_limit_rows: int,
    predict_top_k: int,
) -> list[dict[str, Any]]:
    active = get_active_model(conn)
    if not active:
        logger.info("Predict skipped: no active model in model_registry.")
        return []

    bundle = load_model_bundle(active["path_or_payload"])
    dataset = load_lifecycle_dataset(
        conn,
        target_edge_bps=target_edge_bps,
        limit=max(predict_limit_rows, 1),
        closed_only=False,
    )
    X = dataset["X"]
    rows = dataset["rows"]
    if X.shape[0] == 0:
        logger.info("Predict skipped: no signals in lifecycle tables.")
        return []

    pred = predict_batch(bundle, X)
    open_prob = pred.get("open_probability")
    expected_edge = pred.get("expected_net_edge_bps")
    if open_prob is None:
        return []

    records: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        rec = {
            "signal_id": str(row["signal_id"]),
            "symbol": str(row["symbol"]),
            "side": str(row["side"]),
            "open_probability": float(open_prob[idx]),
        }
        if expected_edge is not None:
            rec["expected_net_edge_bps"] = float(expected_edge[idx])
        records.append(rec)

    records.sort(
        key=lambda item: (
            float(item.get("open_probability", 0.0)),
            float(item.get("expected_net_edge_bps", 0.0)),
        ),
        reverse=True,
    )
    top = records[: max(int(predict_top_k), 1)]
    logger.info("ML predict top=%s sample=%s", len(top), top[:3])
    return top


def main() -> None:
    parser = argparse.ArgumentParser(description="Lifecycle ML service")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")
    parser.add_argument("--mode", choices=["bootstrap", "train", "predict", "online"], default=None)
    parser.add_argument("--online-interval", type=int, default=None, help="Loop interval seconds")
    parser.add_argument("--train-once", action="store_true", help="Legacy alias for --mode train (single run)")
    parser.add_argument("--predict-once", action="store_true", help="Run predict one time and exit")
    parser.add_argument("--limit-rows", type=int, default=None, help="Lifecycle rows limit for training")
    parser.add_argument("--batch-size", type=int, default=None, help="Batch size for partial_fit")
    parser.add_argument("--min-closed-trades", type=int, default=None, help="Min closed trades for training")
    parser.add_argument("--target-edge-bps", type=float, default=None, help="Override target edge threshold in bps")
    parser.add_argument("--min-fills-for-autocalibration", type=int, default=None)
    parser.add_argument("--autocalibration-out", type=str, default=None)
    parser.add_argument("--training-pause-flag", type=str, default=None, help="Path to pause-training flag file")
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(
        log_dir=config.logging.dir,
        max_bytes=config.logging.max_bytes,
        backup_count=config.logging.backup_count,
    )

    if not config.ml.enabled:
        logger.warning("ML service is disabled by config.ml.enabled=false.")
        return

    mode = str(args.mode or config.ml.mode).strip().lower()
    if args.train_once:
        mode = "train"
    if args.predict_once:
        mode = "predict"
    if mode not in {"bootstrap", "train", "predict", "online"}:
        mode = "bootstrap"

    interval_sec = int(args.online_interval or config.ml.run_interval_sec)
    limit_rows = int(args.limit_rows or config.ml.train_limit_rows)
    batch_size = int(args.batch_size or config.ml.train_batch_size)
    min_closed = int(args.min_closed_trades or config.ml.min_closed_trades_to_train)
    target_edge_bps = float(args.target_edge_bps if args.target_edge_bps is not None else config.strategy.target_edge_bps)
    min_fills_for_autocalib = int(args.min_fills_for_autocalibration or config.ml.min_fills_for_autocalibration)
    autocalib_out = Path(args.autocalibration_out or config.ml.autocalibration_path)
    training_pause_flag = Path(args.training_pause_flag or config.ml.training_pause_flag_path)
    model_dir = str(config.ml.model_dir)
    predict_top_k = int(config.ml.predict_top_k)

    conn = get_connection(config.storage.path)
    ensure_lifecycle_schema(conn)

    async def run_loop() -> None:
        last_train_closed_count = 0
        while True:
            run_bootstrap_stats(conn)
            active = get_active_model(conn)
            active_model_id = str(active["model_id"]) if active else "bootstrap"
            paused = _is_training_paused(training_pause_flag)
            policy_used, profile_id = _latest_policy_context(conn)
            logger.info("Model %s, policy=%s, model=%s", active_model_id, policy_used or "n/a", profile_id or "n/a")

            latest_metrics = _compute_training_metrics(conn, window=200)
            _append_model_stats(conn, active_model_id, latest_metrics)
            logger.info(
                "training_metrics model=%s net_edge_mean=%.4f win_rate=%.2f%% fill_rate=%.2f%%",
                active_model_id,
                float(latest_metrics["net_edge_mean"]),
                float(latest_metrics["win_rate"]) * 100.0,
                float(latest_metrics["fill_rate"]) * 100.0,
            )

            train_enabled = mode in {"bootstrap", "train", "online"}
            predict_enabled = mode in {"predict", "online"}

            if train_enabled:
                closed_now = _count_closed_signals(conn)
                can_train = (
                    not paused
                    and closed_now >= min_closed
                    and (closed_now - last_train_closed_count >= max(batch_size, 1))
                )
                if args.train_once:
                    can_train = not paused
                if can_train:
                    trained = run_train_once(
                        conn,
                        target_edge_bps=target_edge_bps,
                        limit_rows=limit_rows,
                        min_closed_trades=min_closed,
                        batch_size=batch_size,
                        model_dir=model_dir,
                    )
                    if trained is not None:
                        last_train_closed_count = closed_now
                        logger.info(
                            "training_progress closed=%s next_batch_at=%s",
                            closed_now,
                            closed_now + max(batch_size, 1),
                        )
                    run_retention(
                        conn,
                        config.storage.path,
                        retention_days=config.retention_days,
                        max_size_gb=config.retention_max_db_size_gb,
                        run_vacuum=True,
                    )
                elif paused:
                    logger.info("training paused by flag: %s", training_pause_flag)

            if predict_enabled:
                run_predict_once(
                    conn,
                    target_edge_bps=target_edge_bps,
                    predict_limit_rows=max(limit_rows, 500),
                    predict_top_k=predict_top_k,
                )

            run_autocalibration(
                conn,
                min_fills=min_fills_for_autocalib,
                safety_buffer_bps=float(config.strategy.safety_buffer_bps),
                target_edge_bps=target_edge_bps,
                out_path=autocalib_out,
            )

            if args.train_once or args.predict_once:
                break
            await asyncio.sleep(max(interval_sec, 10))

    try:
        asyncio.run(run_loop())
    finally:
        conn.close()


if __name__ == "__main__":
    main()
