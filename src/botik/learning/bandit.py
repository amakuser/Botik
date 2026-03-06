"""
Context-aware Gaussian Thompson Sampling bandit for action-profile selection.
"""
from __future__ import annotations

import math
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ArmState:
    n: int
    mean: float
    m2: float


class GaussianThompsonBandit:
    def __init__(
        self,
        conn: sqlite3.Connection,
        profile_ids: list[str],
        epsilon: float = 0.05,
        prior_std: float = 3.0,
    ) -> None:
        self.conn = conn
        unique_profiles = [p.strip() for p in profile_ids if p and p.strip()]
        self.profile_ids = unique_profiles if unique_profiles else ["default"]
        self.epsilon = min(max(float(epsilon), 0.0), 1.0)
        self.prior_std = max(float(prior_std), 0.01)

    def _load_state(self, symbol: str, profile_id: str) -> ArmState:
        row = self.conn.execute(
            """
            SELECT n, mean, m2
            FROM bandit_state
            WHERE symbol = ? AND profile_id = ?
            LIMIT 1
            """,
            (symbol, profile_id),
        ).fetchone()
        if not row:
            return ArmState(n=0, mean=0.0, m2=0.0)
        return ArmState(
            n=max(int(row[0] or 0), 0),
            mean=float(row[1] or 0.0),
            m2=float(row[2] or 0.0),
        )

    def _upsert_state(self, symbol: str, profile_id: str, state: ArmState) -> None:
        self.conn.execute(
            """
            INSERT INTO bandit_state (symbol, profile_id, n, mean, m2, updated_at_utc)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, profile_id) DO UPDATE SET
                n=excluded.n,
                mean=excluded.mean,
                m2=excluded.m2,
                updated_at_utc=excluded.updated_at_utc
            """,
            (symbol, profile_id, state.n, state.mean, state.m2, _utc_now_iso()),
        )
        self.conn.commit()

    def select(
        self,
        pass_symbols: list[str],
        ctx: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, str]:
        selected: dict[str, str] = {}
        context = ctx or {}
        for symbol in pass_symbols:
            if len(self.profile_ids) == 1:
                selected[symbol] = self.profile_ids[0]
                continue

            if random.random() < self.epsilon:
                selected[symbol] = random.choice(self.profile_ids)
                continue

            best_profile = self.profile_ids[0]
            best_score = -10**9
            spread_bps = float((context.get(symbol) or {}).get("median_spread_bps", 0.0))
            spread_adjust = min(max(spread_bps, -25.0), 25.0) * 0.01
            for profile_id in self.profile_ids:
                state = self._load_state(symbol, profile_id)
                if state.n < 2:
                    sigma = self.prior_std
                else:
                    variance = max(state.m2 / max(state.n - 1, 1), 1e-6)
                    sigma = math.sqrt(variance / max(state.n, 1))
                sampled = random.gauss(state.mean, sigma) + spread_adjust
                if sampled > best_score:
                    best_score = sampled
                    best_profile = profile_id
            selected[symbol] = best_profile
        return selected

    def update(self, signal_id: str, reward_bps: float | None) -> None:
        if reward_bps is None:
            return
        row = self.conn.execute(
            """
            SELECT symbol, profile_id
            FROM signals
            WHERE signal_id = ?
            LIMIT 1
            """,
            (signal_id,),
        ).fetchone()
        if not row:
            return
        symbol = str(row[0] or "").upper().strip()
        profile_id = str(row[1] or "").strip()
        if not symbol:
            return
        if not profile_id:
            profile_id = self.profile_ids[0]
        self.update_arm(symbol, profile_id, reward_bps)

    def update_arm(self, symbol: str, profile_id: str, reward_bps: float) -> None:
        state = self._load_state(symbol=symbol, profile_id=profile_id)
        n1 = state.n + 1
        delta = float(reward_bps) - state.mean
        mean1 = state.mean + (delta / n1)
        m2_1 = state.m2 + delta * (float(reward_bps) - mean1)
        self._upsert_state(symbol, profile_id, ArmState(n=n1, mean=mean1, m2=m2_1))

