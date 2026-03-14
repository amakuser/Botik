from __future__ import annotations

from src.botik.gui.app import build_dashboard_home_instrument_sections, filter_dashboard_strategy_modes


def test_filter_dashboard_strategy_modes_keeps_instruments_independent() -> None:
    modes = ["spot_spread", "spot_spike", "futures_spike_reversal"]
    assert filter_dashboard_strategy_modes(modes, "spot") == ["spot_spread", "spot_spike"]
    assert filter_dashboard_strategy_modes(modes, "futures") == ["futures_spike_reversal"]


def test_build_dashboard_home_instrument_sections_formats_spot_and_futures_blocks() -> None:
    sections = build_dashboard_home_instrument_sections(
        raw_cfg={
            "strategy": {
                "take_profit_pct": 0.004,
                "stop_loss_pct": 0.002,
                "max_order_notional_usdt": 25,
                "min_active_position_usdt": 1.5,
                "bandit_enabled": False,
            },
            "ml": {"mode": "online"},
        },
        release_manifest={
            "active_spot_model_version": "spot-model-v3",
            "active_futures_model_version": "fut-model-v8",
            "spot_runtime_version": "1.0.0",
            "futures_training_engine_version": "0.1.1",
        },
        spot_workspace={
            "holdings_count": 4,
            "open_orders_count": 2,
            "recovered_holdings_count": 1,
            "stale_holdings_count": 1,
            "manual_holdings_count": 1,
        },
        futures_training_workspace={
            "training_runtime_status": "running",
            "best_checkpoint": "fut-model-v8",
        },
        futures_paper_workspace={
            "closed_results_count": 5,
            "good_results_count": 3,
            "bad_results_count": 2,
            "positions_count": 1,
            "open_orders_count": 1,
            "net_pnl_total": 1.2345,
        },
        exec_mode="paper",
    )

    assert "active_holdings=4" in sections["spot_primary_line"]
    assert "current_mode=paper" in sections["spot_primary_line"]
    assert "active_model=spot-model-v3" in sections["spot_primary_line"]
    assert "runtime=1.0.0" in sections["spot_meta_line"]
    assert "policy=Model-driven" in sections["spot_meta_line"]
    assert "hard_rules=off" in sections["spot_settings_line"]
    assert "training_source=Paper only" in sections["spot_settings_line"]
    assert "dust_threshold=1.5" in sections["spot_settings_line"]

    assert "training_status=running" in sections["futures_primary_line"]
    assert "paper_results=5" in sections["futures_primary_line"]
    assert "good=3 bad=2" in sections["futures_primary_line"]
    assert "active_model=fut-model-v8" in sections["futures_primary_line"]
    assert "net_pnl=1.234500" in sections["futures_meta_line"]
    assert "best_checkpoint=fut-model-v8" in sections["futures_meta_line"]
    assert "training_source=Paper only" in sections["futures_settings_line"]


def test_build_dashboard_home_instrument_sections_safe_fallbacks() -> None:
    sections = build_dashboard_home_instrument_sections(
        raw_cfg={},
        release_manifest={},
        spot_workspace={},
        futures_training_workspace={},
        futures_paper_workspace={},
        exec_mode="paper",
    )
    assert "active_holdings=0" in sections["spot_primary_line"]
    assert "active_model=unknown" in sections["spot_primary_line"]
    assert "runtime=unknown" in sections["spot_meta_line"]
    assert "hard_rules=off" in sections["spot_settings_line"]
    assert "training_status=unknown" in sections["futures_primary_line"]
    assert "paper_results=0" in sections["futures_primary_line"]
    assert "net_pnl=0.000000" in sections["futures_meta_line"]
