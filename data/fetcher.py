"""
Cost-effective OHLCV data fetcher.
Supports yfinance (free), ccxt (crypto), rithmic (Topstep real-time), and cqg (AMP/CQG real-time).
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from typing import Literal

import pandas as pd

from loguru import logger

Provider = Literal["yfinance", "ccxt", "rithmic", "cqg"]


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


# CQG WebAPI BarUnit: minute = 8 (BAR_UNIT_MIN in samples)
_CQG_BAR_UNIT_MIN = 8


def _tf_to_cqg_bar(timeframe: str) -> tuple[int, int]:
    """Map timeframe string to CQG bar_unit, unit_number. Uses minute bars (unit 8)."""
    interval_mins = _tf_to_interval_minutes(timeframe)
    unit_num = min(interval_mins, 60 * 24 - 1) if interval_mins < 24 * 60 else 1440
    return (_CQG_BAR_UNIT_MIN, unit_num)


class DataFetcher:
    """Fetch OHLCV with timezone-aware index. yfinance, ccxt, rithmic (Topstep), or cqg (AMP)."""

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
    )
