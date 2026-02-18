"""
Cost-effective OHLCV data fetcher.
Supports yfinance (free equities/forex) and ccxt (free crypto, low-latency).
"""
from __future__ import annotations

import re
from typing import Literal

import pandas as pd

from loguru import logger

Provider = Literal["yfinance", "ccxt"]


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


class DataFetcher:
    """Fetch OHLCV with timezone-aware index. Cheapest: yfinance or ccxt."""

    def __init__(
        self,
        provider: Provider = "yfinance",
        exchange_id: str = "binance",
        timezone: str = "America/New_York",
    ):
        self.provider = provider
        self.exchange_id = exchange_id
        self.timezone = timezone
        self._exchange = None

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


def get_fetcher(config: dict) -> DataFetcher:
    """Build DataFetcher from config."""
    data_cfg = config.get("data", {})
    return DataFetcher(
        provider=data_cfg.get("provider", "yfinance"),
        exchange_id=data_cfg.get("exchange_id", "binance"),
        timezone=data_cfg.get("timezone", "America/New_York"),
    )
