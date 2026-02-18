"""Unit tests for FVG detection."""
import pandas as pd
from datetime import datetime, timezone

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from structure import find_fvgs


def test_bullish_fvg():
    # Bullish FVG: low(candle_0) > high(candle_2)
    # Candle 0: low=100,  Candle 1: gap,  Candle 2: high=98
    idx = pd.date_range("2024-01-01", periods=5, freq="15min", tz="UTC")
    df = pd.DataFrame({
        "open": [99, 98, 97, 98, 99],
        "high": [101, 100, 99, 100, 101],
        "low": [98, 97, 96, 97, 98],
        "close": [100, 99, 98, 99, 100],
    }, index=idx)
    # Candle 0: low=98, Candle 2: high=99 -> 98 > 99 is False. Need low1 > high3.
    # Candle 0 low=98, candle 1 low=97, candle 2 high=99. So low0=98 < high2=99, no bullish.
    # Set low0=100, high2=99 -> bullish FVG
    df.loc[df.index[0], "low"] = 100
    df.loc[df.index[0], "high"] = 101
    df.loc[df.index[2], "high"] = 99
    df.loc[df.index[2], "low"] = 96
    fvgs = find_fvgs(df)
    assert len(fvgs) >= 1
    b = [f for f in fvgs if f.direction == "bullish"]
    assert len(b) >= 1
    assert b[0].zone_low == 99
    assert b[0].zone_high == 100


def test_bearish_fvg():
    idx = pd.date_range("2024-01-01", periods=5, freq="15min", tz="UTC")
    df = pd.DataFrame({
        "open": [101, 102, 103, 102, 101],
        "high": [102, 103, 104, 103, 102],
        "low": [100, 101, 102, 101, 100],
        "close": [101, 102, 103, 102, 101],
    }, index=idx)
    # Bearish: high(candle_0) < low(candle_2). high0=102, low2=102 -> need high0 < low2
    df.loc[df.index[0], "high"] = 101
    df.loc[df.index[2], "low"] = 103
    fvgs = find_fvgs(df)
    bear = [f for f in fvgs if f.direction == "bearish"]
    assert len(bear) >= 1
    assert bear[0].zone_low == 101
    assert bear[0].zone_high == 103


if __name__ == "__main__":
    test_bullish_fvg()
    test_bearish_fvg()
    print("FVG tests OK")
