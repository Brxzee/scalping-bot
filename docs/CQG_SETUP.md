# CQG WebAPI setup (AMP / Quantower-style data)

You can use **CQG** (e.g. via AMP or a CQG data feed) for real-time futures bar data instead of delayed yfinance. The bot uses the official **CQG WebAPIPythonSamples** repo to connect and request time bars (e.g. 5m NQ/ES).

## Option: AMP + CQG

If you have an **AMP Futures** (or similar) account with CQG data, you can use CQG WebAPI credentials for the bot. Your broker will provide:

- **CQG WebAPI host** (e.g. `wss://api.cqg.com:443` or a demo URL).
- **Username / password** for the WebAPI (often the same as your CQG/AMP login; confirm with AMP).

## What you need

1. **CQG WebAPIPythonSamples**  
   Clone the official samples repo (required for the bot to call the CQG WebAPI):

   ```bash
   git clone https://github.com/cqg/WebAPIPythonSamples.git
   ```

2. **Path to the repo**  
   Set `data.cqg.samples_path` in `config/settings.yaml` to the **full path** of the cloned repo (e.g. `/Users/you/WebAPIPythonSamples`).

3. **Credentials**  
   Put CQG WebAPI username and password in `.env` (do not commit):

   ```
   CQG_USER=your_cqg_username
   CQG_PASSWORD=your_cqg_password
   ```

   The bot loads these in `config/__init__.py` and passes them to the CQG client.

## Bot config

1. In **`config/settings.yaml`** (under `data`):
   - Set `provider: cqg`.
   - Under `cqg`:
     - `host`: CQG WebAPI host (e.g. `wss://api.cqg.com:443`; use the URL your broker or CQG docs specify).
     - `samples_path`: Full path to the **WebAPIPythonSamples** repo root.

2. In **`.env`** (project root):
   - `CQG_USER=...`
   - `CQG_PASSWORD=...`

3. Run the bot as usual: `python run_detector.py --realtime`, `python backtest.py`. With `provider: cqg`, the fetcher will use CQG for NQ and ES bar data.

## Supported symbols

Same as Rithmic: **NQ** and **ES** (front-month continuous). Config symbols `NQ=F` and `ES=F` are mapped to CQG roots `NQ` and `ES`.

## Quick checklist

- [ ] WebAPIPythonSamples repo cloned; `data.cqg.samples_path` set to its path.
- [ ] CQG WebAPI host from your broker (e.g. AMP).
- [ ] `.env` with `CQG_USER` and `CQG_PASSWORD`.
- [ ] `config/settings.yaml`: `data.provider: cqg`, `data.cqg.host`, `data.cqg.samples_path`.
