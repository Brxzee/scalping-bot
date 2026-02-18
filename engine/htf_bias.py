"""
HTF bias: 1H, 4H, daily structure-based bias for stacking probability.
Only take 5m setups when direction aligns with 1H, 4H, and daily.
"""
from __future__ import annotations

from typing import Literal

import pandas as pd

from structure import find_swing_highs_lows


Bias = Literal["bullish", "bearish"] | None


def get_htf_bias(
    df: pd.DataFrame,
    lookback: int = 50,
    method: str = "structure",
) -> Bias:
    """
    Return bullish/bearish/None from HTF structure.
    Structure: close vs recent swing high/low. Close > last swing high -> bullish;
    close < last swing low -> bearish; else None.
    """
    if df is None or df.empty or len(df) < lookback:
        return None
    df_tail = df.tail(lookback)
    highs = df_tail["high"]
    lows = df_tail["low"]
    close = df_tail["close"].iloc[-1]
    swing_highs, swing_lows = find_swing_highs_lows(df_tail, lookback=min(5, lookback // 5))
    if not swing_highs or not swing_lows:
        return None
    last_sh = max(s.price for s in swing_highs)
    last_sl = min(s.price for s in swing_lows)
    if close > last_sh:
        return "bullish"
    if close < last_sl:
        return "bearish"
    return None


def htf_aligned(
    direction: str,
    bias_1h: Bias,
    bias_4h: Bias,
    bias_daily: Bias,
    require_1h: bool = True,
    require_4h: bool = True,
    require_daily: bool = True,
    treat_none_as_aligned: bool = False,
) -> bool:
    """
    True if 5m setup direction is not opposed by any required HTF bias.
    - treat_none_as_aligned=False (strict): every required TF must be explicitly bullish/bearish and match.
    - treat_none_as_aligned=True (soft): only reject when a required TF has opposite bias; None = pass.
    """
    if direction not in ("bullish", "bearish"):
        return False

    def _ok(bias: Bias, req: bool) -> bool:
        if not req:
            return True
        if treat_none_as_aligned:
            return bias is None or bias == direction  # None = no conflict
        return bias is not None and bias == direction  # strict: must match

    if not _ok(bias_1h, require_1h):
        return False
    if not _ok(bias_4h, require_4h):
        return False
    if not _ok(bias_daily, require_daily):
        return False
    return True
