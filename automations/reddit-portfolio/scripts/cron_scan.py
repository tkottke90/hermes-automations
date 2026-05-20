#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
cron_scan.py — Lightweight cron wrapper for run_cycle.py.

Runs every 15 minutes Mon–Fri during market hours (13:30–21:00 UTC / 8:30AM–4PM CT).
Iterates all enabled portfolios from config.json.
Prints nothing if rate-limited or market closed. Stdout is delivered to Hermes chat.
"""

import json
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
CONFIG_PATH = Path.home() / ".hermes" / "reddit-portfolio" / "config.json"

def is_market_hours() -> bool:
    """Rough check: Mon–Fri, 13:30–21:00 UTC (8:30AM–4PM CT with buffer)."""
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:  # Sat=5, Sun=6
        return False
    hour_min = now.hour * 60 + now.minute
    return 13 * 60 + 30 <= hour_min <= 21 * 60

if not is_market_hours():
    sys.exit(0)

config = json.loads(CONFIG_PATH.read_text())
portfolios = [p["id"] for p in config.get("portfolios", []) if p.get("enabled", True)]

for portfolio_id in portfolios:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "run_cycle.py"), portfolio_id, "--upload-latest"],
        capture_output=True, text=True, timeout=300,
        cwd=str(SCRIPTS_DIR)
    )
    output = result.stdout.strip()
    stderr = result.stderr.strip()
    if output:
        print(f"[{portfolio_id}]\n{output}")
    if stderr and result.returncode != 0:
        print(f"[ERROR:{portfolio_id}] {stderr[-300:]}")
    elif stderr and not output:
        # Surface info/rate-limit messages when stdout is silent
        print(f"[INFO] [{portfolio_id}] {stderr[-300:]}")
