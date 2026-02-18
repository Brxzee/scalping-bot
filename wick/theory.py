"""
Powell Trades wick theory: significant wicks, 50% midpoint, respect/disrespect.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from structure import find_swing_highs_lows, atr_series


@dataclass
class WickEvent:
    """A significant wick with 50% midpoint and optional respect/disrespect."""
    timestamp: pd.Timestamp
    direction: str  # bullish (lower wick) | bearish (upper wick)
    midpoint: float
    wick_high: float
    wick_low: float
    bar_index: int
    respect: Optional[bool] = None  # True = respect (reversal), False = disrespect
    swing_bar_index: Optional[int] = None


def find_wick_events(
    df: pd.DataFrame,
    wick_to_body_ratio_min: float = 2.0,
    body_to_range_max: float = 0.5,
    atr_min_mult: float = 0.3,
    respect_bars_lookback: int = 10,
    swing_lookback: int = 5,
    atr_period: int = 14,
) -> List[WickEvent]:
    """
    Find significant wicks at swing levels; compute 50% midpoint; determine respect/disrespect.
    """
    events: List[WickEvent] = []
    if len(df) < 3:
        return events
    swing_highs, swing_lows = find_swing_highs_lows(df, lookback=swing_lookback)
    atr = atr_series(df["high"], df["low"], df["close"], atr_period)
    swing_high_indices = {s.bar_index for s in swing_highs}
    swing_low_indices = {s.bar_index for s in swing_lows}

    for i in range(1, len(df) - 1):
        o, h, l, c = df["open"].iloc[i], df["high"].iloc[i], df["low"].iloc[i], df["close"].iloc[i]
        body = abs(c - o)
        body_bottom = min(o, c)
        body_top = max(o, c)
        wick_upper = h - body_top
        wick_lower = body_bottom - l
        full_range = h - l
        if full_range <= 0:
            continue
        atr_val = atr.iloc[i] if i < len(atr) else None
        if atr_val is not None and atr_val > 0 and atr_min_mult > 0:
            min_wick_size = atr_min_mult * atr_val
        else:
            min_wick_size = 0

        # Lower wick (bullish) - at or near swing low
        near_swing_low = i in swing_low_indices or any(
            abs(i - s.bar_index) <= swing_lookback * 2 for s in swing_lows
        )
        if wick_lower >= wick_to_body_ratio_min * body and wick_lower >= min_wick_size and near_swing_low:
            if body_to_range_max and body / full_range > body_to_range_max:
                continue  # skip if we require pin-bar and this is not
            midpoint = l + (body_bottom - l) * 0.5
            ev = WickEvent(
                timestamp=df.index[i],
                direction="bullish",
                midpoint=midpoint,
                wick_high=h,
                wick_low=l,
                bar_index=i,
                swing_bar_index=i if i in swing_low_indices else None,
            )
            for j in range(i + 1, min(i + 1 + respect_bars_lookback, len(df))):
                close_j = df["close"].iloc[j]
                if close_j < midpoint:
                    ev.respect = False
                    break
                if close_j > body_top:
                    ev.respect = True
                    break
            events.append(ev)

        # Upper wick (bearish) - at or near swing high
        near_swing_high = i in swing_high_indices or any(
            abs(i - s.bar_index) <= swing_lookback * 2 for s in swing_highs
        )
        if wick_upper >= wick_to_body_ratio_min * body and wick_upper >= min_wick_size and near_swing_high:
            if body_to_range_max and body / full_range > body_to_range_max:
                continue
            midpoint = body_top + (h - body_top) * 0.5
            ev = WickEvent(
                timestamp=df.index[i],
                direction="bearish",
                midpoint=midpoint,
                wick_high=h,
                wick_low=l,
                bar_index=i,
                swing_bar_index=i if i in swing_high_indices else None,
            )
            for j in range(i + 1, min(i + 1 + respect_bars_lookback, len(df))):
                close_j = df["close"].iloc[j]
                if close_j > midpoint:
                    ev.respect = False
                    break
                if close_j < body_bottom:
                    ev.respect = True
                    break
            events.append(ev)

    return events
