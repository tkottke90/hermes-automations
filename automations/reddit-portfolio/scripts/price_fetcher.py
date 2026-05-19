#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
price_fetcher.py — Real-time stock price fetching via yfinance.
Includes 60-second in-memory cache and graceful fallback for unavailable tickers.
"""

import time
import datetime
import yfinance as yf

_cache: dict = {}  # ticker -> (timestamp, data)
CACHE_TTL = 60  # seconds

_market_state_cache: dict = {"state": None, "fetched_at": None}
MARKET_STATE_TTL = 300  # seconds (5 minutes)


def get_price(ticker: str) -> dict | None:
    """
    Fetch current price info for a ticker.
    Returns dict with keys: ticker, price, open, prev_close, volume, market_cap, market_open, error
    Returns None if ticker is completely unavailable.
    """
    ticker = ticker.upper().strip()
    now = time.time()

    # Return cached value if fresh
    if ticker in _cache:
        ts, data = _cache[ticker]
        if now - ts < CACHE_TTL:
            return data

    try:
        t = yf.Ticker(ticker)
        info = t.fast_info

        price = getattr(info, "last_price", None)
        if price is None or price == 0:
            # Try history as fallback
            hist = t.history(period="1d", interval="1m")
            if hist.empty:
                result = {"ticker": ticker, "price": None, "error": "no_data"}
                _cache[ticker] = (now, result)
                return result
            price = float(hist["Close"].iloc[-1])

        result = {
            "ticker": ticker,
            "price": round(float(price), 4),
            "open": round(float(getattr(info, "open", price) or price), 4),
            "prev_close": round(float(getattr(info, "previous_close", price) or price), 4),
            "volume": int(getattr(info, "three_month_average_volume", 0) or 0),
            "market_cap": getattr(info, "market_cap", None),
            "market_open": _is_market_open(),
            "error": None,
        }
    except Exception as e:
        result = {"ticker": ticker, "price": None, "error": str(e)}

    _cache[ticker] = (now, result)
    return result


def get_prices(tickers: list[str]) -> dict[str, dict]:
    """Fetch prices for a list of tickers. Returns dict keyed by ticker."""
    return {t: get_price(t) for t in tickers}


def _is_market_open_timebased() -> bool:
    """Fallback: time-based check (9:30 AM – 4:00 PM ET, Mon–Fri). No holiday awareness."""
    import zoneinfo
    now_et = datetime.datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close


def _is_market_open() -> bool:
    """Check if US market is open via yfinance marketState (holiday-aware).
    Caches the result for 5 minutes. Falls back to time-based check on API error."""
    now = datetime.datetime.utcnow()
    fetched_at = _market_state_cache["fetched_at"]
    if fetched_at is None or (now - fetched_at).total_seconds() > MARKET_STATE_TTL:
        try:
            info = yf.Ticker("SPY").info
            _market_state_cache["state"] = info.get("marketState", "CLOSED")
            _market_state_cache["fetched_at"] = now
        except Exception:
            return _is_market_open_timebased()
    return _market_state_cache["state"] == "REGULAR"


def is_market_open() -> bool:
    return _is_market_open()


if __name__ == "__main__":
    # Quick test
    import json
    test_tickers = ["NXXT", "GDC", "DVLT", "AAPL", "FAKEXYZ"]
    for t in test_tickers:
        result = get_price(t)
        print(json.dumps(result, indent=2))
