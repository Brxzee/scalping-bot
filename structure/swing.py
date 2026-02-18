"""Swing high/low detection for context and key levels."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd


@dataclass
class SwingLevel:
    """A swing high or low."""
    timestamp: pd.Timestamp
    price: float
    is_high: bool
    bar_index: int


def find_swing_highs_lows(
    df: pd.DataFrame,
    lookback: int = 5,
) -> tuple[List[SwingLevel], List[SwingLevel]]:
    """
    Local extrema: swing high when high[i] is max in window; swing low when low[i] is min.
    Returns (swing_highs, swing_lows).
    """
    if len(df) < lookback * 2 + 1:
        return [], []
    highs = df["high"]
    lows = df["low"]
    swing_highs: List[SwingLevel] = []
    swing_lows: List[SwingLevel] = []
    for i in range(lookback, len(df) - lookback):
        window_high = highs.iloc[i - lookback : i + lookback + 1]
        if highs.iloc[i] == window_high.max():
            swing_highs.append(SwingLevel(
                timestamp=df.index[i],
                price=float(highs.iloc[i]),
                is_high=True,
                bar_index=i,
            ))
        window_low = lows.iloc[i - lookback : i + lookback + 1]
        if lows.iloc[i] == window_low.min():
            swing_lows.append(SwingLevel(
                timestamp=df.index[i],
                price=float(lows.iloc[i]),
                is_high=False,
                bar_index=i,
            ))
    return swing_highs, swing_lows
