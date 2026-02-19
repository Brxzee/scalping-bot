# Interactive Brokers (IBKR) setup (real-time futures data)

**Interactive Brokers** provides real-time CME futures data (NQ, ES) with a funded account. No extra data fees for basic CME market data subscriptions.

## Requirements

1. **IBKR account** (paper or live trading account)
2. **TWS (Trader Workstation)** or **IB Gateway** running and connected
3. **Market data subscriptions** enabled for CME (NQ, ES) — usually included with account

## Setup steps

### 1. Install TWS or IB Gateway

- **TWS**: Full trading platform — download from [ibkr.com](https://www.interactivebrokers.com/en/index.php?f=16042)
- **IB Gateway**: Lightweight API-only — download from [ibkr.com](https://www.interactivebrokers.com/en/index.php?f=16457)

Both work; IB Gateway is lighter if you only need API access.

### 2. Enable API access

In TWS/IB Gateway:
1. Go to **Configure** → **API** → **Settings**
2. Check **Enable ActiveX and Socket Clients**
3. Add **127.0.0.1** to trusted IPs (or leave blank for localhost only)
4. Set **Socket port** to match your app:
   - **IB Gateway**: **4002** (paper) or **4001** (live)
   - **TWS**: **7497** (paper) or **7496** (live)
5. Click **OK** and restart TWS/Gateway

### 3. Connect and subscribe to market data

1. Log into TWS/IB Gateway with your IBKR account
2. Ensure you're connected (green status)
3. Subscribe to **CME** market data if prompted (NQ and ES are usually included)

### 4. Bot config

In **`config/settings.yaml`**:
- Set `data.provider: ibkr`
- Under `ibkr`:
  - `host`: Usually `127.0.0.1` (localhost)
  - `port`: **IB Gateway** = `4002` (paper) or `4001` (live). **TWS** = `7497` (paper) or `7496` (live)
  - `client_id`: Unique integer (e.g., `1`). Must be different from any other IBKR API connections running.
  - `use_rth`: `true` = regular trading hours only (fewer bars). `false` = include extended hours (more bars; useful if you trade on Topstep and want full-session backtest).

### 5. Run the bot

```bash
python run_detector.py --realtime
python backtest.py --days 90
```

The bot will connect to TWS/Gateway and fetch NQ/ES bars.

## Troubleshooting

**"IBKR: failed to connect"**
- Ensure TWS/IB Gateway is running and connected
- Check that API is enabled in TWS/Gateway settings
- Verify `host` and `port` match your TWS/Gateway settings
- Ensure firewall isn't blocking localhost connections

**"IBKR: no bars returned"**
- Ensure you're subscribed to CME market data in TWS/Gateway
- Check that NQ/ES contracts are available (front month resolves automatically)
- Try requesting a shorter duration (IBKR has limits on historical data)

**Multiple connections**
- Each IBKR API connection needs a unique `client_id` (1, 2, 3, etc.)
- If you have other scripts/software using IBKR API, use different client IDs

## Ports

**IB Gateway** (what you have running) uses different ports than TWS:
- **4002**: IB Gateway paper trading
- **4001**: IB Gateway live trading

**TWS** (Trader Workstation):
- **7497**: TWS paper trading
- **7496**: TWS live trading

If you get "Connection refused" on 7497, you're likely using **IB Gateway** — set `ibkr.port: 4002` (paper) or `4001` (live) in `config/settings.yaml`.

## Quick checklist

- [ ] IBKR account (paper or live)
- [ ] TWS or IB Gateway installed and running
- [ ] API enabled in TWS/Gateway settings (port 7497/7496)
- [ ] Connected to IBKR and subscribed to CME data
- [ ] `config/settings.yaml`: `data.provider: ibkr`, `ibkr.host`, `ibkr.port`, `ibkr.client_id`
- [ ] Run bot — it connects to TWS/Gateway and fetches NQ/ES bars
