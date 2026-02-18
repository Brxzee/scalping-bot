"""London / New York key opens (killzones). Times in EST."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class KillzoneWindow:
    start_h: int
    start_m: int
    end_h: int
    end_m: int
    name: str


def _parse_time(s: str) -> tuple[int, int]:
    parts = s.strip().split(":")
    h = int(parts[0]) if parts else 0
    m = int(parts[1]) if len(parts) > 1 else 0
    return h, m


def in_killzone(
    ts: pd.Timestamp,
    london_start: str = "02:00",
    london_end: str = "05:00",
    newyork_start: str = "07:00",
    newyork_end: str = "10:00",
    extend_minutes_after: int = 30,
) -> bool:
    """
    True if timestamp falls inside London or NY killzone (or within extend_minutes_after of zone end).
    Expects ts to be timezone-aware (e.g. America/New_York).
    """
    return get_killzone_name(ts, london_start, london_end, newyork_start, newyork_end, extend_minutes_after) is not None


def get_killzone_name(
    ts: pd.Timestamp,
    london_start: str = "02:00",
    london_end: str = "05:00",
    newyork_start: str = "07:00",
    newyork_end: str = "10:00",
    extend_minutes_after: int = 30,
) -> Optional[str]:
    """Return 'london', 'newyork', or None."""
    if ts.tz is None:
        return None
    # Normalize to EST for comparison (config is in EST)
    try:
        ts_local = ts.tz_convert("America/New_York")
    except Exception:
        ts_local = ts
    time = ts_local.time()
    minute_of_day = time.hour * 60 + time.minute

    lsh, lsm = _parse_time(london_start)
    leh, lem = _parse_time(london_end)
    nsh, nsm = _parse_time(newyork_start)
    neh, nem = _parse_time(newyork_end)

    london_start_m = lsh * 60 + lsm
    london_end_m = leh * 60 + lem
    london_end_ext = london_end_m + extend_minutes_after
    if london_start_m <= minute_of_day <= london_end_ext:
        return "london"
    if london_end_m < london_start_m:  # overnight
        if minute_of_day >= london_start_m or minute_of_day <= london_end_ext:
            return "london"

    ny_start_m = nsh * 60 + nsm
    ny_end_m = neh * 60 + nem
    ny_end_ext = ny_end_m + extend_minutes_after
    if ny_start_m <= minute_of_day <= ny_end_ext:
        return "newyork"
    if ny_end_m < ny_start_m:
        if minute_of_day >= ny_start_m or minute_of_day <= ny_end_ext:
            return "newyork"
    return None
