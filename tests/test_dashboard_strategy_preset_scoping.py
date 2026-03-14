from __future__ import annotations

from src.botik.gui.app import dashboard_strategy_preset_labels, filter_dashboard_strategy_modes


def test_dashboard_strategy_preset_labels_are_scoped_by_instrument() -> None:
    assert dashboard_strategy_preset_labels("spot") == [
        "Spot Spread (Maker)",
        "Spot Spike Burst",
    ]
    assert dashboard_strategy_preset_labels("futures") == ["Futures Spike Reversal"]



def test_filter_dashboard_strategy_modes_keeps_spot_actions_spot_only() -> None:
    modes = ["spot_spread", "spot_spike", "futures_spike_reversal"]
    assert filter_dashboard_strategy_modes(modes, "spot") == ["spot_spread", "spot_spike"]
    assert filter_dashboard_strategy_modes(modes, "futures") == ["futures_spike_reversal"]
