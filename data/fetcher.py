"""
Cost-effective OHLCV data fetcher.
Supports yfinance (free), ccxt (crypto), rithmic (Topstep real-time), cqg (AMP/CQG real-time), polygon (free tier), and ibkr (Interactive Brokers real-time).
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from typing import Literal

import pandas as pd

from loguru import logger

Provider = Literal["yfinance", "ccxt", "rithmic", "cqg", "polygon", "ibkr"]


def _tf_to_ccxt(tf: str) -> str:
    """Map 15m, 1h etc to ccxt timeframe."""
    m = re.match(r"^(\d+)(m|h|d)$", tf.strip().lower())
    if not m:
        return "1h"
    num, unit = m.groups()
    if unit == "m":
        return f"{num}m"
    if unit == "h":
        return f"{num}h"
    return f"{num}d"


def _tf_to_yfinance_interval(tf: str) -> str:
    """Map 1m, 5m, 15m, 1h, 1d to yfinance interval."""
    tf = tf.strip().lower()
    if tf in ("1m", "2m", "5m", "15m", "30m", "60m", "1h", "90m"):
        return "1h" if tf in ("1h", "60m") else tf.replace("h", "m")
    if tf in ("1d", "5d", "1wk", "1mo"):
        return tf
    return "1h"


def _symbol_to_rithmic_root(symbol: str) -> str | None:
    """Map NQ=F, ES=F to Rithmic root (NQ, ES)."""
    u = (symbol or "").upper()
    if u.startswith("ES=") or u == "ES":
        return "ES"
    if u.startswith("NQ=") or u == "NQ":
        return "NQ"
    return None


def _symbol_to_cqg_root(symbol: str) -> str | None:
    """Map NQ=F, ES=F to CQG symbol root (NQ, ES)."""
    u = (symbol or "").upper()
    if u.startswith("ES=") or u == "ES":
        return "ES"
    if u.startswith("NQ=") or u == "NQ":
        return "NQ"
    return None


def _symbol_to_polygon_root(symbol: str) -> str | None:
    """Map NQ=F, ES=F to Polygon base symbol (NQ, ES)."""
    u = (symbol or "").upper()
    if u.startswith("ES=") or u == "ES":
        return "ES"
    if u.startswith("NQ=") or u == "NQ":
        return "NQ"
    return None


def _tf_to_polygon_resolution(timeframe: str) -> str:
    """Map timeframe string to Polygon resolution (e.g., 5m -> '5mins', 1h -> '1hour')."""
    tf = (timeframe or "5m").strip().lower()
    m = re.match(r"^(\d+)(m|h|d)$", tf)
    if not m:
        return "5mins"
    num, unit = m.groups()
    n = int(num)
    if unit == "m":
        if n == 1:
            return "1min"
        return f"{n}mins"
    if unit == "h":
        if n == 1:
            return "1hour"
        return f"{n}hours"
    if unit == "d":
        if n == 1:
            return "1day"
        return f"{n}days"
    return "5mins"


# CQG WebAPI BarUnit: minute = 8 (BAR_UNIT_MIN in samples)
_CQG_BAR_UNIT_MIN = 8


def _tf_to_cqg_bar(timeframe: str) -> tuple[int, int]:
    """Map timeframe string to CQG bar_unit, unit_number. Uses minute bars (unit 8)."""
    interval_mins = _tf_to_interval_minutes(timeframe)
    unit_num = min(interval_mins, 60 * 24 - 1) if interval_mins < 24 * 60 else 1440
    return (_CQG_BAR_UNIT_MIN, unit_num)


class DataFetcher:
    """Fetch OHLCV with timezone-aware index. yfinance, ccxt, rithmic (Topstep), cqg (AMP), polygon, or ibkr (IBKR)."""

    def __init__(
        self,
        provider: Provider = "yfinance",
        exchange_id: str = "binance",
        timezone: str = "America/New_York",
        rithmic_url: str = "",
        rithmic_system_name: str = "TopstepTrader",
        rithmic_app_name: str = "scalping_bot",
        rithmic_user: str = "",
        rithmic_password: str = "",
        cqg_host: str = "",
        cqg_user: str = "",
        cqg_password: str = "",
        cqg_samples_path: str = "",
        polygon_api_key: str = "",
        ibkr_host: str = "127.0.0.1",
        ibkr_port: int = 4002,
        ibkr_client_id: int = 1,
        ibkr_use_rth: bool = True,
    ):
        self.provider = provider
        self.exchange_id = exchange_id
        self.timezone = timezone
        self._exchange = None
        self.rithmic_url = rithmic_url or "rituz00100.rithmic.com:443"
        self.rithmic_system_name = rithmic_system_name
        self.rithmic_app_name = rithmic_app_name
        self.rithmic_user = rithmic_user
        self.rithmic_password = rithmic_password
        self.cqg_host = cqg_host or "wss://api.cqg.com:443"
        self.cqg_user = cqg_user
        self.cqg_password = cqg_password
        self.cqg_samples_path = cqg_samples_path
        self.polygon_api_key = polygon_api_key
        self.ibkr_host = ibkr_host
        self.ibkr_port = ibkr_port
        self.ibkr_client_id = ibkr_client_id
        self.ibkr_use_rth = ibkr_use_rth

    def _get_exchange(self):
        if self._exchange is not None:
            return self._exchange
        import ccxt
        self._exchange = getattr(ccxt, self.exchange_id)({"enableRateLimit": True})
        return self._exchange

    def fetch(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
    ) -> pd.DataFrame:
        """
        Return DataFrame with columns: open, high, low, close, volume (if available).
        Index: timezone-aware datetime.
        """
        if self.provider == "yfinance":
            return self._fetch_yfinance(symbol, timeframe, limit)
        if self.provider == "rithmic":
            return self._fetch_rithmic(symbol, timeframe, limit)
        if self.provider == "cqg":
            return self._fetch_cqg(symbol, timeframe, limit)
        if self.provider == "polygon":
            return self._fetch_polygon(symbol, timeframe, limit)
        if self.provider == "ibkr":
            return self._fetch_ibkr(symbol, timeframe, limit)
        return self._fetch_ccxt(symbol, timeframe, limit)

    def _fetch_yfinance(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        import yfinance as yf
        interval = _tf_to_yfinance_interval(timeframe)
        # yfinance 1m only last 7 days; 2m/5m/15m/1h more history
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="max", interval=interval, auto_adjust=True)
        if df.empty:
            logger.warning(f"yfinance returned no data for {symbol} {interval}")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        df = df[["open", "high", "low", "close", "volume"]].tail(limit)
        df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(self.timezone)
        else:
            df.index = df.index.tz_convert(self.timezone)
        return df

    def _fetch_ccxt(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        ex = self._get_exchange()
        tf = _tf_to_ccxt(timeframe)
        ohlcv = ex.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["time"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.set_index("time").drop(columns=["timestamp"])
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(self.timezone)
        else:
            df.index = df.index.tz_convert(self.timezone)
        return df

    def _fetch_rithmic(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Fetch OHLCV via Rithmic (Topstep). Runs async in sync context."""
        try:
            return asyncio.run(
                _fetch_rithmic_async(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=limit,
                    url=self.rithmic_url,
                    system_name=self.rithmic_system_name,
                    app_name=self.rithmic_app_name,
                    user=self.rithmic_user,
                    password=self.rithmic_password,
                    timezone=self.timezone,
                )
            )
        except Exception as e:
            logger.warning(f"Rithmic fetch failed for {symbol} {timeframe}: {e}")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def _fetch_cqg(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Fetch OHLCV via CQG WebAPI (AMP). Requires WebAPIPythonSamples at data.cqg.samples_path."""
        from .cqg_client import fetch_bars
        root = _symbol_to_cqg_root(symbol)
        if not root:
            logger.warning(f"CQG: unsupported symbol {symbol}; use NQ=F or ES=F")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        bar_unit, unit_number = _tf_to_cqg_bar(timeframe)
        bars = fetch_bars(
            host=self.cqg_host,
            user=self.cqg_user,
            password=self.cqg_password,
            symbol_root=root,
            exchange="CME",
            bar_unit=bar_unit,
            unit_number=unit_number,
            limit=limit,
            samples_path=self.cqg_samples_path,
        )
        if not bars:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(bars).set_index("time")
        df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(self.timezone)
        else:
            df.index = df.index.tz_convert(self.timezone)
        return df.tail(limit)

    def _fetch_polygon(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Fetch OHLCV via Polygon.io REST API (free tier: 5 calls/min, minute bars)."""
        if not self.polygon_api_key:
            logger.warning("Polygon: set POLYGON_API_KEY (e.g. in .env)")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        root = _symbol_to_polygon_root(symbol)
        if not root:
            logger.warning(f"Polygon: unsupported symbol {symbol}; use NQ=F or ES=F")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        try:
            import requests
        except ImportError:
            logger.warning("Polygon: install 'requests' package: pip install requests")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        resolution = _tf_to_polygon_resolution(timeframe)
        # Polygon FUTURES API: GET /futures/v1/aggs/{ticker} (not stocks v2/aggs/.../range/...)
        # Ticker format: ES + month code + year digit (e.g., ESU5 = ES Sep 2025)

        # Get front-month contract ticker
        now = datetime.now()
        month_codes = "FGHJKMNQUVXZ"  # CME: F=Jan,G=Feb,H=Mar,J=Apr,K=May,M=Jun,N=Jul,Q=Aug,U=Sep,V=Oct,X=Nov,Z=Dec
        current_month_idx = now.month - 1
        tickers_to_try = []
        for offset in range(3):
            month_idx = (current_month_idx + offset) % 12
            year_digit = str((now.year + (current_month_idx + offset) // 12) % 10)
            month_code = month_codes[month_idx]
            tickers_to_try.append(f"{root}{month_code}{year_digit}")

        # Start date for window_start.gte (limit bars ago)
        interval_mins = _tf_to_interval_minutes(timeframe)
        start_dt = datetime.now() - timedelta(minutes=limit * interval_mins)
        start_date_str = start_dt.strftime("%Y-%m-%d")

        # Try Massive.com first, then Polygon.io (same API; rebrand may use either host)
        api_bases = ["https://api.polygon.io", "https://api.massive.com"]
        bars_data = None
        last_error = None
        for ticker in tickers_to_try:
            for base in api_bases:
                try:
                    url = f"{base}/futures/v1/aggs/{ticker}"
                    params = {
                        "resolution": resolution,
                        "limit": limit,
                        "sort": "window_start.asc",
                        "apiKey": self.polygon_api_key,
                    }
                    # Optional: filter by start date if API supports it
                    params["window_start.gte"] = start_date_str
                    resp = requests.get(url, params=params, timeout=15)
                    try:
                        data = resp.json()
                    except Exception:
                        data = {}
                    if data.get("status") == "OK" and data.get("results"):
                        bars_data = data.get("results", [])
                        break
                    # Capture API error for logging
                    last_error = (
                        data.get("error")
                        or data.get("message")
                        or (f"{resp.status_code} {resp.reason}" if not resp.ok else None)
                    )
                except requests.exceptions.RequestException as e:
                    last_error = str(e)
                except Exception as e:
                    last_error = str(e)
            if bars_data:
                break

        if not bars_data:
            msg = f"Polygon: no data for {root} (tried {tickers_to_try})"
            if last_error:
                msg += f". API: {last_error}"
            logger.warning(msg)
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        # Build DataFrame from bars (futures API uses window_start in ns, open/high/low/close/volume)
        rows = []
        for bar in bars_data:
            ts_ns = bar.get("window_start", 0)  # nanoseconds
            if ts_ns == 0:
                continue
            dt = datetime.fromtimestamp(ts_ns / 1_000_000_000.0)
            rows.append({
                "open": float(bar.get("open", 0)),
                "high": float(bar.get("high", 0)),
                "low": float(bar.get("low", 0)),
                "close": float(bar.get("close", 0)),
                "volume": int(bar.get("volume", 0)),
                "time": dt,
            })

        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(rows).set_index("time")
        df.index = pd.to_datetime(df.index)
        # Polygon data is in Central Time (CT)
        if df.index.tz is None:
            df.index = df.index.tz_localize("America/Chicago").tz_convert(self.timezone)
        else:
            df.index = df.index.tz_convert(self.timezone)
        return df.tail(limit)

    def _fetch_ibkr(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Fetch OHLCV via Interactive Brokers (ib_insync). Requires TWS/IB Gateway running."""
        try:
            from ib_insync import IB, Future, util
        except ImportError:
            logger.warning("IBKR: install 'ib_insync' package: pip install ib_insync")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        root = _symbol_to_rithmic_root(symbol)  # Reuse same mapping: NQ=F -> NQ, ES=F -> ES
        if not root:
            logger.warning(f"IBKR: unsupported symbol {symbol}; use NQ=F or ES=F")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        # Map timeframe to IBKR bar size (must use exact strings: 1 min, 2 mins, 5 mins, 1 hour, 1 day, etc.)
        interval_mins = _tf_to_interval_minutes(timeframe)
        if interval_mins < 60:
            if interval_mins == 1:
                bar_size = "1 min"
            elif interval_mins in (2, 3, 5, 10, 15, 20, 30):
                bar_size = f"{interval_mins} mins"
            else:
                bar_size = "5 mins"  # fallback to nearest
        elif interval_mins < 24 * 60:
            hours = interval_mins // 60
            if hours in (1, 2, 3, 4, 8):
                bar_size = f"{hours} hour" if hours == 1 else f"{hours} hours"
            else:
                bar_size = "1 hour"
        else:
            bar_size = "1 day"

        # Calculate duration (IBKR format: "X D" for days, "X W" for weeks, etc.)
        duration_days = max(1, (limit * interval_mins) // (24 * 60))
        duration = f"{duration_days} D"

        ib = IB()
        try:
            ib.connect(self.ibkr_host, self.ibkr_port, clientId=self.ibkr_client_id)
        except Exception as e:
            logger.warning(f"IBKR: failed to connect to {self.ibkr_host}:{self.ibkr_port}: {e}")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        try:
            # CME NQ/ES expire quarterly (Mar, Jun, Sep, Dec); need lastTradeDateOrContractMonth (YYYYMM)
            now = datetime.now()
            year = now.year
            month = now.month
            # Next quarterly month: 3,6,9,12
            quarters = (3, 6, 9, 12)
            for q in quarters:
                if month <= q:
                    front_yyyymm = f"{year}{q:02d}"
                    break
            else:
                front_yyyymm = f"{year + 1}03"
            contract = Future(
                symbol=root,
                lastTradeDateOrContractMonth=front_yyyymm,
                exchange="CME",
                currency="USD",
            )
            # Qualify so IB fills conId/localSymbol (required for historical data)
            qualified = ib.qualifyContracts(contract)
            if not qualified:
                logger.warning(f"IBKR: could not qualify contract {root} {front_yyyymm}")
                ib.disconnect()
                return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
            contract = qualified[0]
            # Request historical data (useRTH=False = include extended hours for more bars / backtest alignment)
            bars = ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow="TRADES",
                useRTH=self.ibkr_use_rth,
            )
            ib.sleep(1)  # Wait for data

            if not bars:
                logger.warning(f"IBKR: no bars returned for {root}")
                ib.disconnect()
                return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

            # Convert to DataFrame (build naive datetime from bar.date to avoid tzinfo/replace issues)
            rows = []
            for bar in bars:
                d = bar.date
                try:
                    dt = datetime(d.year, d.month, d.day, d.hour, d.minute, d.second, getattr(d, "microsecond", 0))
                except Exception:
                    dt = datetime.fromtimestamp(d.timestamp()) if hasattr(d, "timestamp") else d
                rows.append({
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": int(bar.volume),
                    "time": dt,
                })

            if not rows:
                ib.disconnect()
                return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

            df = pd.DataFrame(rows).set_index("time")
            df.index = pd.to_datetime(df.index)
            # IBKR returns data in exchange timezone (CME = CT); convert to configured timezone
            if df.index.tz is None:
                df.index = df.index.tz_localize("America/Chicago").tz_convert(self.timezone)
            else:
                df.index = df.index.tz_convert(self.timezone)
            return df.tail(limit)

        except Exception as e:
            logger.warning(f"IBKR fetch failed for {symbol} {timeframe}: {e}")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        finally:
            try:
                ib.disconnect()
            except Exception:
                pass


async def _fetch_rithmic_async(
    symbol: str,
    timeframe: str,
    limit: int,
    url: str,
    system_name: str,
    app_name: str,
    user: str,
    password: str,
    timezone: str,
) -> pd.DataFrame:
    """Fetch historical time bars from Rithmic; build DataFrame."""
    from zoneinfo import ZoneInfo

    root = _symbol_to_rithmic_root(symbol)
    if not root or not user or not password:
        if not user or not password:
            logger.warning("Rithmic: set RITHMIC_USER and RITHMIC_PASSWORD (e.g. in .env)")
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    from async_rithmic import RithmicClient, TimeBarType

    interval_mins = _tf_to_interval_minutes(timeframe)
    exchange = "CME"

    client = RithmicClient(
        user=user,
        password=password,
        system_name=system_name,
        app_name=app_name,
        app_version="1.0",
        url=url,
    )
    await client.connect()
    try:
        security_code = await client.get_front_month_contract(root, exchange)
    except Exception as e:
        logger.warning(f"Rithmic get_front_month_contract failed: {e}")
        await client.disconnect()
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    tz = ZoneInfo(timezone) if timezone else ZoneInfo("America/New_York")
    end_dt = datetime.now(tz)
    if interval_mins >= 24 * 60:
        start_dt = end_dt - timedelta(days=limit)
        bar_type = TimeBarType.DAILY_BAR
        interval_param = 1
    else:
        start_dt = end_dt - timedelta(minutes=limit * interval_mins)
        bar_type = TimeBarType.MINUTE_BAR
        interval_param = min(interval_mins, 60 * 24 - 1)

    try:
        bars = await client.get_historical_time_bars(
            security_code,
            exchange,
            start_dt,
            end_dt,
            bar_type,
            interval_param,
        )
    except Exception as e:
        logger.warning(f"Rithmic get_historical_time_bars failed: {e}")
        await client.disconnect()
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    await client.disconnect()

    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    # Build DataFrame from bar dicts (async_rithmic: open_price/high_price/... or open/high/...)
    rows = []
    for b in bars:
        ts = b.get("bar_end_datetime") or b.get("datetime") or b.get("timestamp")
        if ts is None:
            continue
        rows.append({
            "open": float(b.get("open") or b.get("open_price", 0)),
            "high": float(b.get("high") or b.get("high_price", 0)),
            "low": float(b.get("low") or b.get("low_price", 0)),
            "close": float(b.get("close") or b.get("close_price", 0)),
            "volume": int(b.get("volume", 0)),
            "time": ts,
        })
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(rows)
    df = df.set_index("time")
    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(timezone)
    else:
        df.index = df.index.tz_convert(timezone)
    return df.tail(limit)


def _tf_to_interval_minutes(tf: str) -> int:
    """Map timeframe string to interval minutes for Rithmic."""
    tf = (tf or "5m").strip().lower()
    m = re.match(r"^(\d+)(m|h|d)$", tf)
    if not m:
        return 5
    num, unit = m.groups()
    n = int(num)
    if unit == "m":
        return n
    if unit == "h":
        return n * 60
    if unit == "d":
        return n * 24 * 60
    return 5


def get_fetcher(config: dict) -> DataFetcher:
    """Build DataFetcher from config."""
    data_cfg = config.get("data", {})
    rithmic_cfg = data_cfg.get("rithmic", {})
    cqg_cfg = data_cfg.get("cqg", {})
    polygon_cfg = data_cfg.get("polygon", {})
    ibkr_cfg = data_cfg.get("ibkr", {})
    return DataFetcher(
        provider=data_cfg.get("provider", "yfinance"),
        exchange_id=data_cfg.get("exchange_id", "binance"),
        timezone=data_cfg.get("timezone", "America/New_York"),
        rithmic_url=rithmic_cfg.get("url", "rituz00100.rithmic.com:443"),
        rithmic_system_name=rithmic_cfg.get("system_name", "TopstepTrader"),
        rithmic_app_name=rithmic_cfg.get("app_name", "scalping_bot"),
        rithmic_user=rithmic_cfg.get("user", ""),
        rithmic_password=rithmic_cfg.get("password", ""),
        cqg_host=cqg_cfg.get("host", "wss://api.cqg.com:443"),
        cqg_user=cqg_cfg.get("user", ""),
        cqg_password=cqg_cfg.get("password", ""),
        cqg_samples_path=cqg_cfg.get("samples_path", ""),
        polygon_api_key=polygon_cfg.get("api_key", ""),
        ibkr_host=ibkr_cfg.get("host", "127.0.0.1"),
        ibkr_port=ibkr_cfg.get("port", 4002),
        ibkr_client_id=ibkr_cfg.get("client_id", 1),
        ibkr_use_rth=ibkr_cfg.get("use_rth", True),
    )
