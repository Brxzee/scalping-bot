"""Unit tests for killzone (key opens)."""
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from session import in_killzone, get_killzone_name


def test_london_killzone():
    # 03:00 EST = London
    ts = pd.Timestamp("2024-01-15 03:00:00", tz="America/New_York")
    assert get_killzone_name(ts) == "london"
    assert in_killzone(ts) is True


def test_newyork_killzone():
    ts = pd.Timestamp("2024-01-15 08:00:00", tz="America/New_York")
    assert get_killzone_name(ts) == "newyork"
    assert in_killzone(ts) is True


def test_outside_killzone():
    ts = pd.Timestamp("2024-01-15 12:00:00", tz="America/New_York")
    assert get_killzone_name(ts) is None
    assert in_killzone(ts) is False
