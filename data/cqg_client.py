"""
CQG WebAPI bar fetcher. Requires CQG WebAPIPythonSamples repo (clone and set data.cqg.samples_path).
Uses AMP/CQG credentials for real-time futures bar data.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import List

from loguru import logger


def fetch_bars(
    host: str,
    user: str,
    password: str,
    symbol_root: str,
    exchange: str,
    bar_unit: int,
    unit_number: int,
    limit: int,
    samples_path: str,
) -> List[dict]:
    """
    Fetch historical time bars from CQG WebAPI. Requires CQG WebAPIPythonSamples on path.
    symbol_root: e.g. "ES", "NQ". exchange: e.g. "CME".
    bar_unit: CQG BarUnit e.g. 8 = BAR_UNIT_MIN. unit_number: e.g. 5 for 5-min bars.
    Returns list of dicts with open, high, low, close, volume, time (datetime).
    """
    if not samples_path or not Path(samples_path).exists():
        logger.warning("CQG: samples_path not set or missing. Clone WebAPIPythonSamples and set data.cqg.samples_path.")
        return []
    if not user or not password:
        logger.warning("CQG: set CQG_USER and CQG_PASSWORD (e.g. in .env).")
        return []

    try:
        if samples_path not in sys.path:
            sys.path.insert(0, samples_path)
    except Exception:
        pass

    try:
        from WebAPI import webapi_client
        from WebAPI.webapi_2_pb2 import ClientMsg, ServerMsg
        from WebAPI.historical_2_pb2 import TimeBarParameters
        import logon as cqg_logon
        import meta as cqg_meta
    except ImportError as e:
        logger.warning(f"CQG: could not import WebAPI (is samples_path correct?): {e}")
        return []

    client = webapi_client.WebApiClient()
    client.connect(host)
    try:
        base_time_str = cqg_logon.logon(client, user, password)
    except Exception as e:
        logger.warning(f"CQG logon failed: {e}")
        client.disconnect()
        return []

    try:
        contract_metadata = cqg_meta.resolve_symbol(client, symbol_root, 1)
        contract_id = getattr(contract_metadata, "contract_id", None) or getattr(contract_metadata, "id", None)
        if contract_id is None:
            logger.warning("CQG: could not get contract_id for symbol")
            cqg_logon.logoff(client)
            client.disconnect()
            return []
    except Exception as e:
        logger.warning(f"CQG resolve_symbol failed: {e}")
        cqg_logon.logoff(client)
        client.disconnect()
        return []

    # CQG time: from_utc_time is (current_utc_ms - base_ts_ms) - lookback_ms
    try:
        base_dt = datetime.strptime(base_time_str, "%Y-%m-%dT%H:%M:%S")
        base_ts_ms = int(base_dt.timestamp() * 1000)
    except Exception:
        base_ts_ms = 0
    current_utc_ms = int(datetime.utcnow().timestamp() * 1000)
    ms_per_bar = 60000 * unit_number  # 5m = 300000
    lookback_ms = limit * ms_per_bar
    from_utc_time = (current_utc_ms - base_ts_ms) - lookback_ms

    client_msg = ClientMsg()
    tb_request = client_msg.time_bar_requests.add()
    tb_request.request_id = 2
    tb_request.time_bar_parameters.contract_id = contract_id
    tb_request.time_bar_parameters.bar_unit = bar_unit
    tb_request.time_bar_parameters.unit_number = unit_number
    tb_request.time_bar_parameters.from_utc_time = from_utc_time
    client.send_client_message(client_msg)

    bars_out: List[dict] = []
    max_rounds = 100
    while max_rounds > 0:
        max_rounds -= 1
        server_msg = client.receive_server_message()
        if not getattr(server_msg, "time_bar_reports", None):
            continue
        for report in server_msg.time_bar_reports:
            for bar in report.time_bars:
                bar_utc = getattr(bar, "bar_utc_time", 0)
                real_utc_ms = base_ts_ms + bar_utc
                dt = datetime.utcfromtimestamp(real_utc_ms / 1000.0)
                open_p = getattr(bar, "scaled_open_price", 0) or getattr(bar, "open_price", 0)
                high_p = getattr(bar, "scaled_high_price", 0) or getattr(bar, "high_price", 0)
                low_p = getattr(bar, "scaled_low_price", 0) or getattr(bar, "low_price", 0)
                close_p = getattr(bar, "scaled_close_price", 0) or getattr(bar, "close_price", 0)
                vol = getattr(bar, "scaled_volume", 0) or getattr(bar, "volume", 0)
                bars_out.append({
                    "open": float(open_p),
                    "high": float(high_p),
                    "low": float(low_p),
                    "close": float(close_p),
                    "volume": int(vol),
                    "time": dt,
                })
            if report.is_report_complete:
                break
        if any(getattr(r, "is_report_complete", False) for r in server_msg.time_bar_reports):
            break

    cqg_logon.logoff(client)
    client.disconnect()
    return bars_out[-limit:] if len(bars_out) > limit else bars_out
