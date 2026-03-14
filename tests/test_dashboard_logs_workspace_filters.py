from __future__ import annotations

from src.botik.gui.app import (
    dashboard_log_matches_filters,
    detect_dashboard_log_channel,
    detect_dashboard_log_instrument,
    detect_dashboard_log_level,
    detect_dashboard_log_pair,
)


def test_detect_dashboard_log_metadata_classifies_channels_and_instruments() -> None:
    assert detect_dashboard_log_channel("[spot] refreshed BTCUSDT holding") == "spot"
    assert detect_dashboard_log_channel("[futures-paper] paper session result") == "futures_paper"
    assert detect_dashboard_log_channel("[telegram-workspace] reload failed") == "telegram"
    assert detect_dashboard_log_channel("[models] promoted champion") == "models"
    assert detect_dashboard_log_channel("[reconciliation] issue resolved") == "ops"

    assert detect_dashboard_log_instrument("[spot] refreshed BTCUSDT holding") == "spot"
    assert detect_dashboard_log_instrument("[futures-paper] paper session result") == "futures"
    assert detect_dashboard_log_instrument("[telegram-workspace] reload failed") == "telegram"
    assert detect_dashboard_log_instrument("[models] promoted champion") == "models"
    assert detect_dashboard_log_instrument("[reconciliation] issue resolved") == "ops"

    assert detect_dashboard_log_level("[spot] WARNING stale holding") == "WARNING"
    assert detect_dashboard_log_pair("[spot] BTCUSDT refreshed") == "BTCUSDT"


def test_dashboard_log_matches_filters_respects_channel_instrument_level_and_query() -> None:
    line = "[futures-paper] ERROR ETHUSDT paper result closed with loss"

    assert dashboard_log_matches_filters(
        line,
        level_filter="ERROR",
        pair_filter="ETHUSDT",
        channel_filter="futures_paper",
        instrument_filter="futures",
        query_filter="loss",
    ) is True

    assert dashboard_log_matches_filters(
        line,
        level_filter="WARNING",
        pair_filter="ETHUSDT",
        channel_filter="futures_paper",
        instrument_filter="futures",
        query_filter="loss",
    ) is False

    assert dashboard_log_matches_filters(
        line,
        level_filter="ERROR",
        pair_filter="BTCUSDT",
        channel_filter="futures_paper",
        instrument_filter="futures",
        query_filter="loss",
    ) is False

    assert dashboard_log_matches_filters(
        line,
        level_filter="ERROR",
        pair_filter="ETHUSDT",
        channel_filter="telegram",
        instrument_filter="futures",
        query_filter="loss",
    ) is False

    assert dashboard_log_matches_filters(
        line,
        level_filter="ERROR",
        pair_filter="ETHUSDT",
        channel_filter="futures_paper",
        instrument_filter="spot",
        query_filter="loss",
    ) is False


def test_dashboard_log_matches_filters_safe_all_fallback() -> None:
    line = "[ui] INFO refreshed dashboard snapshot"
    assert dashboard_log_matches_filters(
        line,
        level_filter="ALL",
        pair_filter="ALL",
        channel_filter="ALL",
        instrument_filter="ALL",
        query_filter="",
    ) is True
