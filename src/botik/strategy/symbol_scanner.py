"""
Scanner worker helpers: picks active symbols for spread strategy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.botik.strategy.pair_admission import evaluate_pair_admission

if TYPE_CHECKING:
    from src.botik.config import AppConfig
    from src.botik.state.state import TradingState


@dataclass(frozen=True)
class SymbolScore:
    symbol: str
    score_bps: float
    reason: str


def pick_active_symbols(state: "TradingState", config: "AppConfig") -> tuple[list[str], dict[str, Any]]:
    """
    Evaluate symbols and return top-k PASS candidates.
    """
    summary: dict[str, Any] = {
        "universe_total": len(config.symbols),
        "pass": 0,
        "watch": 0,
        "reject": 0,
        "stale": 0,
        "selected": 0,
        "top_symbol": "",
        "top_score_bps": 0.0,
    }
    scores: list[SymbolScore] = []

    for symbol in config.symbols:
        decision = evaluate_pair_admission(symbol=symbol, state=state, config=config)
        status = decision.status.upper()
        if status == "PASS":
            summary["pass"] += 1
            metrics = decision.metrics
            score_bps = float(metrics.get("median_spread_bps", 0.0)) - float(metrics.get("min_required_spread_bps", 0.0))
            scores.append(SymbolScore(symbol=symbol, score_bps=score_bps, reason=decision.reason))
        elif status == "WATCH":
            summary["watch"] += 1
        else:
            summary["reject"] += 1
        if decision.stale_data:
            summary["stale"] += 1

    scores.sort(key=lambda s: s.score_bps, reverse=True)

    top_k = max(int(config.strategy.scanner_top_k), 1)
    selected_scores = scores[:top_k]
    selected = [s.symbol for s in selected_scores]
    summary["selected"] = len(selected)
    if selected_scores:
        summary["top_symbol"] = selected_scores[0].symbol
        summary["top_score_bps"] = selected_scores[0].score_bps

    return selected, summary
