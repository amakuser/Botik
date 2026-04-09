"""
Database migration runner for Botik.

Migrations are numbered Python functions registered in MIGRATIONS dict.
Each migration receives a Conn and applies schema changes idempotently.

Usage:
    from src.botik.storage.db import get_db
    from src.botik.storage.migrations import run_migrations

    db = get_db()
    with db.connect() as conn:
        run_migrations(conn)
"""
from __future__ import annotations

import logging
from typing import Callable

from src.botik.storage.db import Conn, SQLITE, POSTGRES

log = logging.getLogger("botik.storage.migrations")


# ─────────────────────────────────────────────────────────────────────────────
#  Version tracking table
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_version_table(conn: Conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS _schema_migrations (
            version     INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            applied_at  TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _applied_versions(conn: Conn) -> set[int]:
    try:
        rows = conn.execute("SELECT version FROM _schema_migrations").fetchall()
        return {int(r[0]) for r in rows}
    except Exception:
        return set()


def _mark_applied(conn: Conn, version: int, name: str) -> None:
    if conn.dialect == SQLITE:
        conn.execute(
            "INSERT OR IGNORE INTO _schema_migrations (version, name, applied_at) "
            "VALUES (?, ?, datetime('now'))",
            (version, name),
        )
    else:
        conn.execute(
            "INSERT INTO _schema_migrations (version, name, applied_at) "
            "VALUES (%s, %s, NOW()) ON CONFLICT (version) DO NOTHING",
            (version, name),
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_migrations(conn: Conn) -> int:
    """
    Apply all pending migrations.  Returns number of migrations applied.
    Safe to call on every startup — already-applied migrations are skipped.
    """
    _ensure_version_table(conn)
    applied = _applied_versions(conn)
    count = 0
    for version, (name, fn) in sorted(MIGRATIONS.items()):
        if version in applied:
            continue
        log.info("Applying migration %03d: %s", version, name)
        fn(conn)
        conn.commit()
        _mark_applied(conn, version, name)
        conn.commit()
        count += 1
    if count:
        log.info("Applied %d migration(s)", count)
    return count


# ─────────────────────────────────────────────────────────────────────────────
#  Migration definitions
# ─────────────────────────────────────────────────────────────────────────────

def _m001_core_schema(conn: Conn) -> None:
    """Initial core schema: account_snapshots, reconciliation, audit."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS account_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id     TEXT UNIQUE NOT NULL,
            reconciliation_run_id TEXT,
            account_type    TEXT NOT NULL,
            snapshot_kind   TEXT NOT NULL,
            total_equity    REAL,
            wallet_balance  REAL,
            available_balance REAL,
            payload_json    TEXT NOT NULL,
            created_at_utc  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_account_snapshots_kind
            ON account_snapshots(snapshot_kind, created_at_utc);

        CREATE TABLE IF NOT EXISTS reconciliation_runs (
            reconciliation_run_id TEXT PRIMARY KEY,
            trigger_source  TEXT NOT NULL,
            status          TEXT NOT NULL,
            started_at_utc  TEXT NOT NULL,
            finished_at_utc TEXT,
            summary_json    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_reconciliation_runs_started
            ON reconciliation_runs(started_at_utc);

        CREATE TABLE IF NOT EXISTS reconciliation_issues (
            issue_id        TEXT PRIMARY KEY,
            reconciliation_run_id TEXT,
            issue_type      TEXT NOT NULL,
            domain          TEXT NOT NULL,
            symbol          TEXT,
            severity        TEXT NOT NULL,
            details_json    TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'open',
            created_at_utc  TEXT NOT NULL,
            resolved_at_utc TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_reconciliation_issues_open
            ON reconciliation_issues(status, created_at_utc);

        CREATE TABLE IF NOT EXISTS strategy_runs (
            strategy_run_id TEXT PRIMARY KEY,
            strategy_name   TEXT NOT NULL,
            market_category TEXT NOT NULL,
            status          TEXT NOT NULL,
            started_at_utc  TEXT NOT NULL,
            finished_at_utc TEXT,
            config_json     TEXT
        );

        CREATE TABLE IF NOT EXISTS events_audit (
            event_id        TEXT PRIMARY KEY,
            event_type      TEXT NOT NULL,
            domain          TEXT NOT NULL,
            symbol          TEXT,
            ref_id          TEXT,
            payload_json    TEXT NOT NULL,
            created_at_utc  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_audit_type
            ON events_audit(event_type, created_at_utc);
        """
    )


def _m002_spot_schema(conn: Conn) -> None:
    """Spot storage: balances, holdings, orders, fills, decisions."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS spot_balances (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type    TEXT NOT NULL,
            asset           TEXT NOT NULL,
            free_qty        REAL NOT NULL DEFAULT 0.0,
            locked_qty      REAL NOT NULL DEFAULT 0.0,
            total_qty       REAL NOT NULL DEFAULT 0.0,
            source_of_truth TEXT NOT NULL,
            created_at_utc  TEXT NOT NULL,
            updated_at_utc  TEXT NOT NULL,
            UNIQUE(account_type, asset)
        );

        CREATE TABLE IF NOT EXISTS spot_holdings (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type            TEXT NOT NULL,
            symbol                  TEXT NOT NULL,
            base_asset              TEXT NOT NULL,
            free_qty                REAL NOT NULL DEFAULT 0.0,
            locked_qty              REAL NOT NULL DEFAULT 0.0,
            avg_entry_price         REAL,
            current_price           REAL,
            purchase_value_usdt     REAL,
            current_value_usdt      REAL,
            unrealized_pnl          REAL,
            unrealized_pnl_pct      REAL,
            hold_reason             TEXT NOT NULL,
            source_of_truth         TEXT NOT NULL,
            recovered_from_exchange INTEGER NOT NULL DEFAULT 0,
            strategy_owner          TEXT,
            auto_sell_allowed       INTEGER NOT NULL DEFAULT 0,
            created_at_utc          TEXT NOT NULL,
            updated_at_utc          TEXT NOT NULL,
            UNIQUE(account_type, symbol, base_asset)
        );
        CREATE INDEX IF NOT EXISTS idx_spot_holdings_symbol
            ON spot_holdings(symbol, updated_at_utc);

        CREATE TABLE IF NOT EXISTS spot_orders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type    TEXT NOT NULL,
            symbol          TEXT NOT NULL,
            order_id        TEXT,
            order_link_id   TEXT UNIQUE,
            side            TEXT NOT NULL,
            order_type      TEXT NOT NULL,
            price           REAL,
            qty             REAL,
            filled_qty      REAL NOT NULL DEFAULT 0.0,
            status          TEXT NOT NULL,
            time_in_force   TEXT,
            is_maker        INTEGER,
            created_at_utc  TEXT NOT NULL,
            updated_at_utc  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_spot_orders_symbol
            ON spot_orders(symbol, created_at_utc);
        CREATE INDEX IF NOT EXISTS idx_spot_orders_status
            ON spot_orders(status, updated_at_utc);

        CREATE TABLE IF NOT EXISTS spot_fills (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            exec_id         TEXT UNIQUE NOT NULL,
            order_id        TEXT,
            order_link_id   TEXT,
            symbol          TEXT NOT NULL,
            side            TEXT NOT NULL,
            exec_price      REAL NOT NULL,
            exec_qty        REAL NOT NULL,
            exec_fee        REAL,
            fee_currency    TEXT,
            is_maker        INTEGER,
            exec_time_ms    INTEGER,
            recorded_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_spot_fills_symbol_time
            ON spot_fills(symbol, exec_time_ms);

        CREATE TABLE IF NOT EXISTS spot_exit_decisions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            decision_type   TEXT NOT NULL,
            pnl_pct         REAL,
            pnl_quote       REAL,
            reason          TEXT,
            created_at_utc  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_spot_exit_decisions_symbol
            ON spot_exit_decisions(symbol, created_at_utc);
        """
    )


def _m003_futures_schema(conn: Conn) -> None:
    """Futures storage: positions, orders, fills, paper trades."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS futures_positions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type        TEXT NOT NULL,
            symbol              TEXT NOT NULL,
            side                TEXT NOT NULL,
            size                REAL NOT NULL DEFAULT 0.0,
            entry_price         REAL,
            mark_price          REAL,
            leverage            REAL,
            liq_price           REAL,
            unrealised_pnl      REAL,
            cum_realised_pnl    REAL,
            protection_status   TEXT NOT NULL DEFAULT 'unknown',
            strategy_owner      TEXT,
            updated_at_utc      TEXT NOT NULL,
            created_at_utc      TEXT NOT NULL,
            UNIQUE(account_type, symbol, side)
        );
        CREATE INDEX IF NOT EXISTS idx_futures_positions_symbol
            ON futures_positions(symbol, updated_at_utc);

        CREATE TABLE IF NOT EXISTS futures_open_orders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type    TEXT NOT NULL,
            symbol          TEXT NOT NULL,
            order_id        TEXT,
            order_link_id   TEXT UNIQUE,
            side            TEXT NOT NULL,
            order_type      TEXT NOT NULL,
            price           REAL,
            qty             REAL,
            status          TEXT NOT NULL,
            reduce_only     INTEGER NOT NULL DEFAULT 0,
            created_at_utc  TEXT NOT NULL,
            updated_at_utc  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS futures_fills (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            exec_id         TEXT UNIQUE NOT NULL,
            order_link_id   TEXT,
            symbol          TEXT NOT NULL,
            side            TEXT NOT NULL,
            exec_price      REAL NOT NULL,
            exec_qty        REAL NOT NULL,
            exec_fee        REAL,
            fee_rate        REAL,
            is_maker        INTEGER,
            exec_time_ms    INTEGER,
            recorded_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_futures_fills_symbol
            ON futures_fills(symbol, exec_time_ms);

        CREATE TABLE IF NOT EXISTS futures_paper_trades (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id            TEXT UNIQUE NOT NULL,
            symbol              TEXT NOT NULL,
            side                TEXT NOT NULL,
            entry_price         REAL NOT NULL,
            exit_price          REAL,
            qty                 REAL NOT NULL,
            gross_pnl           REAL,
            net_pnl             REAL,
            hold_time_ms        INTEGER,
            spike_direction     INTEGER,
            spike_strength_bps  REAL,
            impulse_bps         REAL,
            entry_reason        TEXT,
            exit_reason         TEXT,
            model_scope         TEXT NOT NULL DEFAULT 'futures',
            model_version       TEXT,
            was_profitable      INTEGER,
            opened_at_utc       TEXT NOT NULL,
            closed_at_utc       TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_futures_paper_symbol
            ON futures_paper_trades(symbol, opened_at_utc);
        CREATE INDEX IF NOT EXISTS idx_futures_paper_scope
            ON futures_paper_trades(model_scope, closed_at_utc);

        CREATE TABLE IF NOT EXISTS futures_protection_orders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            side            TEXT NOT NULL,
            sl_price        REAL,
            tp_price        REAL,
            status          TEXT NOT NULL DEFAULT 'unknown',
            created_at_utc  TEXT NOT NULL,
            updated_at_utc  TEXT NOT NULL,
            UNIQUE(symbol, side)
        );

        CREATE TABLE IF NOT EXISTS futures_funding_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            funding_rate    REAL NOT NULL,
            funding_fee     REAL,
            created_at_utc  TEXT NOT NULL
        );
        """
    )


def _m004_lifecycle_schema(conn: Conn) -> None:
    """ML lifecycle: signals, order events, executions, outcomes, model stats."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS signals (
            signal_id               TEXT PRIMARY KEY,
            model_scope             TEXT NOT NULL DEFAULT 'spot',
            ts_signal_ms            INTEGER NOT NULL,
            symbol                  TEXT NOT NULL,
            side                    TEXT NOT NULL,
            best_bid                REAL,
            best_ask                REAL,
            mid                     REAL,
            spread_bps              REAL,
            depth_bid_quote         REAL,
            depth_ask_quote         REAL,
            slippage_buy_bps_est    REAL,
            slippage_sell_bps_est   REAL,
            trades_per_min          REAL,
            p95_trade_gap_ms        REAL,
            vol_1s_bps              REAL,
            impulse_bps             REAL,
            spike_direction         INTEGER,
            spike_strength_bps      REAL,
            min_required_spread_bps REAL,
            scanner_status          TEXT,
            model_version           TEXT,
            profile_id              TEXT,
            action_entry_tick_offset    INTEGER,
            action_order_qty_base       REAL,
            action_target_profit        REAL,
            action_safety_buffer        REAL,
            action_min_top_book_qty     REAL,
            action_stop_loss_pct        REAL,
            action_take_profit_pct      REAL,
            action_hold_timeout_sec     INTEGER,
            action_maker_only           INTEGER,
            policy_used             TEXT,
            pred_open_prob          REAL,
            pred_exp_edge_bps       REAL,
            active_model_id         TEXT,
            model_id                TEXT,
            reward_net_edge_bps     REAL,
            reward_updated_at_utc   TEXT,
            order_size_quote        REAL,
            order_size_base         REAL,
            entry_price             REAL,
            created_at_utc          TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_signals_symbol_ts
            ON signals(symbol, ts_signal_ms);
        CREATE INDEX IF NOT EXISTS idx_signals_scope
            ON signals(model_scope, created_at_utc);

        CREATE TABLE IF NOT EXISTS order_signal_map (
            order_link_id   TEXT PRIMARY KEY,
            signal_id       TEXT,
            created_at_utc  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_order_signal_signal
            ON order_signal_map(signal_id);

        CREATE TABLE IF NOT EXISTS order_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id        TEXT,
            order_link_id   TEXT,
            signal_id       TEXT,
            symbol          TEXT NOT NULL,
            side            TEXT,
            order_type      TEXT,
            time_in_force   TEXT,
            price           REAL,
            qty             REAL,
            order_status    TEXT,
            avg_price       REAL,
            cum_exec_qty    REAL,
            cum_exec_value  REAL,
            created_time_ms INTEGER,
            updated_time_ms INTEGER,
            event_time_utc  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_order_events_order_link
            ON order_events(order_link_id);
        CREATE INDEX IF NOT EXISTS idx_order_events_symbol_ts
            ON order_events(symbol, event_time_utc);

        CREATE TABLE IF NOT EXISTS executions_raw (
            exec_id         TEXT PRIMARY KEY,
            order_id        TEXT,
            order_link_id   TEXT,
            signal_id       TEXT,
            symbol          TEXT NOT NULL,
            side            TEXT,
            order_type      TEXT,
            exec_price      REAL NOT NULL,
            exec_qty        REAL NOT NULL,
            exec_fee        REAL,
            fee_rate        REAL,
            fee_currency    TEXT,
            is_maker        INTEGER,
            exec_time_ms    INTEGER,
            recorded_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_exec_signal
            ON executions_raw(signal_id);
        CREATE INDEX IF NOT EXISTS idx_exec_symbol_time
            ON executions_raw(symbol, exec_time_ms);

        CREATE TABLE IF NOT EXISTS outcomes (
            signal_id                   TEXT PRIMARY KEY,
            model_scope                 TEXT NOT NULL DEFAULT 'spot',
            symbol                      TEXT NOT NULL,
            entry_vwap                  REAL,
            exit_vwap                   REAL,
            filled_qty                  REAL,
            hold_time_ms                INTEGER,
            gross_pnl_quote             REAL,
            net_pnl_quote               REAL,
            net_edge_bps                REAL,
            max_adverse_excursion_bps   REAL,
            max_favorable_excursion_bps REAL,
            was_fully_filled            INTEGER,
            was_profitable              INTEGER,
            exit_reason                 TEXT,
            closed_at_utc               TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_outcomes_symbol_close
            ON outcomes(symbol, closed_at_utc);
        CREATE INDEX IF NOT EXISTS idx_outcomes_scope
            ON outcomes(model_scope, closed_at_utc);

        CREATE TABLE IF NOT EXISTS model_stats (
            model_id        TEXT NOT NULL,
            model_scope     TEXT NOT NULL DEFAULT 'spot',
            ts_ms           INTEGER,
            net_edge_mean   REAL,
            win_rate        REAL,
            fill_rate       REAL,
            accuracy        REAL,
            sharpe_ratio    REAL,
            trade_count     INTEGER,
            status          TEXT NOT NULL DEFAULT 'idle',
            created_at_utc  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_model_stats_ts
            ON model_stats(ts_ms);
        CREATE INDEX IF NOT EXISTS idx_model_stats_scope
            ON model_stats(model_scope, ts_ms);

        CREATE TABLE IF NOT EXISTS bandit_state (
            symbol      TEXT NOT NULL,
            profile_id  TEXT NOT NULL,
            n           INTEGER NOT NULL,
            mean        REAL NOT NULL,
            m2          REAL NOT NULL,
            updated_at_utc TEXT NOT NULL,
            PRIMARY KEY (symbol, profile_id)
        );
        """
    )


def _m005_price_history(conn: Conn) -> None:
    """OHLCV price history table for ML feature building."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            category        TEXT NOT NULL DEFAULT 'spot',
            interval        TEXT NOT NULL,
            open_time_ms    INTEGER NOT NULL,
            open            REAL NOT NULL,
            high            REAL NOT NULL,
            low             REAL NOT NULL,
            close           REAL NOT NULL,
            volume          REAL NOT NULL,
            turnover        REAL,
            created_at_utc  TEXT NOT NULL,
            UNIQUE(symbol, category, interval, open_time_ms)
        );
        CREATE INDEX IF NOT EXISTS idx_price_history_symbol_time
            ON price_history(symbol, category, interval, open_time_ms);
        """
    )


def _m006_app_logs(conn: Conn) -> None:
    """Persistent structured log storage split by channel."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS app_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            channel         TEXT NOT NULL DEFAULT 'app',
            level           TEXT NOT NULL DEFAULT 'INFO',
            message         TEXT NOT NULL,
            extra_json      TEXT,
            created_at_utc  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_app_logs_channel_ts
            ON app_logs(channel, created_at_utc);
        CREATE INDEX IF NOT EXISTS idx_app_logs_level_ts
            ON app_logs(level, created_at_utc);
        """
    )


def _m007_bot_settings(conn: Conn) -> None:
    """Key-value store for runtime settings (API keys, config overrides)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS bot_settings (
            key             TEXT PRIMARY KEY,
            value           TEXT,
            is_secret       INTEGER NOT NULL DEFAULT 0,
            description     TEXT,
            updated_at_utc  TEXT NOT NULL
        );
        """
    )


def _m008_ml_training_runs(conn: Conn) -> None:
    """ML training run history with criteria for 'model is trained'."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ml_training_runs (
            run_id          TEXT PRIMARY KEY,
            model_scope     TEXT NOT NULL,
            model_version   TEXT NOT NULL,
            mode            TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending',
            epoch           INTEGER,
            max_epochs      INTEGER,
            loss            REAL,
            accuracy        REAL,
            sharpe_ratio    REAL,
            trade_count     INTEGER,
            is_trained      INTEGER NOT NULL DEFAULT 0,
            trained_at_utc  TEXT,
            started_at_utc  TEXT NOT NULL,
            finished_at_utc TEXT,
            notes           TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ml_training_scope
            ON ml_training_runs(model_scope, started_at_utc);
        CREATE INDEX IF NOT EXISTS idx_ml_training_trained
            ON ml_training_runs(model_scope, is_trained, trained_at_utc);
        """
    )


def _m009_telegram_log(conn: Conn) -> None:
    """Telegram command and alert history."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS telegram_commands (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id         TEXT NOT NULL,
            username        TEXT,
            command         TEXT NOT NULL,
            args            TEXT,
            response_status TEXT NOT NULL DEFAULT 'sent',
            created_at_utc  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_telegram_commands_ts
            ON telegram_commands(created_at_utc);

        CREATE TABLE IF NOT EXISTS telegram_alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type      TEXT NOT NULL,
            message         TEXT NOT NULL,
            delivered       INTEGER NOT NULL DEFAULT 0,
            created_at_utc  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_telegram_alerts_ts
            ON telegram_alerts(created_at_utc);
        """
    )


def _m010_labeled_samples(conn: Conn) -> None:
    """Labeled samples for ML training (historical + live trades)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS labeled_samples (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            feature_hash    TEXT UNIQUE NOT NULL,
            symbol          TEXT NOT NULL,
            model_scope     TEXT NOT NULL DEFAULT 'futures',
            features_json   TEXT NOT NULL,
            label           INTEGER NOT NULL,
            source          TEXT NOT NULL DEFAULT 'historical',
            weight          REAL NOT NULL DEFAULT 1.0,
            created_at_utc  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_labeled_scope_symbol
            ON labeled_samples(model_scope, symbol, created_at_utc);
        CREATE INDEX IF NOT EXISTS idx_labeled_source
            ON labeled_samples(source, model_scope);
        """
    )


def _m011_symbol_registry(conn: Conn) -> None:
    """
    Symbol registry for the ML data pipeline — raw OHLCV data tracking only.

    Tracks per-symbol candle availability independently of model logic.
    No hardcoded symbol lists — the system discovers and registers symbols itself.

    This table knows nothing about models or labeling.
    For per-model labeling status see: _m012_symbol_labeling_status.

    data_status: 'empty' | 'partial' | 'ready'
                 'ready' means >= MIN_CANDLES_READY candles are available.
    ws_active:   1 if a live WebSocket subscription is currently active.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS symbol_registry (
            symbol           TEXT    NOT NULL,
            category         TEXT    NOT NULL,
            interval         TEXT    NOT NULL DEFAULT '1',
            candle_count     INTEGER NOT NULL DEFAULT 0,
            last_candle_ms   INTEGER,
            last_backfill_at TEXT,
            ws_active        INTEGER NOT NULL DEFAULT 0,
            data_status      TEXT    NOT NULL DEFAULT 'empty',
            added_at_utc     TEXT    NOT NULL,
            updated_at_utc   TEXT    NOT NULL,
            PRIMARY KEY (symbol, category, interval)
        );
        CREATE INDEX IF NOT EXISTS idx_symbol_registry_status
            ON symbol_registry(data_status, category);
        """
    )


def _m012_symbol_labeling_status(conn: Conn) -> None:
    """
    Per-model labeling status for the ML data pipeline.

    Tracks how many labeled_samples have been created for each
    (symbol, category, interval, model_scope) combination.

    Separated from symbol_registry deliberately:
    - futures-labeler (model_scope='futures') uses different feature logic than
      spot-labeler (model_scope='spot'), even on the same raw candles.
    - A symbol can be fully labeled for futures but still pending for spot.

    labeling_status: 'pending' | 'labeling' | 'ready'
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS symbol_labeling_status (
            symbol          TEXT    NOT NULL,
            category        TEXT    NOT NULL,
            interval        TEXT    NOT NULL DEFAULT '1',
            model_scope     TEXT    NOT NULL,
            labeling_status TEXT    NOT NULL DEFAULT 'pending',
            labeled_count   INTEGER NOT NULL DEFAULT 0,
            last_labeled_at TEXT,
            added_at_utc    TEXT    NOT NULL,
            updated_at_utc  TEXT    NOT NULL,
            PRIMARY KEY (symbol, category, interval, model_scope)
        );
        CREATE INDEX IF NOT EXISTS idx_symbol_labeling_scope
            ON symbol_labeling_status(model_scope, labeling_status);
        CREATE INDEX IF NOT EXISTS idx_symbol_labeling_status
            ON symbol_labeling_status(labeling_status, category);
        """
    )


def _m014_price_history_drop_created_at(conn: Conn) -> None:
    """
    Drop redundant created_at_utc column from price_history.

    The column duplicates information already implicit in open_time_ms and
    is never read by any query.  Removing it saves ~25 bytes per row; on
    a 27 M-row table that is ~675 MB recovered after the next VACUUM.

    Requires SQLite ≥ 3.35.0 (ALTER TABLE … DROP COLUMN).
    """
    try:
        conn.execute("ALTER TABLE price_history DROP COLUMN created_at_utc")
    except Exception:
        # Column may already be absent (fresh DB or already migrated).
        pass


def _m015_futures_fills_closed_pnl(conn: Conn) -> None:
    """Add closed_pnl column to futures_fills for AccountSyncWorker data."""
    try:
        conn.execute("ALTER TABLE futures_fills ADD COLUMN closed_pnl REAL")
    except Exception:
        pass  # Already exists or not supported


def _m013_orderbook_snapshots(conn: Conn) -> None:
    """
    Orderbook snapshots table for the order book poller (T41).

    Stores periodic REST snapshots of the Bybit order book
    (top 25 bids/asks) for a watched set of symbols.

    Retention: only the last 100 snapshots per (symbol, category) are kept.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS orderbook_snapshots (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol         TEXT    NOT NULL,
            category       TEXT    NOT NULL DEFAULT 'linear',
            bids_json      TEXT    NOT NULL,
            asks_json      TEXT    NOT NULL,
            ts_ms          INTEGER NOT NULL,
            created_at_utc TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_orderbook_symbol_ts
            ON orderbook_snapshots(symbol, category, ts_ms DESC);
        """
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Registry  (version → (name, function))
# ─────────────────────────────────────────────────────────────────────────────

MIGRATIONS: dict[int, tuple[str, Callable[[Conn], None]]] = {
    1: ("core_schema",          _m001_core_schema),
    2: ("spot_schema",          _m002_spot_schema),
    3: ("futures_schema",       _m003_futures_schema),
    4: ("lifecycle_schema",     _m004_lifecycle_schema),
    5: ("price_history",        _m005_price_history),
    6: ("app_logs",             _m006_app_logs),
    7: ("bot_settings",         _m007_bot_settings),
    8: ("ml_training_runs",     _m008_ml_training_runs),
    9: ("telegram_log",         _m009_telegram_log),
    10: ("labeled_samples",     _m010_labeled_samples),
    11: ("symbol_registry",          _m011_symbol_registry),
    12: ("symbol_labeling_status",   _m012_symbol_labeling_status),
    13: ("orderbook_snapshots",      _m013_orderbook_snapshots),
    14: ("price_history_drop_created_at", _m014_price_history_drop_created_at),
    15: ("futures_fills_closed_pnl",      _m015_futures_fills_closed_pnl),
}
