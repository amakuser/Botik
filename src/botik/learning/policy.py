"""
Policy selector: ML-aware profile choice with bandit fallback.
"""
from __future__ import annotations

import random
import zlib
from typing import Any

import numpy as np

from src.botik.config import ActionProfileConfig
from src.botik.learning.bandit import GaussianThompsonBandit
from src.botik.learning.policy_manager import ModelBundle, predict_with_details


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _stable_hash_to_unit(text: str) -> float:
    raw = zlib.adler32(text.encode("utf-8")) & 0xFFFFFFFF
    return float(raw % 100000) / 100000.0


class PolicySelector:
    def __init__(self, bandit: GaussianThompsonBandit) -> None:
        self.bandit = bandit
        self._last_meta: dict[str, dict[str, Any]] = {}

    def _build_feature_row(
        self,
        symbol: str,
        snapshot: dict[str, Any],
        profile: ActionProfileConfig,
        model_version: str = "policy-ml",
    ) -> list[float]:
        return [
            _safe_float(snapshot.get("median_spread_bps")),
            _safe_float(snapshot.get("depth_bid_quote")),
            _safe_float(snapshot.get("depth_ask_quote")),
            _safe_float(snapshot.get("slippage_buy_bps")),
            _safe_float(snapshot.get("slippage_sell_bps")),
            _safe_float(snapshot.get("trades_per_min")),
            _safe_float(snapshot.get("p95_trade_gap_ms")),
            _safe_float(snapshot.get("vol_1s_bps")),
            _safe_float(snapshot.get("min_required_spread_bps")),
            # Use notional proxy from profile size and current top-of-book mid.
            _safe_float(profile.order_qty_base) * _safe_float(snapshot.get("mid")),
            _safe_float(profile.order_qty_base),
            _safe_float(profile.entry_tick_offset),
            _safe_float(profile.order_qty_base),
            _safe_float(profile.target_profit),
            _safe_float(profile.safety_buffer),
            _safe_float(profile.min_top_book_qty),
            _safe_float(profile.stop_loss_pct),
            _safe_float(profile.take_profit_pct),
            _safe_float(profile.hold_timeout_sec),
            1.0 if profile.maker_only or profile.maker_only is None else 0.0,
            1.0,  # side_sign: Buy proxy for entry decision
            _stable_hash_to_unit(symbol),
            _stable_hash_to_unit(profile.profile_id),
            _stable_hash_to_unit(model_version),
            _safe_float(snapshot.get("impulse_bps")),
            _safe_float(snapshot.get("spike_direction")),
            _safe_float(snapshot.get("spike_strength_bps")),
        ]

    def get_last_selection_meta(self) -> dict[str, dict[str, Any]]:
        return {k: dict(v) for k, v in self._last_meta.items()}

    def select(
        self,
        pass_symbols: list[str],
        profiles: list[ActionProfileConfig],
        ctx: dict[str, dict[str, Any]],
        model: ModelBundle | None,
        eps: float,
    ) -> dict[str, str]:
        self._last_meta = {}
        profile_list = [p for p in profiles if p.profile_id and p.profile_id.strip()]
        if not pass_symbols:
            return {}
        if not profile_list:
            out = self.bandit.select(pass_symbols, ctx=ctx)
            for symbol, profile_id in out.items():
                self._last_meta[symbol] = {
                    "policy_used": "Bandit",
                    "profile_id": profile_id,
                    "pred_open_prob": None,
                    "pred_exp_edge_bps": None,
                    "active_model_id": None,
                    "reason": "no_profiles",
                }
            return out

        eps = min(max(float(eps), 0.0), 1.0)
        if model is None:
            out = self.bandit.select(pass_symbols, ctx=ctx)
            for symbol, profile_id in out.items():
                self._last_meta[symbol] = {
                    "policy_used": "Bandit",
                    "profile_id": profile_id,
                    "pred_open_prob": None,
                    "pred_exp_edge_bps": None,
                    "active_model_id": None,
                    "reason": "model_unavailable",
                }
            return out

        selected: dict[str, str] = {}
        for symbol in pass_symbols:
            snapshot = ctx.get(symbol) or {}
            if random.random() < eps:
                picked = random.choice(profile_list)
                selected[symbol] = picked.profile_id
                self._last_meta[symbol] = {
                    "policy_used": "ML",
                    "profile_id": picked.profile_id,
                    "pred_open_prob": None,
                    "pred_exp_edge_bps": None,
                    "active_model_id": model.model_id,
                    "reason": "epsilon_explore",
                }
                continue

            rows = [self._build_feature_row(symbol, snapshot, p, model.model_id) for p in profile_list]
            matrix = np.array(rows, dtype=float)
            open_prob, exp_edge = predict_with_details(model, matrix)
            score = exp_edge + (open_prob * 0.01)
            idx = int(np.argmax(score))
            chosen = profile_list[idx]
            selected[symbol] = chosen.profile_id
            self._last_meta[symbol] = {
                "policy_used": "ML",
                "profile_id": chosen.profile_id,
                "pred_open_prob": float(open_prob[idx]),
                "pred_exp_edge_bps": float(exp_edge[idx]),
                "active_model_id": model.model_id,
                "reason": "model_argmax",
            }
        return selected

    def update_reward(self, signal_id: str, reward_bps: float) -> None:
        self.bandit.update(signal_id=signal_id, reward_bps=reward_bps)
