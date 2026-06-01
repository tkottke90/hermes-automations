#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
reddit_portfolio_scan.py — Cron wrapper for run_cycle.py.

Runs every 15 minutes Mon–Fri during market hours.
Runs all enabled portfolios IN PARALLEL to stay within the 120s cron timeout.
Prints nothing if rate-limited or market closed.
"""

import json
import sys
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path.home() / ".hermes" / "reddit-portfolio" / "scripts"
CONFIG_PATH = Path.home() / ".hermes" / "reddit-portfolio" / "config.json"


def is_market_hours() -> bool:
    """Rough check: Mon–Fri, 13:30–21:00 UTC (8:30AM–4PM CT with buffer)."""
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return False
    hour_min = now.hour * 60 + now.minute
    return 13 * 60 + 30 <= hour_min <= 21 * 60


if not is_market_hours():
    now = datetime.now(timezone.utc)
    print(f"[scanner] Market closed — skipping scan (UTC {now.strftime('%H:%M')} is outside 13:30–21:00 Mon–Fri)")
    sys.exit(0)

config = json.loads(CONFIG_PATH.read_text())
portfolios = [p["id"] for p in config.get("portfolios", []) if p.get("enabled", True)]

results = {}
lock = threading.Lock()


def run_portfolio(portfolio_id: str):
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "run_cycle.py"), portfolio_id],
        capture_output=True, text=True, timeout=110,  # 110s per portfolio, fits within 120s total
        cwd=str(SCRIPTS_DIR)
    )
    with lock:
        results[portfolio_id] = result


threads = [threading.Thread(target=run_portfolio, args=(pid,)) for pid in portfolios]
for t in threads:
    t.start()
for t in threads:
    t.join(timeout=115)  # wait up to 115s for all threads

for portfolio_id in portfolios:
    result = results.get(portfolio_id)
    if result is None:
        print(f"[{portfolio_id}]\n[ERROR] Portfolio timed out — no result returned")
        continue

    output = result.stdout.strip()
    stderr = result.stderr.strip() if result.stderr else ""

    if output or stderr or result.returncode != 0:
        print(f"[{portfolio_id}]")
        if output:
            print(output)
        if stderr:
            label = "[ERROR]" if result.returncode != 0 else "[INFO]"
            print(f"{label} {stderr}")
        if result.returncode != 0 and not stderr:
            print(f"[ERROR] Process exited with code {result.returncode} (no stderr output)")
    else:
        print(f"[{portfolio_id}] ℹ️  No output from scan cycle (no trades, no rate-limit info)")
