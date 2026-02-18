"""Setup record and export (Telegram-compatible dict)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class SetupRecord:
    """Single trade setup: entry = rejection candle zone, stop beyond wick, target capped."""
    symbol: str
    timeframe: str
    direction: str  # bullish | bearish
    entry_zone_high: float
    entry_zone_low: float
    stop: float
    target: float
    confluences: List[str]
    score: int
    timestamp: datetime
    key_level_type: str = "Rejection Block"
    key_level_price: float = 0.0
    rejection_candle_high: float = 0.0  # Full candle (stop for short)
    rejection_candle_low: float = 0.0   # Full candle (stop for long)


def setup_log_line(s: SetupRecord, prefix: str = "") -> str:
    """Single line for console logging: timestamp, symbol, direction, score, entry, stop, target, RR, confluences."""
    entry = (s.entry_zone_high + s.entry_zone_low) / 2
    risk_pts = abs(entry - s.stop)
    reward_pts = abs(s.target - entry)
    rr = reward_pts / risk_pts if risk_pts > 0 else 0.0
    ts = s.timestamp.strftime("%Y-%m-%d %H:%M") if hasattr(s.timestamp, "strftime") else str(s.timestamp)
    conf = ", ".join(s.confluences) if s.confluences else "—"
    return (
        f"{prefix}{s.symbol} {s.timeframe} {s.direction} | bar={ts} | score={s.score} | "
        f"entry={entry:.2f} stop={s.stop:.2f} target={s.target:.2f} RR=1:{rr:.1f} | {conf}"
    )


def setup_to_telegram_dict(s: SetupRecord) -> Dict[str, Any]:
    """
    Map our SetupRecord to the format expected by the user's TelegramNotifier.send_setup_alert.
    """
    entry = (s.entry_zone_high + s.entry_zone_low) / 2
    risk_pts = abs(entry - s.stop)
    reward_pts = abs(s.target - entry)
    rr = reward_pts / risk_pts if risk_pts > 0 else 0.0
    if s.score >= 6:
        quality_rating = "High"
    elif s.score >= 4:
        quality_rating = "Medium"
    else:
        quality_rating = "Low"
    key_price = s.key_level_price or entry
    return {
        "strategy": "Powell ICT Scalping",
        "symbol": s.symbol,
        "direction": s.direction,
        "quality_rating": quality_rating,
        "quality_score": s.score,
        "requires_manual_review": False,
        "entry": entry,
        "stop_loss": s.stop,
        "take_profit": s.target,
        "rr_ratio": rr,
        "risk_points": risk_pts,
        "reward_points": reward_pts,
        "key_level": {"type": s.key_level_type, "price": key_price},
        "fib_level": "N/A",
        "alignment_quality": ", ".join(s.confluences) if s.confluences else "Killzone + RB",
        "timestamp": s.timestamp,
        "entry_note": "Retracement into wick (entry_fib); discretion for high RR",
    }
