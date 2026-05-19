#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
setup.py — One-time setup script for the Reddit Portfolio Tracker.

What this does:
  1. Creates the required directory structure under ~/.hermes/reddit-portfolio/
  2. Installs Python dependencies (yfinance, jinja2)
  3. Initialises portfolio state files for each portfolio in config.json
  4. Copies cron wrapper scripts to ~/.hermes/scripts/
  5. Registers two Hermes cron jobs:
       - Scanner:      every 15 min, Mon–Fri (market hours guard in script)
       - Daily report: 02:05 UTC (9:05 PM CT), Mon–Fri

Usage:
    python3.11 setup.py

Re-running is safe — existing portfolio state files are never overwritten.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR    = Path.home() / ".hermes" / "reddit-portfolio"
SCRIPTS_DIR = BASE_DIR / "scripts"
HERMES_SCRIPTS = Path.home() / ".hermes" / "scripts"
CONFIG_PATH = BASE_DIR / "config.json"
ENV_PATH    = Path.home() / ".hermes" / ".env"

CRON_SCAN_SRC   = SCRIPTS_DIR / "cron_scan.py"
CRON_REPORT_SRC = SCRIPTS_DIR / "cron_daily_report.py"
CRON_SCAN_DST   = HERMES_SCRIPTS / "reddit_portfolio_scan.py"
CRON_REPORT_DST = HERMES_SCRIPTS / "reddit_portfolio_daily_report.py"

REQUIRED_PACKAGES = ["yfinance", "jinja2"]

CRON_SCAN_SCHEDULE   = "*/15 * * * 1-5"   # every 15 min Mon–Fri (script guards market hours)
CRON_REPORT_SCHEDULE = "5 2 * * 1-5"      # 02:05 UTC = 9:05 PM CT Mon–Fri


def step(msg: str):
    print(f"\n{'─'*60}\n▶  {msg}")


def ok(msg: str):
    print(f"   ✅  {msg}")


def warn(msg: str):
    print(f"   ⚠️   {msg}")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


# ── 1. Directories ───────────────────────────────────────────────────────────
step("Creating directory structure")

dirs = [
    BASE_DIR / "portfolios",
    BASE_DIR / "reports",
    BASE_DIR / "scripts",
    HERMES_SCRIPTS,
]

if CONFIG_PATH.exists():
    config = json.loads(CONFIG_PATH.read_text())
    for p in config.get("portfolios", []):
        dirs.append(BASE_DIR / "portfolios" / p["id"])
else:
    warn("config.json not found — skipping per-portfolio directories (run setup again after creating config.json)")
    config = {"portfolios": []}

for d in dirs:
    d.mkdir(parents=True, exist_ok=True)
    ok(f"mkdir {d.relative_to(Path.home())}")


# ── 2. Python dependencies ───────────────────────────────────────────────────
step("Installing Python dependencies")

r = run([sys.executable, "-m", "pip", "install", "--quiet", *REQUIRED_PACKAGES])
if r.returncode == 0:
    ok(f"Installed: {', '.join(REQUIRED_PACKAGES)}")
else:
    warn(f"pip install failed:\n{r.stderr[-400:]}")
    sys.exit(1)


# ── 3. Initialise portfolio state files ─────────────────────────────────────
step("Initialising portfolio state files")

for p in config.get("portfolios", []):
    pid      = p["id"]
    balance  = p.get("starting_balance", 2000.0)
    sub      = p.get("subreddit", pid)
    port_dir = BASE_DIR / "portfolios" / pid

    port_file = port_dir / "portfolio.json"
    txn_file  = port_dir / "transactions.json"

    if not port_file.exists():
        port_file.write_text(json.dumps({
            "id": pid,
            "subreddit": sub,
            "check_interval_minutes": p.get("check_interval_minutes", 15),
            "starting_balance": balance,
            "current_balance": balance,
            "last_read_utc": None,
            "holdings": {}
        }, indent=2))
        ok(f"Created portfolios/{pid}/portfolio.json  (balance: ${balance:,.2f})")
    else:
        ok(f"portfolios/{pid}/portfolio.json already exists — skipped")

    if not txn_file.exists():
        txn_file.write_text("[]")
        ok(f"Created portfolios/{pid}/transactions.json")
    else:
        ok(f"portfolios/{pid}/transactions.json already exists — skipped")


# ── 4. Copy cron wrapper scripts ─────────────────────────────────────────────
step("Copying cron wrapper scripts to ~/.hermes/scripts/")

for src, dst in [(CRON_SCAN_SRC, CRON_SCAN_DST), (CRON_REPORT_SRC, CRON_REPORT_DST)]:
    if not src.exists():
        warn(f"Source not found: {src} — skipping (scripts must be present in {SCRIPTS_DIR})")
        continue
    shutil.copy2(src, dst)
    ok(f"Copied {src.name} → {dst}")


# ── 5. Register Hermes cron jobs ─────────────────────────────────────────────
step("Registering Hermes cron jobs")

hermes = shutil.which("hermes")
if not hermes:
    warn("hermes CLI not found in PATH — skipping cron job registration.")
    warn("Register manually with:")
    warn(f"  hermes cron add --schedule '{CRON_SCAN_SCHEDULE}' --script {CRON_SCAN_DST} --no-agent")
    warn(f"  hermes cron add --schedule '{CRON_REPORT_SCHEDULE}' --script {CRON_REPORT_DST} --no-agent")
else:
    jobs = [
        {
            "name": "Reddit Portfolio Scanner",
            "schedule": CRON_SCAN_SCHEDULE,
            "script": CRON_SCAN_DST.name,      # filename only, relative to ~/.hermes/scripts/
            "desc": "Every 15 min Mon–Fri (market hours guard inside script)",
        },
        {
            "name": "Reddit Portfolio Daily Report",
            "schedule": CRON_REPORT_SCHEDULE,
            "script": CRON_REPORT_DST.name,    # filename only, relative to ~/.hermes/scripts/
            "desc": "Daily at 02:05 UTC (9:05 PM CT) Mon–Fri",
        },
    ]

    for job in jobs:
        r = run([
            hermes, "cron", "add",
            "--name", job["name"],
            "--script", job["script"],
            "--no-agent",
            job["schedule"],
        ])
        if r.returncode == 0:
            ok(f"Registered: \"{job['name']}\"  [{job['desc']}]")
        else:
            # Likely already exists — print warning but don't fail
            warn(f"Could not register \"{job['name']}\": {r.stderr.strip() or r.stdout.strip()}")
            warn("It may already exist — check with: hermes cron list")


# ── 6. Env var check ─────────────────────────────────────────────────────────
step("Checking environment variables")

def env_set(key: str) -> bool:
    import os
    if os.environ.get(key):
        return True
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if line.startswith(f"{key}=") and line.split("=", 1)[1].strip():
                return True
    return False

pushover_ok = env_set("PUSHOVER_USER_KEY") and env_set("PUSHOVER_API_TOKEN")
minio_ok    = env_set("MINIO_ACCESS_KEY") and env_set("MINIO_SECRET_KEY")

if pushover_ok:
    ok("Pushover credentials found (PUSHOVER_USER_KEY + PUSHOVER_API_TOKEN)")
else:
    warn("Pushover credentials missing — add PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN to ~/.hermes/.env")

if minio_ok:
    ok("MinIO credentials found (MINIO_ACCESS_KEY + MINIO_SECRET_KEY)")
else:
    warn("MinIO credentials missing — add MINIO_ACCESS_KEY and MINIO_SECRET_KEY to ~/.hermes/.env")


# ── Done ─────────────────────────────────────────────────────────────────────
print(f"""
{'═'*60}
✅  Setup complete!

Next steps:
  • Edit config.json to add/remove portfolios
  • Verify cron jobs:  hermes cron list
  • Manual test scan:  python3.11 {SCRIPTS_DIR}/run_cycle.py <portfolio_id> --force
  • Manual report:     python3.11 {SCRIPTS_DIR}/daily_report.py <portfolio_id>
{'═'*60}
""")
