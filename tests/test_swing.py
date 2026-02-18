"""Unit tests for swing high/low detection."""
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from structure import find_swing_highs_lows


def test_swing_high_low():
    # Create a V shape: high in the middle
    idx = pd.date_range("2024-01-01", periods=11, freq="15min", tz="UTC")
    highs = [1, 2, 3, 4, 5, 10, 5, 4, 3, 2, 1]
    lows = [0, 1, 2, 3, 4, 5, 4, 3, 2, 1, 0]
    df = pd.DataFrame({"open": [1]*11, "high": highs, "low": lows, "close": [1]*11}, index=idx)
    sh, sl = find_swing_highs_lows(df, lookback=2)
    assert len(sh) >= 1
    assert any(s.price == 10 for s in sh)
    assert len(sl) >= 1
