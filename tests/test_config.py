"""Tests for config loading and daily limits."""
import os
import tempfile
from pathlib import Path

import pytest

# Add project root
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import load_config, get_daily_limits, get_bybit_settings


def test_load_config_from_file():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        f.write(b"""
bybit:
  api_key: test
  testnet: true
daily_limits:
  max_loss: 50
  max_trades: 10
execution_mode: sync
dry_run: true
""")
        path = f.name
    try:
        config = load_config(path)
        assert config["dry_run"] is True
        assert config["execution_mode"] == "sync"
        limits = get_daily_limits(config)
        assert limits["max_loss"] == 50
        assert limits["max_trades"] == 10
        bybit = get_bybit_settings(config)
        assert bybit["api_key"] == "test"
        assert bybit["testnet"] is True
    finally:
        os.unlink(path)


def test_get_daily_limits_defaults():
    config = {}
    limits = get_daily_limits(config)
    assert "max_loss" in limits
    assert "max_trades" in limits
