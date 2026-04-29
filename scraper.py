# scraper.py
# ─────────────────────────────────────────────────────────────
# Fetches live equity quote data from NSE and returns it as a
# pandas DataFrame.  All network calls go through NSESession so
# cookies / headers are handled transparently.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import requests

from config import QUOTE_EQUITY
from nse_session import NSESession

logger = logging.getLogger(__name__)

# ── DataFrame column contract ─────────────────────────────────
COLUMNS = ["Symbol", "Last Price", "Change", "% Change", "High", "Low",
           "Prev Close", "Volume", "Status"]


def fetch_quote(symbol: str, session: NSESession) -> pd.DataFrame:
    """
    Fetch live quote for a single NSE equity symbol.

    Parameters
    ----------
    symbol  : Uppercase NSE ticker, e.g. "RELIANCE"
    session : Shared NSESession instance

    Returns
    -------
    pd.DataFrame with columns defined by COLUMNS above.
    On error returns a one-row DataFrame with Status = error message.
    """
    symbol = symbol.strip().upper()
    try:
        response = session.get(QUOTE_EQUITY, params={"symbol": symbol})
        data = response.json()
        return _parse_quote(symbol, data)

    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response else "?"
        msg = f"HTTP {status_code}"
        logger.warning("fetch_quote(%s): %s", symbol, msg)
        return _error_row(symbol, msg)

    except requests.exceptions.ConnectionError:
        msg = "No network"
        logger.warning("fetch_quote(%s): connection error", symbol)
        return _error_row(symbol, msg)

    except requests.exceptions.Timeout:
        msg = "Timeout"
        logger.warning("fetch_quote(%s): request timed out", symbol)
        return _error_row(symbol, msg)

    except (KeyError, ValueError, TypeError) as exc:
        msg = f"Parse error: {exc}"
        logger.error("fetch_quote(%s): %s", symbol, msg)
        return _error_row(symbol, msg)

    except Exception as exc:  # noqa: BLE001
        msg = f"Error: {exc}"
        logger.exception("fetch_quote(%s): unexpected error", symbol)
        return _error_row(symbol, msg)


def fetch_multiple(symbols: list[str], session: NSESession) -> pd.DataFrame:
    """
    Fetch quotes for multiple symbols and concatenate into one DataFrame.
    """
    frames = [fetch_quote(sym, session) for sym in symbols]
    return pd.concat(frames, ignore_index=True)


# ── Internal helpers ──────────────────────────────────────────

def _parse_quote(symbol: str, data: dict) -> pd.DataFrame:
    """
    Extract fields from the NSE API JSON response.

    NSE response shape (simplified):
    {
      "priceInfo": {
        "lastPrice":        2450.75,
        "change":           -12.30,
        "pChange":          -0.50,
        "intraDayHighLow":  {"max": 2475.00, "min": 2430.00},
        "previousClose":    2463.05,
      },
      "metadata": {
        "tradingStatus": "Market is Open",
        "totalTradedVolume": 1234567
      }
    }
    """
    price_info = data.get("priceInfo", {})
    metadata   = data.get("metadata", {})
    intraday   = price_info.get("intraDayHighLow", {})

    row = {
        "Symbol":      symbol,
        "Last Price":  _safe_float(price_info.get("lastPrice")),
        "Change":      _safe_float(price_info.get("change")),
        "% Change":    _safe_float(price_info.get("pChange")),
        "High":        _safe_float(intraday.get("max") or price_info.get("dayHigh")),
        "Low":         _safe_float(intraday.get("min") or price_info.get("dayLow")),
        "Prev Close":  _safe_float(price_info.get("previousClose")),
        "Volume":      metadata.get("totalTradedVolume", "N/A"),
        "Status":      metadata.get("tradingStatus", "OK"),
    }
    return pd.DataFrame([row], columns=COLUMNS)


def _error_row(symbol: str, message: str) -> pd.DataFrame:
    row = {col: "—" for col in COLUMNS}
    row["Symbol"] = symbol
    row["Status"] = message
    return pd.DataFrame([row], columns=COLUMNS)


def _safe_float(value) -> float | str:
    try:
        return float(value)
    except (TypeError, ValueError):
        return "N/A"