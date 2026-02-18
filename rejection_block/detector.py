"""
ICT rejection block: strong wick at key level (OB, FVG, liquidity, swing).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from structure import (
    find_swing_highs_lows,
    find_fvgs,
    find_order_blocks,
    find_liquidity_sweeps,
    atr_series,
)


@dataclass
class RejectionBlock:
    """Single rejection block: the rejection candle defines entry zone and stop."""
    timestamp: pd.Timestamp
    direction: str  # bullish | bearish
    zone_high: float   # Entry zone (body boundary)
    zone_low: float    # Entry zone (wick extreme)
    candle_high: float # Full rejection candle high (stop for short)
    candle_low: float  # Full rejection candle low (stop for long)
    bar_index: int
    key_levels_nearby: List[str]
    reversal_confirmed: bool  # Close beyond rejection candle = valid entry
    volume_ok: bool


def _zone_near_price(zone_high: float, zone_low: float, price: float, pct: float) -> bool:
    mid = (zone_high + zone_low) / 2
    return abs(price - mid) <= mid * pct if mid else False


def _zone_overlaps(high1: float, low1: float, high2: float, low2: float, pct: float) -> bool:
    mid1 = (high1 + low1) / 2
    dist = mid1 * pct if mid1 else 0
    return not (high1 + dist < low2 or low1 - dist > high2)


def find_rejection_blocks(
    df: pd.DataFrame,
    wick_to_body_ratio_min: float = 2.0,
    reversal_confirmation_bars: int = 3,
    key_level_proximity_pct: float = 0.001,
    volume_above_avg_mult: float = 1.0,
    swing_lookback: int = 5,
    atr_period: int = 14,
    # Structure params passed through
    ob_displacement_bars: int = 2,
    ob_body_atr_mult: float = 0.5,
    sweep_threshold_pct: float = 0.02,
) -> List[RejectionBlock]:
    """
    Candles with long wick (bullish = lower wick, bearish = upper wick),
    tagged with nearby key levels; optional reversal and volume confirmation.
    """
    out: List[RejectionBlock] = []
    if len(df) < 4:
        return out
    swing_highs, swing_lows = find_swing_highs_lows(df, lookback=swing_lookback)
    fvgs = find_fvgs(df)
    obs = find_order_blocks(
        df,
        displacement_bars=ob_displacement_bars,
        body_atr_mult=ob_body_atr_mult,
        atr_period=atr_period,
    )
    sweeps = find_liquidity_sweeps(df, swing_lookback=swing_lookback, threshold_pct=sweep_threshold_pct)
    atr = atr_series(df["high"], df["low"], df["close"], atr_period)
    vol = df["volume"] if "volume" in df.columns else pd.Series(1.0, index=df.index)
    vol_avg = vol.rolling(20).mean()

    for i in range(1, len(df) - reversal_confirmation_bars):
        o, h, l, c = df["open"].iloc[i], df["high"].iloc[i], df["low"].iloc[i], df["close"].iloc[i]
        body = abs(c - o)
        body_bottom = min(o, c)
        body_top = max(o, c)
        wick_upper = h - body_top
        wick_lower = body_bottom - l

        # Pick dominant wick: one RB per candle (longer wick wins)
        bullish_ok = wick_lower >= wick_to_body_ratio_min * body
        bearish_ok = wick_upper >= wick_to_body_ratio_min * body
        if not bullish_ok and not bearish_ok:
            continue
        if bullish_ok and bearish_ok:
            direction = "bearish" if wick_upper >= wick_lower else "bullish"
        else:
            direction = "bullish" if bullish_ok else "bearish"

        if direction == "bullish":
            zone_high = body_bottom
            zone_low = l
        else:
            zone_high = h
            zone_low = body_top

        key_levels: List[str] = []
        if direction == "bullish":
            for sl in swing_lows:
                if _zone_near_price(zone_high, zone_low, sl.price, key_level_proximity_pct):
                    key_levels.append("swing_low")
                    break
            for f in fvgs:
                if f.direction == "bullish" and _zone_overlaps(zone_high, zone_low, f.zone_high, f.zone_low, key_level_proximity_pct):
                    key_levels.append("fvg")
                    break
            for ob in obs:
                if ob.direction == "bullish" and _zone_overlaps(zone_high, zone_low, ob.zone_high, ob.zone_low, key_level_proximity_pct):
                    key_levels.append("order_block")
                    break
            for sw in sweeps:
                if sw.direction == "sweep_lows" and _zone_near_price(zone_high, zone_low, sw.level, key_level_proximity_pct):
                    key_levels.append("liquidity_sweep")
                    break
        else:
            for sh in swing_highs:
                if _zone_near_price(zone_high, zone_low, sh.price, key_level_proximity_pct):
                    key_levels.append("swing_high")
                    break
            for f in fvgs:
                if f.direction == "bearish" and _zone_overlaps(zone_high, zone_low, f.zone_high, f.zone_low, key_level_proximity_pct):
                    key_levels.append("fvg")
                    break
            for ob in obs:
                if ob.direction == "bearish" and _zone_overlaps(zone_high, zone_low, ob.zone_high, ob.zone_low, key_level_proximity_pct):
                    key_levels.append("order_block")
                    break
            for sw in sweeps:
                if sw.direction == "sweep_highs" and _zone_near_price(zone_high, zone_low, sw.level, key_level_proximity_pct):
                    key_levels.append("liquidity_sweep")
                    break

        # Reversal confirmation
        reversal_confirmed = False
        if direction == "bullish":
            candle_high = h
            for j in range(i + 1, min(i + 1 + reversal_confirmation_bars, len(df))):
                if df["close"].iloc[j] > candle_high:
                    reversal_confirmed = True
                    break
        else:
            candle_low = l
            for j in range(i + 1, min(i + 1 + reversal_confirmation_bars, len(df))):
                if df["close"].iloc[j] < candle_low:
                    reversal_confirmed = True
                    break

        vol_ok = True
        if volume_above_avg_mult > 0 and i < len(vol_avg) and vol_avg.iloc[i] > 0:
            vol_ok = vol.iloc[i] >= volume_above_avg_mult * vol_avg.iloc[i]

        out.append(RejectionBlock(
            timestamp=df.index[i],
            direction=direction,
            zone_high=zone_high,
            zone_low=zone_low,
            candle_high=float(h),
            candle_low=float(l),
            bar_index=i,
            key_levels_nearby=key_levels,
            reversal_confirmed=reversal_confirmed,
            volume_ok=vol_ok,
        ))

    return out
