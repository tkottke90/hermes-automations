#!/usr/bin/env python3
"""
Stock Price Monitor
- Reads all tickers from ~/.hermes/finance/stocks/tickers.json
- Alerts if price crosses configurable thresholds per ticker
- Alerts if price has increased >20% in the last 24 hours
- Tracks day-open price and sends a daily summary after 4:55 PM CST (22:55 UTC)
- Runs every 15 minutes Mon-Fri 13:00-23:00 UTC; silent if no conditions are met

Usage:
    python3 stock_monitor.py           # runs all tickers in tickers.json
    python3 stock_monitor.py SRXH      # runs a single specific ticker
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yfinance as yf
except ImportError:
    os.system(f"{sys.executable} -m pip install yfinance -q")
    import yfinance as yf

# --- Centralized config and data directories ---
BASE_DIR     = os.path.expanduser("~/.hermes/finance/stocks")
TICKERS_FILE = os.path.join(BASE_DIR, "tickers.json")
TICKERS_DIR  = os.path.join(BASE_DIR, "tickers")

# Daily summary fires on the first run at or after 22:55 UTC (4:55 PM CST / 5:55 PM CDT)
SUMMARY_HOUR_UTC   = 22
SUMMARY_MINUTE_UTC = 55

sys.path.insert(0, str(Path.home() / ".hermes" / "lib"))
from pushover import send_notification as send_pushover

DEFAULT_CONFIG = {
    "threshold_low":    None,   # None = disabled
    "threshold_high":   None,
    "change_alert_pct": 20.0,
}

# ----------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------

def load_all_ticker_configs():
    if os.path.exists(TICKERS_FILE):
        with open(TICKERS_FILE) as f:
            return json.load(f)
    return {}

def load_state(ticker):
    state_file = os.path.join(TICKERS_DIR, f"{ticker.lower()}_state.json")
    if os.path.exists(state_file):
        with open(state_file) as f:
            return json.load(f)
    return {}

def save_state(ticker, state):
    os.makedirs(TICKERS_DIR, exist_ok=True)
    state_file = os.path.join(TICKERS_DIR, f"{ticker.lower()}_state.json")
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)

def get_price(ticker):
    t = yf.Ticker(ticker)
    return round(float(t.fast_info.last_price), 4)

def pct_change(new, old):
    return ((new - old) / old) * 100

# ----------------------------------------------------------------
# Per-ticker monitor
# ----------------------------------------------------------------

def monitor_ticker(ticker, config, now):
    today_str      = now.strftime("%Y-%m-%d")
    threshold_low  = config.get("threshold_low")
    threshold_high = config.get("threshold_high")
    change_alert   = config.get("change_alert_pct", DEFAULT_CONFIG["change_alert_pct"])

    state  = load_state(ticker)
    alerts = []

    try:
        price = get_price(ticker)
    except Exception as e:
        send_pushover(f"{ticker} Monitor Error", f"⚠️ Failed to fetch price: {e}", sound="siren")
        return

    # --- Day-open tracking ---
    if state.get("day_open_date") != today_str:
        state["day_open_price"] = price
        state["day_open_date"]  = today_str
    day_open_price = state["day_open_price"]

    # --- Threshold alerts (edge-triggered) ---
    crossed_low  = state.get("crossed_low", False)
    crossed_high = state.get("crossed_high", False)

    if threshold_low is not None:
        if price > threshold_low and not crossed_low:
            alerts.append(f"📈 {ticker} crossed above ${threshold_low:.2f} — current: ${price:.4f}")
            crossed_low = True
        elif price <= threshold_low and crossed_low:
            crossed_low = False

    if threshold_high is not None:
        if price > threshold_high and not crossed_high:
            alerts.append(f"🚀 {ticker} crossed above ${threshold_high:.2f} — current: ${price:.4f}")
            crossed_high = True
        elif price <= threshold_high and crossed_high:
            crossed_high = False

    # --- 24-hour rolling change alert ---
    baseline_price    = state.get("price")
    baseline_time_str = state.get("timestamp")

    if baseline_price and baseline_time_str:
        hours_elapsed = (now - datetime.fromisoformat(baseline_time_str)).total_seconds() / 3600
        if hours_elapsed >= 24:
            chg = pct_change(price, baseline_price)
            if chg >= change_alert:
                alerts.append(
                    f"⚡ {ticker} +{chg:.1f}% in 24 hours!\n"
                    f"  ${baseline_price:.4f} → ${price:.4f}"
                )
            state["price"]     = price
            state["timestamp"] = now.isoformat()
    else:
        state["price"]     = price
        state["timestamp"] = now.isoformat()

    # --- Daily summary ---
    after_summary_time = (
        now.hour > SUMMARY_HOUR_UTC or
        (now.hour == SUMMARY_HOUR_UTC and now.minute >= SUMMARY_MINUTE_UTC)
    )
    if after_summary_time and state.get("summary_sent_date") != today_str:
        chg   = pct_change(price, day_open_price)
        arrow = "📈" if chg >= 0 else "📉"
        sign  = "+" if chg >= 0 else ""
        send_pushover(
            f"{ticker} Daily Summary",
            f"{arrow} {ticker} Daily Summary — {today_str}\n"
            f"  Open:   ${day_open_price:.4f}\n"
            f"  Close:  ${price:.4f}\n"
            f"  Change: {sign}{chg:.2f}%",
            sound="magic"
        )
        state["summary_sent_date"] = today_str

    # --- Persist & send intraday alerts ---
    state["crossed_low"]  = crossed_low
    state["crossed_high"] = crossed_high
    state["last_checked"] = now.isoformat()
    state["last_price"]   = price
    save_state(ticker, state)

    if alerts:
        body = "\n\n".join(alerts)
        send_pushover(f"{ticker} Stock Alert", f"{body}\n\nChecked: {now.strftime('%H:%M UTC')}")

# ----------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------

def generate_and_upload_report():
    """Generate and upload the HTML ticker report. Failures are non-fatal."""
    import subprocess
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stock_report.py")
    try:
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=120
        )
        output = (result.stdout + result.stderr).strip()
        if output:
            print(output, flush=True)
        if result.returncode != 0:
            send_pushover(
                "Stock Report Error",
                f"⚠️ Report generation failed (exit {result.returncode})\n{output[-300:]}",
                sound="siren",
            )
    except Exception as e:
        send_pushover("Stock Report Error", f"⚠️ Report script error: {e}", sound="siren")


def main():
    now            = datetime.now(timezone.utc)
    all_configs    = load_all_ticker_configs()

    # Single ticker mode: python3 stock_monitor.py AAPL
    if len(sys.argv) > 1:
        ticker = sys.argv[1].upper()
        config = {**DEFAULT_CONFIG, **all_configs.get(ticker, {})}
        monitor_ticker(ticker, config, now)
    else:
        # All-tickers mode: read every ticker from tickers.json
        if not all_configs:
            print("No tickers found in tickers.json — nothing to monitor.")
            return
        for ticker, config in all_configs.items():
            monitor_ticker(ticker, {**DEFAULT_CONFIG, **config}, now)
        # Generate HTML report after all tickers are processed
        generate_and_upload_report()

if __name__ == "__main__":
    main()
