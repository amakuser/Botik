import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "app-service" / "src"))

from botik_app_service.contracts.jobs import StartJobRequest
from botik_app_service.contracts.bootstrap import BootstrapPayload
from botik_app_service.contracts.errors import ErrorEnvelope
from botik_app_service.contracts.health import HealthResponse
from botik_app_service.contracts.logs import LogChannelSnapshot, LogEntry
from botik_app_service.contracts.models import ModelsReadSnapshot
from botik_app_service.contracts.runtime_status import RuntimeStatusSnapshot
from botik_app_service.contracts.futures import FuturesReadSnapshot
from botik_app_service.contracts.spot import SpotReadSnapshot
from botik_app_service.contracts.analytics import AnalyticsReadSnapshot
from botik_app_service.contracts.telegram import TelegramConnectivityCheckResult, TelegramOpsSnapshot


def test_contract_models_roundtrip():
    health = HealthResponse(status="ok", service="svc", version="1", session_id="abc")
    assert health.model_dump()["status"] == "ok"

    error = ErrorEnvelope(code="boom", message="failed")
    assert error.model_dump()["code"] == "boom"

    payload = BootstrapPayload.model_validate(
        {
            "app_name": "Botik Foundation",
            "version": "1",
            "session": {
                "session_id": "abc",
                "transport_base_url": "http://127.0.0.1:8765",
                "events_url": "http://127.0.0.1:8765/events",
            },
            "capabilities": {
                "desktop": True,
                "jobs": True,
                "routes": ["/", "/jobs", "/logs", "/runtime", "/spot", "/futures", "/telegram", "/analytics", "/models"],
            },
            "routes": ["/", "/jobs", "/logs", "/runtime", "/spot", "/futures", "/telegram", "/analytics", "/models"],
        }
    )
    assert payload.session.session_id == "abc"

    backfill_request = StartJobRequest.model_validate(
        {
            "job_type": "data_backfill",
            "payload": {
                "symbol": "BTCUSDT",
                "category": "spot",
                "intervals": ["1m"],
            },
        }
    )
    assert backfill_request.payload_dict()["intervals"] == ("1m",)

    integrity_request = StartJobRequest.model_validate(
        {
            "job_type": "data_integrity",
            "payload": {
                "symbol": "BTCUSDT",
                "category": "spot",
                "intervals": ["1m"],
            },
        }
    )
    assert integrity_request.payload_dict()["symbol"] == "BTCUSDT"

    snapshot = LogChannelSnapshot.model_validate(
        {
            "channel": "app",
            "entries": [
                {
                    "channel": "app",
                    "level": "INFO",
                    "message": "hello",
                    "source": "botik_app_service",
                }
            ],
            "truncated": False,
        }
    )
    assert isinstance(snapshot.entries[0], LogEntry)

    runtime_snapshot = RuntimeStatusSnapshot.model_validate(
        {
            "generated_at": "2026-04-11T10:00:00Z",
            "runtimes": [
                {
                    "runtime_id": "spot",
                    "label": "Spot Runtime",
                    "state": "running",
                    "pids": [1111],
                    "pid_count": 1,
                    "last_heartbeat_at": "2026-04-11T09:59:55Z",
                    "last_heartbeat_age_seconds": 5,
                    "last_error": None,
                    "last_error_at": None,
                    "status_reason": "process present with recent heartbeat activity",
                    "source_mode": "fixture",
                }
            ],
        }
    )
    assert runtime_snapshot.runtimes[0].runtime_id == "spot"

    futures_snapshot = FuturesReadSnapshot.model_validate(
        {
            "source_mode": "fixture",
            "summary": {
                "account_type": "UNIFIED",
                "positions_count": 1,
                "protected_positions_count": 1,
                "attention_positions_count": 0,
                "recovered_positions_count": 0,
                "open_orders_count": 1,
                "recent_fills_count": 1,
                "unrealized_pnl_total": 42.125,
            },
            "positions": [
                {
                    "account_type": "UNIFIED",
                    "symbol": "ETHUSDT",
                    "side": "Buy",
                    "position_idx": 1,
                    "margin_mode": "cross",
                    "leverage": 5.0,
                    "qty": 0.02,
                    "entry_price": 3000.0,
                    "mark_price": 3010.5,
                    "liq_price": 2500.0,
                    "unrealized_pnl": 42.125,
                    "take_profit": 3050.0,
                    "stop_loss": 2950.0,
                    "protection_status": "protected",
                    "source_of_truth": "fixture",
                    "recovered_from_exchange": False,
                    "strategy_owner": "futures_spike_reversal",
                    "updated_at_utc": "2026-04-11T12:00:00Z",
                }
            ],
            "active_orders": [
                {
                    "account_type": "UNIFIED",
                    "symbol": "ETHUSDT",
                    "side": "Sell",
                    "order_id": "fut-order-1",
                    "order_link_id": "fut-link-1",
                    "order_type": "Limit",
                    "time_in_force": "GTC",
                    "price": 3050.0,
                    "qty": 0.02,
                    "status": "New",
                    "reduce_only": True,
                    "close_on_trigger": False,
                    "strategy_owner": "futures_spike_reversal",
                    "updated_at_utc": "2026-04-11T12:00:00Z",
                }
            ],
            "recent_fills": [
                {
                    "account_type": "UNIFIED",
                    "symbol": "ETHUSDT",
                    "side": "Buy",
                    "exec_id": "fut-exec-1",
                    "order_id": "fut-order-1",
                    "order_link_id": "fut-link-1",
                    "price": 3001.0,
                    "qty": 0.02,
                    "exec_fee": 0.15,
                    "fee_currency": "USDT",
                    "is_maker": True,
                    "exec_time_ms": 1700000000123,
                    "created_at_utc": "2026-04-11T12:00:00Z",
                }
            ],
            "truncated": {
                "positions": False,
                "active_orders": False,
                "recent_fills": False,
            },
        }
    )
    assert futures_snapshot.summary.positions_count == 1

    spot_snapshot = SpotReadSnapshot.model_validate(
        {
            "source_mode": "fixture",
            "summary": {
                "account_type": "UNIFIED",
                "balance_assets_count": 1,
                "holdings_count": 1,
                "recovered_holdings_count": 0,
                "strategy_owned_holdings_count": 1,
                "open_orders_count": 1,
                "recent_fills_count": 1,
                "pending_intents_count": 1,
            },
            "balances": [
                {
                    "asset": "BTC",
                    "free_qty": 0.01,
                    "locked_qty": 0.0,
                    "total_qty": 0.01,
                    "source_of_truth": "fixture",
                    "updated_at_utc": "2026-04-11T12:00:00Z",
                }
            ],
            "holdings": [
                {
                    "account_type": "UNIFIED",
                    "symbol": "BTCUSDT",
                    "base_asset": "BTC",
                    "free_qty": 0.01,
                    "locked_qty": 0.0,
                    "total_qty": 0.01,
                    "avg_entry_price": 60000.0,
                    "hold_reason": "strategy_entry",
                    "source_of_truth": "fixture",
                    "recovered_from_exchange": False,
                    "strategy_owner": "spot_spread",
                    "auto_sell_allowed": False,
                    "updated_at_utc": "2026-04-11T12:00:00Z",
                }
            ],
            "active_orders": [
                {
                    "account_type": "UNIFIED",
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "order_id": "order-1",
                    "order_link_id": "link-1",
                    "order_type": "Limit",
                    "time_in_force": "PostOnly",
                    "price": 60000.0,
                    "qty": 0.01,
                    "filled_qty": 0.0,
                    "status": "New",
                    "strategy_owner": "spot_spread",
                    "updated_at_utc": "2026-04-11T12:00:00Z",
                }
            ],
            "recent_fills": [
                {
                    "account_type": "UNIFIED",
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "exec_id": "exec-1",
                    "order_id": "order-1",
                    "order_link_id": "link-1",
                    "price": 60000.0,
                    "qty": 0.01,
                    "fee": 0.02,
                    "fee_currency": "USDT",
                    "is_maker": True,
                    "exec_time_ms": 1700000000123,
                    "created_at_utc": "2026-04-11T12:00:00Z",
                }
            ],
            "truncated": {
                "balances": False,
                "holdings": False,
                "active_orders": False,
                "recent_fills": False,
            },
        }
    )
    assert spot_snapshot.summary.holdings_count == 1

    telegram_snapshot = TelegramOpsSnapshot.model_validate(
        {
            "source_mode": "fixture",
            "summary": {
                "bot_profile": "ops",
                "token_profile_name": "TELEGRAM_BOT_TOKEN",
                "token_configured": True,
                "internal_bot_disabled": False,
                "connectivity_state": "unknown",
                "connectivity_detail": "Use connectivity check to verify Telegram Bot API reachability.",
                "allowed_chat_count": 2,
                "allowed_chats_masked": ["12***34", "56***78"],
                "commands_count": 2,
                "alerts_count": 1,
                "errors_count": 1,
                "last_successful_send": "fixture alert delivered",
                "last_error": "fixture warning observed",
                "startup_status": "configured",
            },
            "recent_commands": [
                {
                    "ts": "2026-04-11T11:58:00Z",
                    "command": "/status",
                    "source": "telegram_bot",
                    "status": "ok",
                    "chat_id_masked": "12***34",
                    "username": "fixture_user",
                    "args": "",
                }
            ],
            "recent_alerts": [
                {
                    "ts": "2026-04-11T11:59:00Z",
                    "alert_type": "delivery",
                    "message": "fixture alert delivered",
                    "delivered": True,
                    "source": "telegram",
                    "status": "ok",
                }
            ],
            "recent_errors": [
                {
                    "ts": "2026-04-11T11:57:00Z",
                    "error": "fixture warning observed",
                    "source": "telegram",
                    "status": "warning",
                }
            ],
            "truncated": {
                "recent_commands": False,
                "recent_alerts": False,
                "recent_errors": False,
            },
        }
    )
    assert telegram_snapshot.summary.allowed_chat_count == 2

    telegram_check = TelegramConnectivityCheckResult.model_validate(
        {
            "source_mode": "fixture",
            "state": "healthy",
            "detail": "fixture connectivity check passed",
            "bot_username": "botik_fixture_bot",
            "latency_ms": 42.0,
            "error": None,
        }
    )
    assert telegram_check.state == "healthy"

    analytics_snapshot = AnalyticsReadSnapshot.model_validate(
        {
            "source_mode": "fixture",
            "summary": {
                "total_closed_trades": 4,
                "winning_trades": 3,
                "losing_trades": 1,
                "win_rate": 0.75,
                "total_net_pnl": 16.0,
                "average_net_pnl": 4.0,
                "today_net_pnl": 1.5,
            },
            "equity_curve": [
                {
                    "date": "2026-04-10",
                    "daily_pnl": 5.0,
                    "cumulative_pnl": 5.0,
                }
            ],
            "recent_closed_trades": [
                {
                    "symbol": "XRPUSDT",
                    "scope": "spot",
                    "net_pnl": 1.5,
                    "was_profitable": True,
                    "closed_at": "2026-04-11 12:00",
                }
            ],
            "truncated": {
                "equity_curve": False,
                "recent_closed_trades": False,
            },
        }
    )
    assert analytics_snapshot.summary.total_closed_trades == 4

    models_snapshot = ModelsReadSnapshot.model_validate(
        {
            "source_mode": "fixture",
            "summary": {
                "total_models": 3,
                "active_declared_count": 2,
                "ready_scopes": 2,
                "recent_training_runs_count": 2,
                "latest_run_scope": "futures",
                "latest_run_status": "running",
                "latest_run_mode": "online",
                "manifest_status": "loaded",
                "db_available": True,
            },
            "scopes": [
                {
                    "scope": "spot",
                    "active_model": "spot-champion-v3",
                    "checkpoint_name": "spot-champion-v3.pkl",
                    "latest_registry_model": "spot-challenger-v4",
                    "latest_registry_status": "candidate",
                    "latest_registry_created_at": "2026-04-11T10:00:00Z",
                    "latest_training_model_version": "spot-champion-v3",
                    "latest_training_status": "completed",
                    "latest_training_mode": "offline",
                    "latest_training_started_at": "2026-04-10T08:00:00Z",
                    "ready": True,
                    "status_reason": "Active model declared in active_models.yaml.",
                }
            ],
            "registry_entries": [
                {
                    "model_id": "spot-champion-v3",
                    "scope": "spot",
                    "status": "ready",
                    "quality_score": 0.81,
                    "policy": "hybrid",
                    "source_mode": "executed",
                    "artifact_name": "spot-champion-v3.pkl",
                    "created_at_utc": "2026-04-10T08:00:00Z",
                    "is_declared_active": True,
                }
            ],
            "recent_training_runs": [
                {
                    "run_id": "run-futures-1",
                    "scope": "futures",
                    "model_version": "futures-paper-v2",
                    "mode": "online",
                    "status": "running",
                    "is_trained": False,
                    "started_at_utc": "2026-04-11T09:30:00Z",
                    "finished_at_utc": "",
                }
            ],
            "truncated": {
                "registry_entries": False,
                "recent_training_runs": False,
            },
        }
    )
    assert models_snapshot.summary.total_models == 3
