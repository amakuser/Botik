from __future__ import annotations

from pathlib import Path

from src.botik.gui.app import build_dashboard_ops_workspace_sections


def test_build_dashboard_ops_workspace_sections_formats_operational_cards(tmp_path: Path) -> None:
    db_path = tmp_path / "botik_runtime.db"
    db_path.write_text("", encoding="utf-8")
    sections = build_dashboard_ops_workspace_sections(
        ops_status={
            "reconciliation_last_status": "success",
            "reconciliation_last_timestamp": "2026-03-14T12:00:00Z",
            "reconciliation_last_trigger": "startup",
            "reconciliation_open_issues": 2,
            "reconciliation_resolved_issues": 5,
            "reconciliation_lock_symbols": ["BTCUSDT", "ETHUSDT"],
            "futures_protection_line": "protected=2 | pending=1",
            "futures_risk_telemetry_line": "funding=ETHUSDT fee=0.001000 | liq=BTCUSDT dist=120.00bps",
            "spot_holdings_freshness": "2026-03-14 11:59:00",
            "futures_positions_freshness": "2026-03-14 11:58:00",
            "futures_orders_freshness": "2026-03-14 11:57:00",
            "reconciliation_issues_freshness": "2026-03-14 11:56:00",
            "futures_funding_freshness": "2026-03-14 11:55:00",
            "futures_liq_snapshots_freshness": "2026-03-14 11:54:00",
        },
        runtime_caps={"reconciliation": "supported", "protection": "supported"},
        trading_state="running",
        running_modes=["spot_spread"],
        ml_state="running",
        telegram_state="running",
        db_path=db_path,
    )

    assert "trading=running (spot_spread)" in sections["service_health_line"]
    assert "ml=running" in sections["service_health_line"]
    assert "telegram=running" in sections["service_health_line"]
    assert "status=success" in sections["reconciliation_line"]
    assert "issues open=2 resolved=5" in sections["reconciliation_line"]
    assert "locks=BTCUSDT,ETHUSDT" in sections["reconciliation_line"]
    assert "protected=2 | pending=1" in sections["protection_line"]
    assert "funding=ETHUSDT" in sections["protection_line"]
    assert "db=ok (botik_runtime.db)" in sections["db_health_line"]
    assert "reconciliation=supported" in sections["capabilities_line"]
    assert "protection=supported" in sections["capabilities_line"]


def test_build_dashboard_ops_workspace_sections_safe_fallbacks() -> None:
    sections = build_dashboard_ops_workspace_sections(
        ops_status={},
        runtime_caps={},
        trading_state="stopped",
        running_modes=[],
        ml_state="stopped",
        telegram_state="stopped",
        db_path=Path("missing.db"),
    )
    assert "trading=stopped (-)" in sections["service_health_line"]
    assert "status=skipped" in sections["reconciliation_line"]
    assert "locks=-" in sections["reconciliation_line"]
    assert "none | funding=none | liq=none" in sections["protection_line"]
    assert "db=missing (missing.db)" in sections["db_health_line"]
    assert "reconciliation=unknown" in sections["capabilities_line"]
