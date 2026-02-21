"""Tests for RuleEngine and storage."""
import os
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stats import storage
from stats.rule_engine import RuleEngine


def test_storage_record_and_today():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = f.name
    try:
        storage.record_trade(db, "BTCUSDT", "MAStrategy", "Buy", 0.001, 40000.0, pnl=10.0)
        storage.record_trade(db, "BTCUSDT", "MAStrategy", "Sell", 0.001, 40100.0, pnl=-5.0)
        pnl = storage.get_today_pnl(db)
        count = storage.get_today_trade_count(db)
        assert count == 2
        assert pnl == 5.0  # 10 - 5
    finally:
        if os.path.exists(db):
            os.unlink(db)


def test_rule_engine_blocks_on_limit():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = f.name
    try:
        engine = RuleEngine(db, {"max_trades": 2, "max_loss": 100})
        allowed, _ = engine.can_open_trade("BTCUSDT", "MA")
        assert allowed is True
        storage.record_trade(db, "BTCUSDT", "MA", "Buy", 0.001, 40000.0, pnl=0)
        storage.record_trade(db, "BTCUSDT", "MA", "Sell", 0.001, 40000.0, pnl=0)
        allowed, reason = engine.can_open_trade("BTCUSDT", "MA")
        assert allowed is False
        assert "trade limit" in reason.lower()
    finally:
        if os.path.exists(db):
            os.unlink(db)
