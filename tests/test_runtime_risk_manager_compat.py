from __future__ import annotations

from pathlib import Path

from src.botik.config import AppConfig, load_config
from src.botik.main import resolve_risk_leverage
from src.botik.risk.manager import RiskManager


def test_load_config_has_safe_default_leverage_when_missing(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                "execution:",
                "  mode: paper",
                "risk:",
                "  initial_equity_usdt: 10000",
                "  max_total_exposure_pct_of_initial: 2.0",
            ]
        ),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    assert cfg.risk.default_leverage == 1.0


def test_main_to_risk_manager_linear_call_path_uses_leverage() -> None:
    cfg = AppConfig.model_validate(
        {
            "bybit": {"market_category": "linear"},
            "risk": {"default_leverage": 5.0},
        }
    )
    risk_manager = RiskManager(cfg.risk)
    leverage = resolve_risk_leverage(cfg, cfg.bybit.market_category)
    assert leverage == 5.0

    result = risk_manager.check_order(
        symbol="BTCUSDT",
        side="Buy",
        price=50000.0,
        qty=0.001,  # $50 x 5 = $250 effective exposure
        current_total_exposure_usdt=0.0,
        current_symbol_exposure_usdt=0.0,
        current_open_positions=0,
        leverage=leverage,
    )
    assert result.allowed is False
    assert "total_exposure" in result.reason


def test_main_leverage_resolver_falls_back_to_1x_on_invalid_value() -> None:
    cfg = AppConfig.model_validate({"bybit": {"market_category": "linear"}})
    cfg.risk.__dict__["default_leverage"] = "bad-value"
    leverage = resolve_risk_leverage(cfg, cfg.bybit.market_category)
    assert leverage == 1.0
