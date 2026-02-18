# Powell ICT Scalping Bot

Enterprise-style scalping setup detector based on **Powell Trades** wick theory and **ICT** rejection blocks aligned with key opens (London / New York killzones). Detection-only; no order execution.

## Features

- **Wick theory**: 50% midpoint rule, respect/disrespect, swing context
- **ICT rejection blocks**: Long wicks at key levels (order block, FVG, liquidity sweep, swing)
- **Killzone filter**: Setups only during London (02:00–05:00 EST) or New York (07:00–10:00 EST)
- **Confluence scoring**: Ranked setups; Telegram alerts for new setups above threshold
- **Instruments**: **Futures only** — NQ and ES via **yfinance** (`NQ=F`, `ES=F`)
- **Timeframe**: **5m** primary (Powell: filter to 5m to capture reversals)
- **RR**: **1:4 to 1:6** (target_rr configurable); **min 10pt stop** (highly probable rejection blocks only)
- **HTF alignment**: **1H + 4H + daily** bias required (stack probability); optional volume-scaled stop buffer

## Setup

```bash
cd scalping_bot
pip install -r requirements.txt
```

### Telegram

Put your credentials in a **`.env`** file in the project root (do not commit it):

```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Or set the same variables in your environment.

## Usage

**One-shot detection** (print setups to stdout):

```bash
python run_detector.py
```

**One-shot, JSON output:**

```bash
python run_detector.py --json
```

**Real-time monitor** (poll every 60s, send new setups to Telegram):

```bash
python run_detector.py --realtime
```

**Real-time without Telegram:**

```bash
python run_detector.py --realtime --no-telegram
```

**Backtest (last 90 days):**

```bash
python backtest.py --days 90
python backtest.py --days 90 --timeframe 1h -v   # 1h bars, verbose trades
```

Real-time alerts only include setups that **form after the bot start time**; historical setups in the lookback window are not sent.

## Configuration

Edit `config/settings.yaml`:

- **data.symbols**: Futures only — `NQ=F`, `ES=F` (Powell trades NQ/ES; do not add forex)
- **data.timeframe_primary**: Entry timeframe (e.g. `15m`)
- **data.realtime_poll_seconds**: Poll interval (min 60 for 1m candles)
- **confluence.min_score_to_alert**: Minimum score to send Telegram alert (default 4)
- **killzone**: London/NY start/end times in EST

## Project layout

- `config/` – Settings, .env loading for Telegram
- `data/` – Fetcher (yfinance for NQ/ES), real-time loop
- `structure/` – Swing, FVG, order block, liquidity sweep, ATR
- `wick/` – Powell wick theory (50% midpoint, respect)
- `rejection_block/` – ICT rejection block detector
- `session/` – Killzone (key opens) filter
- `engine/` – Confluence scoring, setup output
- `notifications/` – Telegram notifier (compatible with your existing format)
- `run_detector.py` – CLI entry

## Tests

```bash
python -m pytest tests/ -v
```

Or run individual tests:

```bash
python tests/test_fvg.py
python tests/test_killzone.py
python tests/test_swing.py
```
