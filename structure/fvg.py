"""Fair Value Gap detection (ICT)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd


@dataclass
class FVG:
    """Bullish or bearish fair value gap."""
    timestamp: pd.Timestamp
    direction: str  # bullish | bearish
    zone_high: float
    zone_low: float
    bar_index: int


def find_fvgs(df: pd.DataFrame) -> List[FVG]:
    """
    Bullish FVG: low(candle_1) > high(candle_3).
    Bearish FVG: high(candle_1) < low(candle_3).
    Candle indices: 0 = first, 1 = middle, 2 = last (so 1 is the gap candle).
    """
    out: List[FVG] = []
    if len(df) < 3:
        return out
    for i in range(len(df) - 2):
        l1, h1 = df["low"].iloc[i], df["high"].iloc[i]
        l2, h2 = df["low"].iloc[i + 1], df["high"].iloc[i + 1]
        l3, h3 = df["low"].iloc[i + 2], df["high"].iloc[i + 2]
        if l1 > h3:
            out.append(FVG(
                timestamp=df.index[i + 1],
                direction="bullish",
                zone_high=l1,
                zone_low=h3,
                bar_index=i + 1,
            ))
        if h1 < l3:
            out.append(FVG(
                timestamp=df.index[i + 1],
                direction="bearish",
                zone_high=l3,
                zone_low=h1,
                bar_index=i + 1,
            ))
    return out
