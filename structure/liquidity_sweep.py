"""Liquidity sweep detection (break of swing then close back)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from .swing import SwingLevel, find_swing_highs_lows


@dataclass
class LiquiditySweep:
    """Sweep of highs (bearish) or lows (bullish)."""
    timestamp: pd.Timestamp
    direction: str  # sweep_highs (bearish) | sweep_lows (bullish)
    level: float
    bar_index: int


def find_liquidity_sweeps(
    df: pd.DataFrame,
    swing_lookback: int = 5,
    threshold_pct: float = 0.02,
) -> List[LiquiditySweep]:
    """
    Sweep of highs: price breaks above swing high by threshold then closes below it.
    Sweep of lows: price breaks below swing low then closes above it.
    """
    out: List[LiquiditySweep] = []
    swing_highs, swing_lows = find_swing_highs_lows(df, lookback=swing_lookback)
    if not swing_highs and not swing_lows:
        return out
    # Build recent levels (last N bars)
    for i in range(swing_lookback * 2, len(df) - 2):
        bar_high = df["high"].iloc[i]
        bar_low = df["low"].iloc[i]
        close_i = df["close"].iloc[i]
        next_high = df["high"].iloc[i + 1]
        next_low = df["low"].iloc[i + 1]
        next_close = df["close"].iloc[i + 1]
        for sh in swing_highs:
            if sh.bar_index >= i:
                continue
            level = sh.price
            thresh = level * (1 + threshold_pct)
            # Some bar breaks above level then closes back below
            if next_high >= thresh and next_close < level:
                out.append(LiquiditySweep(
                    timestamp=df.index[i + 1],
                    direction="sweep_highs",
                    level=level,
                    bar_index=i + 1,
                ))
                break
        for sl in swing_lows:
            if sl.bar_index >= i:
                continue
            level = sl.price
            thresh = level * (1 - threshold_pct)
            if next_low <= thresh and next_close > level:
                out.append(LiquiditySweep(
                    timestamp=df.index[i + 1],
                    direction="sweep_lows",
                    level=level,
                    bar_index=i + 1,
                ))
                break
    return out
