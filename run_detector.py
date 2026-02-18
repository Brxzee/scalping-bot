#!/usr/bin/env python3
"""
Powell ICT Scalping Detector - CLI.
Usage:
  python run_detector.py              # One-shot detection, print setups
  python run_detector.py --realtime  # Real-time loop + Telegram
  python run_detector.py --realtime --no-telegram  # Real-time, log only
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger

from config import load_config
from data.realtime import run_detection_cycle, run_realtime_loop
from engine.setup_output import SetupRecord, setup_log_line


def _setup_to_dict(s: SetupRecord) -> dict:
    return {
        "symbol": s.symbol,
        "timeframe": s.timeframe,
        "direction": s.direction,
        "entry_zone": [s.entry_zone_high, s.entry_zone_low],
        "stop": s.stop,
        "target": s.target,
        "score": s.score,
        "confluences": s.confluences,
        "timestamp": s.timestamp.isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="Powell ICT Scalping Detector")
    parser.add_argument("--config", default=None, help="Path to settings.yaml")
    parser.add_argument("--realtime", action="store_true", help="Run real-time monitor loop")
    parser.add_argument("--no-telegram", action="store_true", help="Disable Telegram in realtime mode")
    parser.add_argument("--json", action="store_true", help="Output setups as JSON (one-shot)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    if not args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="INFO")

    config = load_config(args.config)
    if args.no_telegram and args.realtime:
        config.setdefault("telegram", {})["enabled"] = False

    if args.realtime:
        asyncio.run(run_realtime_loop(config))
        return

    # One-shot
    setups, _ = run_detection_cycle(config)
    if args.json:
        print(json.dumps([_setup_to_dict(s) for s in setups], indent=2))
    else:
        tz_name = config.get("data", {}).get("timezone", "America/New_York")
        try:
            now = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Detected at {now} ({tz_name}) — {len(setups)} setup(s)")
        for i, s in enumerate(setups, 1):
            print(setup_log_line(s, prefix=f"  [{i}] "))
        if not setups:
            print("No setups meeting min confluence score.")


if __name__ == "__main__":
    main()
