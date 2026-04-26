"""Create all e2e fixture files in tests/fixtures/."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

# ── Spot fixture DB ─────────────────────────────────────────────────────────

def create_spot_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE spot_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            asset TEXT NOT NULL,
            free_qty REAL NOT NULL DEFAULT 0,
            locked_qty REAL NOT NULL DEFAULT 0,
            total_qty REAL NOT NULL DEFAULT 0,
            source_of_truth TEXT,
            updated_at_utc TEXT
        );
        CREATE TABLE spot_holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            base_asset TEXT NOT NULL,
            free_qty REAL NOT NULL DEFAULT 0,
            locked_qty REAL NOT NULL DEFAULT 0,
            avg_entry_price REAL,
            hold_reason TEXT NOT NULL DEFAULT 'manual',
            source_of_truth TEXT NOT NULL DEFAULT 'fixture',
            recovered_from_exchange INTEGER NOT NULL DEFAULT 0,
            strategy_owner TEXT,
            auto_sell_allowed INTEGER NOT NULL DEFAULT 0,
            updated_at_utc TEXT
        );
        CREATE TABLE spot_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            order_id TEXT,
            order_link_id TEXT,
            order_type TEXT,
            time_in_force TEXT,
            price REAL NOT NULL DEFAULT 0,
            qty REAL NOT NULL DEFAULT 0,
            filled_qty REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            strategy_owner TEXT,
            updated_at_utc TEXT
        );
        CREATE TABLE spot_fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            exec_id TEXT NOT NULL,
            order_id TEXT,
            order_link_id TEXT,
            price REAL NOT NULL DEFAULT 0,
            qty REAL NOT NULL DEFAULT 0,
            fee REAL,
            fee_currency TEXT,
            is_maker INTEGER,
            exec_time_ms INTEGER,
            created_at_utc TEXT
        );
        CREATE TABLE spot_position_intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty REAL NOT NULL DEFAULT 0,
            created_at_utc TEXT
        );
    """)
    conn.execute("INSERT INTO spot_balances (account_type, asset, free_qty, total_qty, source_of_truth) VALUES (?,?,?,?,?)",
                 ("UNIFIED", "USDT", 5000.0, 5000.0, "fixture"))
    conn.execute("INSERT INTO spot_balances (account_type, asset, free_qty, total_qty, source_of_truth) VALUES (?,?,?,?,?)",
                 ("UNIFIED", "BTC", 0.5, 0.5, "fixture"))
    conn.execute("""INSERT INTO spot_holdings
        (account_type, symbol, base_asset, free_qty, avg_entry_price, hold_reason, source_of_truth, updated_at_utc)
        VALUES (?,?,?,?,?,?,?,?)""",
                 ("UNIFIED", "BTCUSDT", "BTC", 0.5, 65000.0, "strategy_entry", "fixture", "2026-04-15T10:00:00"))
    conn.execute("""INSERT INTO spot_holdings
        (account_type, symbol, base_asset, free_qty, avg_entry_price, hold_reason, source_of_truth, updated_at_utc)
        VALUES (?,?,?,?,?,?,?,?)""",
                 ("UNIFIED", "ETHUSDT", "ETH", 2.0, 3200.0, "strategy_entry", "fixture", "2026-04-14T10:00:00"))
    conn.execute("""INSERT INTO spot_orders
        (account_type, symbol, side, order_id, order_type, price, qty, status, updated_at_utc)
        VALUES (?,?,?,?,?,?,?,?,?)""",
                 ("UNIFIED", "BTCUSDT", "Buy", "order-fixture-001", "Limit", 64000.0, 0.1, "new", "2026-04-15T10:05:00"))
    conn.execute("""INSERT INTO spot_fills
        (account_type, symbol, side, exec_id, order_id, price, qty, fee, fee_currency, exec_time_ms)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                 ("UNIFIED", "BTCUSDT", "Buy", "exec-1", "order-fixture-001", 65000.0, 0.5, 3.25, "USDT", 1744700000000))
    conn.execute("INSERT INTO spot_position_intents (account_type, symbol, side, qty) VALUES (?,?,?,?)",
                 ("UNIFIED", "SOLUSDT", "Buy", 10.0))
    conn.commit()
    conn.close()
    print(f"  created {path.name}")


# ── Futures fixture DB ──────────────────────────────────────────────────────

def create_futures_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE futures_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            position_idx INTEGER NOT NULL DEFAULT 0,
            margin_mode TEXT,
            leverage REAL,
            qty REAL NOT NULL DEFAULT 0,
            entry_price REAL,
            mark_price REAL,
            liq_price REAL,
            unrealized_pnl REAL,
            take_profit REAL,
            stop_loss REAL,
            protection_status TEXT NOT NULL DEFAULT 'protected',
            source_of_truth TEXT NOT NULL DEFAULT 'fixture',
            recovered_from_exchange INTEGER NOT NULL DEFAULT 0,
            strategy_owner TEXT,
            updated_at_utc TEXT
        );
        CREATE TABLE futures_open_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            order_id TEXT,
            order_link_id TEXT,
            order_type TEXT,
            time_in_force TEXT,
            price REAL,
            qty REAL,
            status TEXT NOT NULL,
            reduce_only INTEGER,
            close_on_trigger INTEGER,
            strategy_owner TEXT,
            updated_at_utc TEXT
        );
        CREATE TABLE futures_fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            exec_id TEXT NOT NULL,
            order_id TEXT,
            order_link_id TEXT,
            price REAL NOT NULL DEFAULT 0,
            qty REAL NOT NULL DEFAULT 0,
            exec_fee REAL,
            fee_currency TEXT,
            is_maker INTEGER,
            exec_time_ms INTEGER,
            created_at_utc TEXT
        );
    """)
    conn.execute("""INSERT INTO futures_positions
        (account_type, symbol, side, qty, entry_price, mark_price, unrealized_pnl,
         protection_status, source_of_truth, recovered_from_exchange, updated_at_utc)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                 ("UNIFIED", "ETHUSDT", "Buy", 5.0, 3200.0, 3250.0, 250.0,
                  "protected", "fixture", 0, "2026-04-15T10:00:00"))
    conn.execute("""INSERT INTO futures_positions
        (account_type, symbol, side, qty, entry_price, mark_price, unrealized_pnl,
         protection_status, source_of_truth, recovered_from_exchange, updated_at_utc)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                 ("UNIFIED", "BTCUSDT", "Sell", 0.1, 68000.0, 67500.0, 50.0,
                  "protected", "fixture", 1, "2026-04-14T10:00:00"))
    conn.execute("""INSERT INTO futures_open_orders
        (account_type, symbol, side, order_id, order_type, price, qty, status, updated_at_utc)
        VALUES (?,?,?,?,?,?,?,?,?)""",
                 ("UNIFIED", "ETHUSDT", "Buy", "fut-order-001", "Limit", 3180.0, 2.0, "new", "2026-04-15T10:05:00"))
    conn.execute("""INSERT INTO futures_fills
        (account_type, symbol, side, exec_id, order_id, price, qty, exec_fee, fee_currency, exec_time_ms)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                 ("UNIFIED", "ETHUSDT", "Buy", "fut-exec-1", "fut-order-001", 3200.0, 5.0, 0.48, "USDT", 1744700100000))
    conn.commit()
    conn.close()
    print(f"  created {path.name}")


# ── Analytics fixture DB ────────────────────────────────────────────────────

def create_analytics_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    # Use futures_paper_trades (primary source in analytics adapter)
    conn.executescript("""
        CREATE TABLE futures_paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            model_scope TEXT NOT NULL DEFAULT 'futures',
            net_pnl REAL NOT NULL DEFAULT 0,
            was_profitable INTEGER NOT NULL DEFAULT 0,
            closed_at_utc TEXT NOT NULL
        );
    """)
    trades = [
        ("BTCUSDT",  "futures",  5.0, 1, "2026-04-08T09:00:00"),
        ("ETHUSDT",  "futures",  6.0, 1, "2026-04-09T10:00:00"),
        ("SOLUSDT",  "futures", -1.0, 0, "2026-04-11T11:00:00"),
        ("XRPUSDT",  "futures",  6.0, 1, "2026-04-15T12:00:00"),  # most recent → trade[0]
    ]
    conn.executemany(
        "INSERT INTO futures_paper_trades (symbol, model_scope, net_pnl, was_profitable, closed_at_utc) VALUES (?,?,?,?,?)",
        trades,
    )
    conn.commit()
    conn.close()
    print(f"  created {path.name}")


# ── Models fixture DB ───────────────────────────────────────────────────────

def create_models_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE model_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id TEXT NOT NULL,
            path_or_payload TEXT NOT NULL DEFAULT '',
            metrics_json TEXT NOT NULL DEFAULT '{}',
            created_at_utc TEXT
        );
        CREATE TABLE ml_training_runs (
            run_id TEXT PRIMARY KEY,
            model_scope TEXT NOT NULL,
            model_version TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            epoch INTEGER,
            max_epochs INTEGER,
            loss REAL,
            accuracy REAL,
            sharpe_ratio REAL,
            trade_count INTEGER,
            is_trained INTEGER NOT NULL DEFAULT 0,
            trained_at_utc TEXT,
            started_at_utc TEXT NOT NULL,
            finished_at_utc TEXT,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS app_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );
    """)
    import json as _json
    registry_rows = [
        ("futures-paper-v2",   "models/futures-paper-v2.pkl",   _json.dumps({"status": "active", "model_scope": "futures"}), "2026-04-15T12:00:00"),
        ("spot-champion-v3",   "models/spot-champion-v3.pkl",   _json.dumps({"status": "active", "model_scope": "spot"}),    "2026-04-14T12:00:00"),
        ("futures-candidate-v1","models/futures-candidate-v1.pkl",_json.dumps({"status": "candidate", "model_scope": "futures"}),"2026-04-10T12:00:00"),
    ]
    conn.executemany(
        "INSERT INTO model_registry (model_id, path_or_payload, metrics_json, created_at_utc) VALUES (?,?,?,?)",
        registry_rows,
    )
    # run[0] (most recent by started_at) = run-futures-1
    conn.execute("""
        INSERT INTO ml_training_runs
        (run_id, model_scope, model_version, mode, status, accuracy, is_trained, started_at_utc, finished_at_utc)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, ("run-futures-1", "futures", "futures-paper-v2", "controlled_fixture",
          "completed", 0.72, 1, "2026-04-15T11:00:00", "2026-04-15T11:05:00"))
    conn.execute("""
        INSERT INTO ml_training_runs
        (run_id, model_scope, model_version, mode, status, accuracy, is_trained, started_at_utc, finished_at_utc)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, ("run-spot-1", "spot", "spot-champion-v3", "controlled_fixture",
          "completed", 0.69, 1, "2026-04-14T11:00:00", "2026-04-14T11:05:00"))
    conn.commit()
    conn.close()
    print(f"  created {path.name}")


# ── Models manifest YAML ────────────────────────────────────────────────────

def create_models_manifest(path: Path) -> None:
    path.write_text(
        "active_spot_model: spot-champion-v3\n"
        "active_futures_model: futures-paper-v2\n"
        "spot_checkpoint_path: models/spot-champion-v3.pkl\n"
        "futures_checkpoint_path: models/futures-paper-v2.pkl\n",
        encoding="utf-8",
    )
    print(f"  created {path.name}")


# ── Runtime status fixture JSON ─────────────────────────────────────────────

def create_runtime_status_json(path: Path) -> None:
    payload = {
        "generated_at": "2026-04-19T00:00:00+00:00",
        "runtimes": [
            {
                "runtime_id": "spot",
                "label": "Spot Runtime",
                "state": "offline",
                "pids": [],
                "pid_count": 0,
                "last_heartbeat_at": None,
                "last_heartbeat_age_seconds": None,
                "last_error": None,
                "last_error_at": None,
                "status_reason": "fixture mode — no running process",
                "source_mode": "fixture",
            },
            {
                "runtime_id": "futures",
                "label": "Futures Runtime",
                "state": "offline",
                "pids": [],
                "pid_count": 0,
                "last_heartbeat_at": None,
                "last_heartbeat_age_seconds": None,
                "last_error": None,
                "last_error_at": None,
                "status_reason": "fixture mode — no running process",
                "source_mode": "fixture",
            },
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"  created {path.name}")


# ── Telegram fixture JSON ───────────────────────────────────────────────────

def create_telegram_json(path: Path) -> None:
    payload = {
        "snapshot": {
            "source_mode": "fixture",
            "generated_at": "2026-04-19T00:00:00+00:00",
            "summary": {
                "bot_profile": "botik_fixture_bot",
                "token_profile_name": "TELEGRAM_BOT_TOKEN",
                "token_configured": True,
                "internal_bot_disabled": False,
                "connectivity_state": "healthy",
                "connectivity_detail": "Bot is reachable",
                "allowed_chat_count": 2,
                "allowed_chats_masked": ["***111", "***222"],
                "commands_count": 1,
                "alerts_count": 1,
                "errors_count": 1,
                "last_successful_send": "2026-04-19T00:00:00+00:00",
                "last_error": None,
                "startup_status": "ok",
            },
            "recent_commands": [
                {
                    "ts": "2026-04-19T00:00:00+00:00",
                    "command": "/status",
                    "source": "telegram",
                    "status": "ok",
                    "chat_id_masked": "***111",
                    "username": "fixture_user",
                    "args": None,
                }
            ],
            "recent_alerts": [
                {
                    "ts": "2026-04-19T00:00:00+00:00",
                    "alert_type": "trade_open",
                    "message": "Fixture trade alert: BTCUSDT Buy",
                    "delivered": True,
                    "source": "telegram",
                    "status": "ok",
                }
            ],
            "recent_errors": [
                {
                    "ts": "2026-04-19T00:00:00+00:00",
                    "error": "Fixture connectivity error: test only",
                    "source": "telegram",
                    "status": "error",
                }
            ],
            "truncated": {
                "recent_commands": False,
                "recent_alerts": False,
                "recent_errors": False,
            },
        },
        "connectivity_check_result": {
            "checked_at": "2026-04-19T00:00:00+00:00",
            "source_mode": "fixture",
            "state": "healthy",
            "detail": "Fixture connectivity check passed",
            "bot_username": "botik_fixture_bot",
            "latency_ms": 42.0,
            "error": None,
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"  created {path.name}")


if __name__ == "__main__":
    print("Creating e2e fixtures ...")
    create_spot_db(FIXTURES_DIR / "spot.fixture.db")
    create_futures_db(FIXTURES_DIR / "futures.fixture.db")
    create_analytics_db(FIXTURES_DIR / "analytics.fixture.db")
    create_models_db(FIXTURES_DIR / "models.fixture.db")
    create_models_manifest(FIXTURES_DIR / "active_models.fixture.yaml")
    create_runtime_status_json(FIXTURES_DIR / "runtime_status.fixture.json")
    create_telegram_json(FIXTURES_DIR / "telegram.fixture.json")
    print("Done. 7 fixture files created.")
