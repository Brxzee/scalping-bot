"""Order block detection (last opposite candle before displacement)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from .atr import atr_series


@dataclass
class OrderBlock:
    """Demand (bullish) or supply (bearish) zone."""
    timestamp: pd.Timestamp
    direction: str  # bullish | bearish
    zone_high: float
    zone_low: float
    bar_index: int


def find_order_blocks(
    df: pd.DataFrame,
    displacement_bars: int = 2,
    body_atr_mult: float = 0.5,
    atr_period: int = 14,
) -> List[OrderBlock]:
    """
    Last opposite-bodied candle before a strong move.
    Bullish OB: last down candle before 2+ up candles with large bodies.
    Bearish OB: last up candle before 2+ down candles with large bodies.
    """
    out: List[OrderBlock] = []
    if len(df) < displacement_bars + 2:
        return out
    atr = atr_series(df["high"], df["low"], df["close"], atr_period)
    for i in range(1, len(df) - displacement_bars - 1):
        body = abs(df["close"].iloc[i] - df["open"].iloc[i])
        if pd.isna(atr.iloc[i]) or atr.iloc[i] <= 0:
            continue
        if body < body_atr_mult * atr.iloc[i]:
            continue
        # Bullish: candle i is down (close < open), then next displacement_bars are up and strong
        if df["close"].iloc[i] < df["open"].iloc[i]:
            up_count = 0
            for j in range(i + 1, min(i + 1 + displacement_bars, len(df))):
                if df["close"].iloc[j] > df["open"].iloc[j]:
                    up_count += 1
            if up_count >= displacement_bars:
                out.append(OrderBlock(
                    timestamp=df.index[i],
                    direction="bullish",
                    zone_high=float(df["high"].iloc[i]),
                    zone_low=float(df["low"].iloc[i]),
                    bar_index=i,
                ))
        # Bearish: candle i is up, then next displacement_bars are down
        if df["close"].iloc[i] > df["open"].iloc[i]:
            down_count = 0
            for j in range(i + 1, min(i + 1 + displacement_bars, len(df))):
                if df["close"].iloc[j] < df["open"].iloc[j]:
                    down_count += 1
            if down_count >= displacement_bars:
                out.append(OrderBlock(
                    timestamp=df.index[i],
                    direction="bearish",
                    zone_high=float(df["high"].iloc[i]),
                    zone_low=float(df["low"].iloc[i]),
                    bar_index=i,
                ))
    return out
