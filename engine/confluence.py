"""
Combine rejection blocks with wick theory, key levels, killzone; score and output setups.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from rejection_block import find_rejection_blocks
from rejection_block.detector import RejectionBlock
from wick import find_wick_events
from session import get_killzone_name
from structure import atr_series
from .setup_output import SetupRecord
from .htf_bias import get_htf_bias, htf_aligned


def _capped_target(
    entry: float,
    stop: float,
    direction: str,
    symbol: str,
    config: dict,
) -> float:
    """
    Powell: 1:4 to 1:6 RR. Target = entry + risk * target_rr (long) or entry - risk * target_rr (short).
    """
    risk = abs(entry - stop)
    cap_cfg = config.get("target_cap", {})
    target_rr = cap_cfg.get("target_rr", 5)
    reward = risk * target_rr
    if direction == "bullish":
        return entry + reward
    return entry - reward


def build_setups(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    config: Dict[str, Any],
    df_1h: pd.DataFrame | None = None,
    df_4h: pd.DataFrame | None = None,
    df_daily: pd.DataFrame | None = None,
) -> List[SetupRecord]:
    """
    Run rejection block + wick + killzone; filter by HTF alignment (1H + 4H + daily).
    Min 10pt stop, volume-scaled buffer, 1:4-1:6 RR.
    """
    data_cfg = config.get("data", {})
    htf_cfg = config.get("htf_bias", {})
    struct_cfg = config.get("structure", {})
    wick_cfg = config.get("wick", {})
    rb_cfg = config.get("rejection_block", {})
    kz_cfg = config.get("killzone", {})
    conf_cfg = config.get("confluence", {})
    weights = conf_cfg.get("weights", {})
    min_score = conf_cfg.get("min_score_to_alert", 4)

    swing_lookback = struct_cfg.get("swing_lookback", 5)
    atr_period = struct_cfg.get("atr_period", 14)

    rbs = find_rejection_blocks(
        df,
        wick_to_body_ratio_min=rb_cfg.get("wick_to_body_ratio_min", 2.0),
        reversal_confirmation_bars=rb_cfg.get("reversal_confirmation_bars", 3),
        key_level_proximity_pct=rb_cfg.get("key_level_proximity_pct", 0.001),
        volume_above_avg_mult=rb_cfg.get("volume_above_avg_mult", 1.0),
        swing_lookback=swing_lookback,
        atr_period=atr_period,
        ob_displacement_bars=struct_cfg.get("order_block_displacement_bars", 2),
        ob_body_atr_mult=struct_cfg.get("order_block_body_atr_mult", 0.5),
        sweep_threshold_pct=struct_cfg.get("liquidity_sweep_threshold_pct", 0.02),
    )

    wick_events = find_wick_events(
        df,
        wick_to_body_ratio_min=wick_cfg.get("wick_to_body_ratio_min", 2.0),
        body_to_range_max=wick_cfg.get("body_to_range_max", 0.5),
        atr_min_mult=wick_cfg.get("atr_min_mult", 0.3),
        respect_bars_lookback=wick_cfg.get("respect_bars_lookback", 10),
        swing_lookback=swing_lookback,
        atr_period=atr_period,
    )

    cap_cfg = config.get("target_cap", {})
    require_reversal = cap_cfg.get("require_reversal_confirmed", True)
    stop_buf_nq = cap_cfg.get("stop_buffer_points_nq", 2)
    stop_buf_es = cap_cfg.get("stop_buffer_points_es", 1)
    vol_extra_nq = cap_cfg.get("volume_buffer_extra_nq", 2)
    vol_extra_es = cap_cfg.get("volume_buffer_extra_es", 1)
    vol_above_mult = cap_cfg.get("volume_above_avg_mult", 1.2)
    min_risk_nq = cap_cfg.get("min_risk_points_nq", 10)
    max_risk_nq = cap_cfg.get("max_risk_points_nq", 15)
    min_risk_es = cap_cfg.get("min_risk_points_es", 5)
    max_risk_es = cap_cfg.get("max_risk_points_es", 8)
    htf_lookback = htf_cfg.get("lookback_bars", 50)
    htf_method = htf_cfg.get("method", "structure")

    bias_1h = get_htf_bias(df_1h, lookback=htf_lookback, method=htf_method) if df_1h is not None and htf_cfg.get("enabled", True) else None
    bias_4h = get_htf_bias(df_4h, lookback=htf_lookback, method=htf_method) if df_4h is not None and htf_cfg.get("enabled", True) else None
    bias_daily = get_htf_bias(df_daily, lookback=min(htf_lookback, len(df_daily) if df_daily is not None else 0), method=htf_method) if df_daily is not None and htf_cfg.get("enabled", True) else None

    setups: List[SetupRecord] = []
    for rb in rbs:
        if rb.bar_index >= len(df):
            continue
        # Only setups with reversal candle close (Powell enters on rejection reversal)
        if require_reversal and not rb.reversal_confirmed:
            continue
        ts = rb.timestamp
        kz_name = get_killzone_name(
            ts,
            london_start=kz_cfg.get("london_start", "02:00"),
            london_end=kz_cfg.get("london_end", "05:00"),
            newyork_start=kz_cfg.get("newyork_start", "07:00"),
            newyork_end=kz_cfg.get("newyork_end", "10:00"),
            extend_minutes_after=kz_cfg.get("extend_minutes_after", 30),
        )
        if not kz_name:
            continue  # Only alert in killzone

        score = weights.get("rejection_block", 1)
        confluences: List[str] = ["Rejection Block"]

        if kz_name:
            score += weights.get("killzone", 2)
            confluences.append(f"Killzone ({kz_name})")

        # Wick respect same direction
        for we in wick_events:
            if we.direction != rb.direction:
                continue
            if we.bar_index == rb.bar_index or abs(we.bar_index - rb.bar_index) <= 3:
                if we.respect is True:
                    score += weights.get("wick_respect", 2)
                    confluences.append("Wick 50% respect")
                break

        for k in rb.key_levels_nearby:
            if k == "order_block":
                score += weights.get("order_block", 1)
                confluences.append("Order Block")
            elif k == "fvg":
                score += weights.get("fvg", 1)
                confluences.append("FVG")
            elif k == "liquidity_sweep":
                score += weights.get("liquidity_sweep", 1)
                confluences.append("Liquidity sweep")
            elif k in ("swing_high", "swing_low"):
                score += weights.get("swing_level", 1)
                confluences.append("Swing level")

        if score < min_score:
            continue

        # HTF as bias only (direction/confluence): never filter; add score when aligned for discretion
        if htf_cfg.get("enabled", False):
            if htf_aligned(
                rb.direction,
                bias_1h, bias_4h, bias_daily,
                require_1h=htf_cfg.get("require_1h", True),
                require_4h=htf_cfg.get("require_4h", True),
                require_daily=htf_cfg.get("require_daily", True),
                treat_none_as_aligned=htf_cfg.get("treat_none_as_aligned", True),
            ):
                score += weights.get("htf_aligned", 2)
                confluences.append("HTF aligned (1H+4H+daily)")

        # Entry = within the wick on retracement (before MM volume injection)
        # 0.5 = CE 50% of wick; 0.25 = tighter/higher RR; 0.75 = shallower (same on 5m and 1h)
        is_nq = "NQ" in symbol.upper()
        entry_fib = cap_cfg.get("entry_fib_in_wick", 0.5)
        wick_range = rb.zone_high - rb.zone_low
        if rb.direction == "bullish":
            entry_level = rb.zone_low + entry_fib * wick_range  # long: 50% up the lower wick
        else:
            entry_level = rb.zone_high - entry_fib * wick_range  # short: 50% down the upper wick (MM sell model)
        entry_tolerance = cap_cfg.get("entry_zone_tolerance_points_nq" if is_nq else "entry_zone_tolerance_points_es", 2 if is_nq else 1)
        entry_high = entry_level + entry_tolerance
        entry_low = entry_level - entry_tolerance
        entry_mid = entry_level

        base_buffer = stop_buf_nq if is_nq else stop_buf_es
        vol_extra = vol_extra_nq if is_nq else vol_extra_es
        if "volume" in df.columns and rb.bar_index < len(df):
            vol = df["volume"].iloc[rb.bar_index]
            vol_avg = df["volume"].rolling(20).mean().iloc[rb.bar_index] if rb.bar_index >= 20 else vol
            if vol_avg > 0 and vol >= vol_above_mult * vol_avg:
                base_buffer += vol_extra
        if rb.direction == "bullish":
            stop = rb.candle_low - base_buffer
        else:
            stop = rb.candle_high + base_buffer
        risk_points = abs(entry_mid - stop)
        min_risk = min_risk_nq if is_nq else min_risk_es
        max_risk = max_risk_nq if is_nq else max_risk_es
        if risk_points < min_risk or risk_points > max_risk:
            continue
        target = _capped_target(entry_mid, stop, rb.direction, symbol, config)

        key_type = rb.key_levels_nearby[0] if rb.key_levels_nearby else "Rejection Block"
        key_price = entry_level

        setups.append(SetupRecord(
            symbol=symbol,
            timeframe=timeframe,
            direction=rb.direction,
            entry_zone_high=entry_high,
            entry_zone_low=entry_low,
            stop=stop,
            target=target,
            confluences=confluences,
            score=score,
            timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
            key_level_type=key_type,
            key_level_price=key_price,
            rejection_candle_high=rb.candle_high,
            rejection_candle_low=rb.candle_low,
        ))

    return setups
