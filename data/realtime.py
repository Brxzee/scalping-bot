"""
Real-time monitor: poll data, run detector, send new setups to Telegram.
Only alerts on setups that form after the bot start time (ignores historical setups).
"""
from __future__ import annotations

import asyncio
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Project root = directory containing config, data, engine, etc.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from loguru import logger

from config import load_config
from data.fetcher import get_fetcher
from engine import build_setups, setup_log_line, setup_to_telegram_dict
from engine.setup_output import SetupRecord
from notifications import TelegramNotifier


def _setup_fingerprint(s: SetupRecord) -> str:
    """Unique id for deduplication."""
    return f"{s.symbol}|{s.timeframe}|{s.timestamp.isoformat()}|{s.direction}|{s.entry_zone_low:.4f}"


def _ts_aware_now(tz_name: str) -> datetime:
    """Current time in config timezone for comparison with setup timestamps."""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/New_York")
    return datetime.now(tz)


def _interval_minutes_from_timeframe(tf: str) -> int:
    """Parse timeframe_primary (e.g. 5m, 15m, 1h) to interval minutes."""
    tf = (tf or "5m").strip().lower()
    if tf.endswith("m"):
        return int(re.sub(r"[^0-9]", "", tf) or "5")
    if tf.endswith("h"):
        return int(re.sub(r"[^0-9]", "", tf) or "1") * 60
    if tf == "1d" or tf == "d":
        return 24 * 60
    return 5


def _seconds_until_next_candle_close(
    timeframe_primary: str,
    tz_name: str,
    buffer_seconds: int = 10,
) -> float:
    """
    Seconds until the next candle close (in config tz) + buffer.
    Ensures we poll right after the bar closes so data is aligned with charts.
    """
    tz = ZoneInfo(tz_name) if tz_name else ZoneInfo("America/New_York")
    now = datetime.now(tz)
    interval_mins = _interval_minutes_from_timeframe(timeframe_primary)
    if interval_mins >= 24 * 60:
        # Daily: next close = next midnight
        next_close = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        total_mins = now.hour * 60 + now.minute
        next_boundary_mins = ((total_mins // interval_mins) + 1) * interval_mins
        if next_boundary_mins >= 24 * 60:
            next_close = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            next_close = now.replace(
                hour=next_boundary_mins // 60,
                minute=next_boundary_mins % 60,
                second=0,
                microsecond=0,
            )
    delta = (next_close - now).total_seconds() + buffer_seconds
    return max(1.0, delta)


def run_detection_cycle(config: dict) -> tuple[list[SetupRecord], datetime | None]:
    """
    Fetch 5m + 1H + 4H + daily; run confluence; return (setups, last_primary_bar_time).
    last_primary_bar_time is the timestamp of the most recent 5m bar we have (for freshness check).
    """
    fetcher = get_fetcher(config)
    data_cfg = config.get("data", {})
    symbols = data_cfg.get("symbols", ["NQ=F", "ES=F"])
    tf_primary = data_cfg.get("timeframe_primary", "5m")
    tf_1h = data_cfg.get("timeframe_structure", "1h")
    tf_4h = data_cfg.get("timeframe_4h", "4h")
    tf_daily = data_cfg.get("timeframe_daily", "1d")
    lookback = data_cfg.get("lookback_bars", 500)
    tz_name = data_cfg.get("timezone", "America/New_York")

    all_setups: list[SetupRecord] = []
    last_bar_ts: datetime | None = None
    for symbol in symbols:
        try:
            df_primary = fetcher.fetch(symbol, tf_primary, limit=lookback)
            if df_primary.empty or len(df_primary) < 50:
                logger.warning(f"Not enough data for {symbol} {tf_primary}")
                continue
            # Track most recent primary bar we have (for data freshness)
            bar_ts = df_primary.index[-1]
            if hasattr(bar_ts, "to_pydatetime"):
                bar_ts = bar_ts.to_pydatetime()
            if bar_ts.tzinfo is None:
                bar_ts = bar_ts.replace(tzinfo=ZoneInfo(tz_name))
            else:
                bar_ts = bar_ts.astimezone(ZoneInfo(tz_name))
            if last_bar_ts is None or bar_ts < last_bar_ts:
                last_bar_ts = bar_ts
            df_1h = fetcher.fetch(symbol, tf_1h, limit=min(500, lookback))
            df_4h = fetcher.fetch(symbol, tf_1h, limit=min(500, lookback * 2))
            if not df_4h.empty and len(df_4h) >= 4:
                agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
                if "volume" in df_4h.columns:
                    agg["volume"] = "sum"
                df_4h = df_4h.resample("4h").agg(agg).dropna()
            df_daily = fetcher.fetch(symbol, tf_daily, limit=min(365, lookback))
            setups = build_setups(
                df_primary, symbol, tf_primary, config,
                df_1h=df_1h if not df_1h.empty else None,
                df_4h=df_4h if not df_4h.empty else None,
                df_daily=df_daily if not df_daily.empty else None,
            )
            all_setups.extend(setups)
        except Exception as e:
            logger.exception(f"Detector error for {symbol}: {e}")
    return all_setups, last_bar_ts


async def run_realtime_loop(config: dict):
    """
    Loop: run detection, send only new setups to Telegram.
    By default syncs to primary timeframe candle close (e.g. 5m :00, :05, :10) + buffer
    so polling aligns with chart time and avoids user error.
    """
    data_cfg = config.get("data", {})
    tz_name = data_cfg.get("timezone", "America/New_York")
    tf_primary = data_cfg.get("timeframe_primary", "5m")
    sync_to_candle = data_cfg.get("realtime_sync_to_candle_close", True)
    buffer_after_close = max(5, data_cfg.get("realtime_buffer_after_close_seconds", 15))
    poll_seconds = max(60, data_cfg.get("realtime_poll_seconds", 60))

    telegram_cfg = config.get("telegram", {})
    enabled = telegram_cfg.get("enabled", True)
    rate_limit = telegram_cfg.get("rate_limit_seconds", 0.5)

    notifier: TelegramNotifier | None = None
    if enabled and telegram_cfg.get("bot_token") and telegram_cfg.get("chat_id"):
        notifier = TelegramNotifier(
            bot_token=telegram_cfg["bot_token"],
            chat_id=telegram_cfg["chat_id"],
        )
        await notifier.send_session_start(
            datetime.now().strftime("%Y-%m-%d"),
            ["Powell ICT Scalping"],
        )
    else:
        logger.warning("Telegram disabled or missing bot_token/chat_id; alerts will not be sent.")

    # Only alert on setups that form after this time (ignore all historical setups)
    session_start = _ts_aware_now(tz_name)
    logger.info(f"Session start: {session_start}. Alerts only for setups forming after this time.")

    if sync_to_candle:
        logger.info(
            f"Synced to {tf_primary} candle close ({tz_name}). Poll after each close + {buffer_after_close}s buffer."
        )
    else:
        logger.info(f"Polling every {poll_seconds}s (realtime_sync_to_candle_close=false).")

    seen: set[str] = set()
    previous_count = 0
    while True:
        try:
            if sync_to_candle:
                wait_sec = _seconds_until_next_candle_close(tf_primary, tz_name, buffer_after_close)
                tz = ZoneInfo(tz_name)
                next_poll_at = datetime.now(tz) + timedelta(seconds=wait_sec)
                logger.info(f"Next poll at {next_poll_at.strftime('%Y-%m-%d %H:%M:%S')} {tz_name} (after candle close + {buffer_after_close}s)")
                await asyncio.sleep(wait_sec)

            cycle_at = _ts_aware_now(tz_name)
            logger.info(f"--- Cycle {cycle_at.strftime('%Y-%m-%d %H:%M:%S')} ({tz_name}) ---")

            setups, last_primary_bar_time = run_detection_cycle(config)
            # Only send new setups to Telegram if data is fresh (avoid delayed data = missed entry)
            interval_mins = _interval_minutes_from_timeframe(tf_primary)
            # Stale if last bar is older than one period + 1 min (e.g. 5m bar > 6 min old)
            stale_threshold_sec = (interval_mins * 60) + 60
            data_fresh = True
            if last_primary_bar_time is not None:
                age_sec = (cycle_at - last_primary_bar_time).total_seconds()
                if age_sec > stale_threshold_sec:
                    data_fresh = False
                    logger.warning(
                        f"Data may be delayed (last {tf_primary} bar {age_sec/60:.1f} min old). "
                        "Skipping Telegram this cycle so you don't get a stale alert."
                    )

            new_setups: list[SetupRecord] = []
            for s in setups:
                fp = _setup_fingerprint(s)
                if fp in seen:
                    continue
                # Only alert if setup formed after the bot started (not old data)
                setup_ts = s.timestamp
                if hasattr(setup_ts, "tz_convert"):
                    # pandas Timestamp
                    if setup_ts.tzinfo is None:
                        setup_ts = setup_ts.tz_localize(ZoneInfo(tz_name))
                    else:
                        setup_ts = setup_ts.tz_convert(session_start.tzinfo)
                elif hasattr(setup_ts, "tzinfo") and setup_ts.tzinfo is None:
                    from datetime import datetime as dt
                    setup_ts = setup_ts.replace(tzinfo=session_start.tzinfo)
                if setup_ts < session_start:
                    seen.add(fp)  # mark as seen so we don't re-check
                    continue
                seen.add(fp)
                new_setups.append(s)

            # Console: previous vs this cycle, then list all current setups with timestamps and context
            logger.info(f"Previous cycle: {previous_count} setup(s). This cycle: {len(setups)} total, {len(new_setups)} new.")
            for i, s in enumerate(setups, 1):
                logger.info(setup_log_line(s, prefix=f"  [{i}] "))
            if not setups:
                logger.info("  (no setups)")

            if new_setups and notifier:
                if data_fresh:
                    payloads = [setup_to_telegram_dict(s) for s in new_setups]
                    await notifier.send_multiple_setups(payloads, rate_limit_seconds=rate_limit)
                    logger.info(f"Sent {len(new_setups)} new setup(s) to Telegram")
                else:
                    logger.warning(f"Not sending {len(new_setups)} new setup(s) — data delayed; next cycle will retry.")
            elif new_setups:
                for s in new_setups:
                    logger.info(f"New (no Telegram): {setup_log_line(s)}")

            previous_count = len(setups)

            if not sync_to_candle:
                logger.info(f"Next poll in {poll_seconds}s")
                await asyncio.sleep(poll_seconds)
        except Exception as e:
            logger.exception(f"Realtime cycle error: {e}")
            if notifier:
                await notifier.send_error(str(e))
            if not sync_to_candle:
                await asyncio.sleep(poll_seconds)


def main():
    """Entry for real-time monitoring."""
    config = load_config()
    asyncio.run(run_realtime_loop(config))


if __name__ == "__main__":
    main()
