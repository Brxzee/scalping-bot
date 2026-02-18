#!/usr/bin/env python3
"""
Backtest Powell ICT scalping strategy over the last 90 days (or configurable).
Uses same detection as live (build_setups); simulates entry on next bar, stop/target hit.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger

from config import load_config
from data.fetcher import get_fetcher
from engine import build_setups
from engine.setup_output import SetupRecord
from rejection_block import find_rejection_blocks
from session import get_killzone_name
from engine.htf_bias import get_htf_bias, htf_aligned


@dataclass
class TradeResult:
    """Result of one simulated trade."""
    setup: SetupRecord
    outcome: str  # "win" | "loss"
    exit_price: float
    bars_held: int
    pnl_points: float


def _find_setup_bar_index(df, setup_ts) -> int | None:
    """Return bar index whose timestamp equals or is last before setup_ts."""
    import pandas as pd
    if hasattr(setup_ts, "to_pydatetime"):
        setup_ts = setup_ts.to_pydatetime()
    for i in range(len(df) - 1, -1, -1):
        bar_ts = df.index[i]
        if hasattr(bar_ts, "to_pydatetime"):
            bar_ts = bar_ts.to_pydatetime()
        if bar_ts <= setup_ts:
            return i
    return None


def _simulate_trade(
    df,
    setup: SetupRecord,
    setup_bar_index: int,
    max_bars_to_fill: int = 10,
) -> TradeResult | None:
    """
    Entry on retracement into the wick: first bar after setup that overlaps the entry zone
    (tight band around fib level in wick). Entry at zone mid; stop/target from setup.
    """
    zone_high = setup.entry_zone_high
    zone_low = setup.entry_zone_low
    entry_price = (zone_high + zone_low) / 2
    stop = setup.stop
    target = setup.target
    direction = setup.direction

    # First bar after setup bar that retests the zone (range overlaps zone)
    entry_bar = None
    for j in range(setup_bar_index + 1, min(setup_bar_index + 1 + max_bars_to_fill, len(df))):
        high_j = float(df["high"].iloc[j])
        low_j = float(df["low"].iloc[j])
        if direction == "bullish":
            if low_j <= zone_high and high_j >= zone_low:
                entry_bar = j
                break
        else:
            if high_j >= zone_low and low_j <= zone_high:
                entry_bar = j
                break
    if entry_bar is None:
        return None  # No retest = no fill

    for j in range(entry_bar, len(df)):
        high = float(df["high"].iloc[j])
        low = float(df["low"].iloc[j])
        if direction == "bullish":
            if low <= stop:
                return TradeResult(setup=setup, outcome="loss", exit_price=stop, bars_held=j - entry_bar, pnl_points=stop - entry_price)
            if high >= target:
                return TradeResult(setup=setup, outcome="win", exit_price=target, bars_held=j - entry_bar, pnl_points=target - entry_price)
        else:
            if high >= stop:
                return TradeResult(setup=setup, outcome="loss", exit_price=stop, bars_held=j - entry_bar, pnl_points=entry_price - stop)
            if low <= target:
                return TradeResult(setup=setup, outcome="win", exit_price=target, bars_held=j - entry_bar, pnl_points=entry_price - target)
    return None


def run_backtest(
    config: dict | None = None,
    days: int = 90,
    timeframe: str | None = None,
) -> tuple[list[TradeResult], dict]:
    """
    Fetch last `days` of data, build setups, simulate each trade.
    Returns (list of TradeResult, summary dict).
    """
    config = config or load_config()
    data_cfg = config.get("data", {})
    symbols = data_cfg.get("symbols", ["NQ=F", "ES=F"])
    tf = timeframe or data_cfg.get("timeframe_primary", "5m")
    if "m" in tf:
        mins = 5 if "5" in tf else 15 if "15" in tf else 60 if "60" in tf else 30
        lookback = min(10000, days * 24 * 60 // mins)
    else:
        lookback = min(5000, days * 24)
    lookback = max(lookback, 500)

    fetcher = get_fetcher(config)
    tf_1h = data_cfg.get("timeframe_structure", "1h")
    tf_daily = data_cfg.get("timeframe_daily", "1d")
    all_setups: list[SetupRecord] = []
    for symbol in symbols:
        try:
            df = fetcher.fetch(symbol, tf, limit=lookback)
            if df.empty or len(df) < 100:
                logger.warning(f"Not enough data for {symbol}")
                continue
            df_1h = fetcher.fetch(symbol, tf_1h, limit=min(500, lookback))
            df_4h = fetcher.fetch(symbol, tf_1h, limit=min(500, lookback * 2))
            if not df_4h.empty and len(df_4h) >= 4:
                agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
                if "volume" in df_4h.columns:
                    agg["volume"] = "sum"
                df_4h = df_4h.resample("4h").agg(agg).dropna()
            df_daily = fetcher.fetch(symbol, tf_daily, limit=min(365, lookback))
            setups = build_setups(
                df, symbol, tf, config,
                df_1h=df_1h if not df_1h.empty else None,
                df_4h=df_4h if not df_4h.empty else None,
                df_daily=df_daily if not df_daily.empty else None,
            )
            for s in setups:
                s._df = df
                s._symbol = symbol
            all_setups.extend(setups)
        except Exception as e:
            logger.exception(f"Backtest fetch/setup error {symbol}: {e}")

    results: list[TradeResult] = []
    for s in all_setups:
        df = getattr(s, "_df", None)
        if df is None:
            continue
        setup_ts = s.timestamp
        if hasattr(setup_ts, "to_pydatetime"):
            setup_ts = setup_ts.to_pydatetime()
        idx = _find_setup_bar_index(df, setup_ts)
        if idx is None:
            continue
        tr = _simulate_trade(df, s, idx, max_bars_to_fill=10)
        if tr is not None:
            results.append(tr)

    wins = [r for r in results if r.outcome == "win"]
    losses = [r for r in results if r.outcome == "loss"]
    total_pnl = sum(r.pnl_points for r in results)
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in results:
        equity += r.pnl_points
        peak = max(peak, equity)
        drawdown = peak - equity
        if drawdown > max_dd:
            max_dd = drawdown

    summary = {
        "total_trades": len(results),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": 100.0 * len(wins) / len(results) if results else 0,
        "total_pnl_points": total_pnl,
        "max_drawdown_points": abs(max_dd),
        "avg_bars_held": sum(r.bars_held for r in results) / len(results) if results else 0,
    }
    return results, summary


def run_diagnostic(config: dict, days: int = 90):
    """Print pipeline counts for first symbol to see where setups are lost."""
    data_cfg = config.get("data", {})
    symbols = data_cfg.get("symbols", ["NQ=F"])[:1]
    tf = data_cfg.get("timeframe_primary", "5m")
    lookback = min(10000, days * 24 * 60 // 5)
    lookback = max(lookback, 500)
    fetcher = get_fetcher(config)
    rb_cfg = config.get("rejection_block", {})
    struct_cfg = config.get("structure", {})
    kz_cfg = config.get("killzone", {})
    htf_cfg = config.get("htf_bias", {})
    conf_cfg = config.get("confluence", {})
    min_score = conf_cfg.get("min_score_to_alert", 4)
    cap_cfg = config.get("target_cap", {})
    require_reversal = cap_cfg.get("require_reversal_confirmed", True)

    symbol = symbols[0]
    df = fetcher.fetch(symbol, tf, limit=lookback)
    if df.empty or len(df) < 100:
        print("Diagnostic: not enough 5m data")
        return
    df_1h = fetcher.fetch(symbol, data_cfg.get("timeframe_structure", "1h"), limit=500)
    df_4h = fetcher.fetch(symbol, "1h", limit=500)
    if not df_4h.empty and len(df_4h) >= 4:
        agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
        if "volume" in df_4h.columns:
            agg["volume"] = "sum"
        df_4h = df_4h.resample("4h").agg(agg).dropna()
    df_daily = fetcher.fetch(symbol, data_cfg.get("timeframe_daily", "1d"), limit=365)

    rbs = find_rejection_blocks(
        df,
        wick_to_body_ratio_min=rb_cfg.get("wick_to_body_ratio_min", 2.0),
        reversal_confirmation_bars=rb_cfg.get("reversal_confirmation_bars", 3),
        key_level_proximity_pct=rb_cfg.get("key_level_proximity_pct", 0.001),
        volume_above_avg_mult=rb_cfg.get("volume_above_avg_mult", 1.0),
        swing_lookback=struct_cfg.get("swing_lookback", 5),
        atr_period=struct_cfg.get("atr_period", 14),
        ob_displacement_bars=struct_cfg.get("order_block_displacement_bars", 2),
        ob_body_atr_mult=struct_cfg.get("order_block_body_atr_mult", 0.5),
        sweep_threshold_pct=struct_cfg.get("liquidity_sweep_threshold_pct", 0.02),
    )
    n_rbs = len(rbs)
    n_after_reversal = sum(1 for rb in rbs if not require_reversal or rb.reversal_confirmed)
    n_after_kz = 0
    n_after_score = 0
    n_after_htf = 0
    n_after_risk = 0
    for rb in rbs:
        if require_reversal and not rb.reversal_confirmed:
            continue
        kz = get_killzone_name(
            rb.timestamp,
            london_start=kz_cfg.get("london_start", "02:00"),
            london_end=kz_cfg.get("london_end", "05:00"),
            newyork_start=kz_cfg.get("newyork_start", "07:00"),
            newyork_end=kz_cfg.get("newyork_end", "10:00"),
            extend_minutes_after=kz_cfg.get("extend_minutes_after", 30),
        )
        if not kz:
            continue
        n_after_kz += 1
        score = 1 + 2  # RB + killzone
        for k in rb.key_levels_nearby:
            score += 1
        if score < min_score:
            continue
        n_after_score += 1
        if htf_cfg.get("enabled"):
            bias_1h = get_htf_bias(df_1h, lookback=htf_cfg.get("lookback_bars", 50), method="structure") if not df_1h.empty else None
            bias_4h = get_htf_bias(df_4h, lookback=htf_cfg.get("lookback_bars", 50), method="structure") if not df_4h.empty else None
            bias_d = get_htf_bias(df_daily, lookback=50, method="structure") if not df_daily.empty else None
            if not htf_aligned(
                rb.direction, bias_1h, bias_4h, bias_d,
                require_1h=True, require_4h=True, require_daily=True,
                treat_none_as_aligned=htf_cfg.get("treat_none_as_aligned", False),
            ):
                continue
        n_after_htf += 1
        entry_mid = (rb.zone_high + rb.zone_low) / 2
        is_nq = "NQ" in symbol.upper()
        min_risk = cap_cfg.get("min_risk_points_nq" if is_nq else "min_risk_points_es", 10 if is_nq else 5)
        max_risk = cap_cfg.get("max_risk_points_nq" if is_nq else "max_risk_points_es", 15 if is_nq else 8)
        stop = rb.candle_low - 2 if rb.direction == "bullish" else rb.candle_high + 2
        risk_pts = abs(entry_mid - stop)
        if min_risk <= risk_pts <= max_risk:
            n_after_risk += 1

    setups = build_setups(df, symbol, tf, config, df_1h=df_1h if not df_1h.empty else None, df_4h=df_4h if not df_4h.empty else None, df_daily=df_daily if not df_daily.empty else None)
    print("\n--- Pipeline diagnostic ---")
    print(f"  Rejection blocks (raw):     {n_rbs}")
    print(f"  After reversal confirmed:   {n_after_reversal}")
    print(f"  After killzone:             {n_after_kz}")
    print(f"  After min_score:            {n_after_score}")
    print(f"  After HTF aligned:          {n_after_htf}")
    print(f"  After risk min/max:         {n_after_risk}")
    print(f"  build_setups() returned:    {len(setups)}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Backtest Powell ICT strategy (90 days)")
    parser.add_argument("--config", default=None, help="Config path")
    parser.add_argument("--days", type=int, default=90, help="Days of history")
    parser.add_argument("--timeframe", default=None, help="Override timeframe (e.g. 1h)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print each trade")
    parser.add_argument("--diagnose", action="store_true", help="Show pipeline counts (why 0 setups)")
    args = parser.parse_args()

    config = load_config(args.config)
    results, summary = run_backtest(config=config, days=args.days, timeframe=args.timeframe)

    if args.diagnose or summary["total_trades"] == 0:
        run_diagnostic(config, days=args.days)

    print("\n--- Backtest summary ---")
    print(f"  Total trades:  {summary['total_trades']}")
    print(f"  Wins:          {summary['wins']}")
    print(f"  Losses:        {summary['losses']}")
    print(f"  Win rate:      {summary['win_rate_pct']:.1f}%")
    print(f"  Total P&L:     {summary['total_pnl_points']:.1f} points")
    print(f"  Max drawdown:  {summary['max_drawdown_points']:.1f} points")
    print(f"  Avg bars held: {summary['avg_bars_held']:.1f}")
    if args.verbose and results:
        print("\n--- Trades ---")
        for r in results[:50]:
            print(f"  {r.setup.symbol} {r.setup.direction} {r.outcome} PnL={r.pnl_points:.1f} bars={r.bars_held}")
        if len(results) > 50:
            print(f"  ... and {len(results) - 50} more")


if __name__ == "__main__":
    main()
