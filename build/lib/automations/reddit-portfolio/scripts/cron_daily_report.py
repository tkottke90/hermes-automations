#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
cron_daily_report.py — Daily report cron wrapper.

Runs at 02:05 UTC (9:05PM CT) Mon–Fri.
Iterates all enabled portfolios from config.json.
"""

import json
import sys
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
CONFIG_PATH = Path.home() / ".hermes" / "reddit-portfolio" / "config.json"

config = json.loads(CONFIG_PATH.read_text())
portfolios = [p["id"] for p in config.get("portfolios", []) if p.get("enabled", True)]

for portfolio_id in portfolios:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "daily_report.py"), portfolio_id, "--notify"],
        capture_output=True, text=True, timeout=120,
        cwd=str(SCRIPTS_DIR)
    )
    output = result.stdout.strip()
    if output:
        print(output)
    if result.returncode != 0:
        err = result.stderr[-300:] if result.stderr else "(no stderr)"
        print(f"[daily_report ERROR:{portfolio_id}] {err}")
