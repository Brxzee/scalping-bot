# Topstep Rithmic connection setup (for bot data)

Your Topstep account uses **Rithmic** for market data. The bot can use the same connection (via `async_rithmic`) to get real-time 5m bars instead of delayed yfinance data.

## Where Topstep documents this

1. **Topstep Help Center**  
   - [R|Trader Pro Connection Instructions](https://help.topstep.com/en/articles/8284189-r-trader-pro-connection-instructions)  
   - [R|Trader Plug-in for Market Data](https://help.topstep.com/en/articles/8284184-r-trader-plug-in-for-market-data)

2. **In your Topstep dashboard**  
   - Log in at topstep.com and check **Help** or **Resources** for “Rithmic” or “R|Trader Pro” connection guides.  
   - Your **username** is your Topstep login (all lowercase for Rithmic).  
   - Your **password** is the one you use in R|Trader Pro (often 6 characters, uppercase, starting with `TST___` — Topstep will have sent this when you set up Rithmic/market data).

## Connection details you need

| Setting       | Value for Topstep   | Where to get it |
|---------------|---------------------|------------------|
| **System**    | `TopstepTrader`     | Topstep help / R|Trader Pro login screen |
| **Gateway**   | `Chicago Area`      | Same; sometimes shown as “ChicagoArea” in APIs |
| **Username**  | Your Topstep login  | Your Topstep account (use **all lowercase** for Rithmic) |
| **Password**  | Your Rithmic password | Same as R|Trader Pro; often 6 chars, uppercase, starts with `TST___` |
| **URL (host)** | Rithmic gateway host | See below |

## Finding the Rithmic gateway URL

- Topstep’s public docs often don’t show the exact **host:port** (e.g. `rituz00100.rithmic.com:443`).  
- **Options:**  
  1. **Topstep support** – Ask: “What is the Rithmic gateway URL (host and port) for TopstepTrader / Chicago Area for API/programmatic access?”  
  2. **R|Trader Pro** – After you connect, some versions show the server or “Connection” details in the UI or logs.  
  3. **NinjaTrader** – If you use NinjaTrader with Topstep, the connection guide may list the Rithmic server; that same host is often used for API.  
- The bot config expects something like: `rithmic_url: "rituzXXXXX.rithmic.com:443"` (Topstep will give you the real host).

## What must be enabled on your account

For **market data** (and thus for the bot to get bars):

- **Market Data: ON** (in R|Trader Pro or in your Topstep/Rithmic settings).  
- **Allow Plug-ins: ON** (needed for Rithmic data access).  
- **Orders** can be ON or OFF for the bot if you only want data; leave as you prefer.

You may also need to complete any **Market Data Requirement** forms Topstep/Rithmic ask for (for the exchanges you trade, e.g. CME).

## How the bot uses this

- You put the **connection details** (and optionally the gateway URL) in **config** or **environment variables** (see repo config and `.env.example`).  
- The bot uses the library `async_rithmic` to connect with those credentials and **system name** `TopstepTrader` (and gateway as provided by Topstep).  
- It requests **historical 5m (and 1H/daily) bars** for NQ/ES so your pipeline runs on Rithmic data instead of yfinance.

## Bot config and .env

1. **In `config/settings.yaml`** (under `data`):
   - Set `provider: rithmic`.
   - Under `rithmic`: set `url` to the gateway URL once you have it (default is a placeholder; get the real one from Topstep). `system_name: TopstepTrader` and `app_name: scalping_bot` are already set.

2. **In `.env`** (project root; do not commit this file):
   - `RITHMIC_USER=your_topstep_username` (all lowercase).
   - `RITHMIC_PASSWORD=your_rithmic_password` (same as R|Trader Pro).

   The bot loads these via `config/__init__.py` and passes them to the Rithmic client. Never put credentials in `settings.yaml` or in git.

3. **Run the bot** – Use the same commands as before (`python run_detector.py --realtime`, `python backtest.py`). With `provider: rithmic` the fetcher will use Topstep/Rithmic for NQ and ES bar data.

## Quick checklist

- [ ] Topstep login (username, all lowercase for Rithmic).  
- [ ] Rithmic password (same as R|Trader Pro; often `TST___...`).  
- [ ] System: **TopstepTrader**, Gateway: **Chicago Area**.  
- [ ] Rithmic gateway URL (host:port) from Topstep support or R|Trader Pro/NinjaTrader docs.  
- [ ] Market Data (and if applicable, Allow Plug-ins) enabled for your account.  
- [ ] `.env` with `RITHMIC_USER` and `RITHMIC_PASSWORD`; `config/settings.yaml` with `data.provider: rithmic` and `data.rithmic.url`.
