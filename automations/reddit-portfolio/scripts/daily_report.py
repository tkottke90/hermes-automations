#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
daily_report.py — Generates the daily HTML report + sends Pushover notification.

Intended to run at ~9PM CT (02:00 UTC) Mon–Fri via cron.

Usage:
    python3.11 daily_report.py [portfolio_id]
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CT = timezone(timedelta(hours=-5))  # CT (UTC-5); CDT offset is -6 but close enough for a TTL


def ttl_until_10am_ct() -> int:
    """Return seconds until 10:00 AM CT the next calendar day."""
    now_ct = datetime.now(CT)
    next_10am = (now_ct + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    return max(60, int((next_10am - now_ct).total_seconds()))

BASE_DIR = Path.home() / ".hermes" / "reddit-portfolio"
SCRIPTS_DIR = Path(__file__).parent

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(Path.home() / ".hermes" / "lib"))
from pushover import send_notification


def build_daily_message(portfolio_id: str) -> tuple[str, str]:
    """Returns (title, message) for the Pushover notification."""
    portfolio_path = BASE_DIR / "portfolios" / portfolio_id / "portfolio.json"
    transactions_path = BASE_DIR / "portfolios" / portfolio_id / "transactions.json"

    portfolio = json.loads(portfolio_path.read_text())
    transactions = json.loads(transactions_path.read_text())

    subreddit = portfolio.get("subreddit", portfolio_id)
    starting = portfolio.get("starting_balance", 2000.0)
    cash = portfolio.get("current_balance", starting)
    holdings = portfolio.get("holdings", {})

    # Fetch current prices
    holdings_value = 0.0
    if holdings:
        from price_fetcher import get_prices
        prices = get_prices(list(holdings.keys()))
        for ticker, h in holdings.items():
            price = prices.get(ticker, {}).get("price") or h.get("avg_cost", 0)
            holdings_value += h.get("shares", 0) * price

    total_value = cash + holdings_value
    total_pnl = total_value - starting
    pnl_emoji = "📈" if total_pnl >= 0 else "📉"

    # Today's trades
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_trades = [t for t in transactions if t.get("timestamp", "").startswith(today)]
    buys = [t for t in today_trades if t.get("type") == "buy"]
    sells = [t for t in today_trades if t.get("type") == "sell"]
    realized_pnl = sum(t.get("profit_loss", 0) or 0 for t in sells)

    # Win rate
    closed = [t for t in transactions if t.get("type") == "sell" and t.get("profit_loss") is not None]
    wins = sum(1 for t in closed if t.get("profit_loss", 0) >= 0)
    win_rate = round(wins / len(closed) * 100) if closed else 0

    title = f"r/{subreddit} Daily Report — {pnl_emoji} ${total_pnl:+.2f}"
    message = (
        f"💰 Portfolio: ${total_value:.2f} (started ${starting:.2f})\n"
        f"{pnl_emoji} Total P/L: ${total_pnl:+.2f} ({(total_pnl/starting*100):+.1f}%)\n"
        f"💵 Cash: ${cash:.2f} | Positions: {len(holdings)}\n"
        f"\n📅 Today: {len(buys)} buys, {len(sells)} sells"
    )
    if sells:
        message += f" | Realized P/L: ${realized_pnl:+.2f}"
    if closed:
        message += f"\n🎯 Win rate: {win_rate}% ({wins}/{len(closed)})"

    return title, message


def run(portfolio_id: str = "pennystock", notify: bool = False):
    print(f"[daily_report] Generating report for '{portfolio_id}'...", flush=True)

    import report_generator

    # Load last decisions if available
    decisions_path = BASE_DIR / "portfolios" / portfolio_id / "last_decisions.json"
    decisions = None
    if decisions_path.exists():
        try:
            decisions = json.loads(decisions_path.read_text())
        except Exception:
            pass

    report_path = report_generator.generate_report(portfolio_id, latest_decisions=decisions)
    print(f"[daily_report] Report written: {report_path}", flush=True)

    # Upload to MinIO S3
    report_url = None
    try:
        from upload_report import upload_report, upload_as_latest
    except ImportError as e:
        print(f"[daily_report] ⚠️  Could not import upload helpers: {e}", flush=True)
        upload_report = None  # type: ignore[assignment]
        upload_as_latest = None  # type: ignore[assignment]

    if upload_report is not None:
        try:
            ok, report_url = upload_report(report_path)
            if ok:
                print(f"[daily_report] ✅ Report uploaded: {report_url}", flush=True)
            else:
                print(f"[daily_report] ⚠️  Upload returned non-success.", flush=True)
                report_url = None
        except Exception as e:
            print(f"[daily_report] ⚠️  Upload failed: {e}", flush=True)

    # Upload stable latest file
    if upload_as_latest is not None:
        try:
            ok_latest, latest_url = upload_as_latest(report_path, portfolio_id)
            if ok_latest:
                print(f"[daily_report] ✅ Latest report uploaded: {latest_url}", flush=True)
            else:
                print(f"[daily_report] ⚠️  Latest upload returned non-success.", flush=True)
        except Exception as e:
            print(f"[daily_report] ⚠️  Latest upload failed: {e}", flush=True)

    # Build and send Pushover notification (only when --notify is passed)
    if notify:
        try:
            title, message = build_daily_message(portfolio_id)
            ok = send_notification(title, message, url=report_url, sound="cashregister", ttl=ttl_until_10am_ct())
            if ok:
                print(f"[daily_report] ✅ Pushover notification sent.", flush=True)
            else:
                print(f"[daily_report] ⚠️  Pushover returned non-success.", flush=True)
        except Exception as e:
            print(f"[daily_report] ⚠️  Pushover failed: {e}", flush=True)
    else:
        print(f"[daily_report] ℹ️  Pushover skipped (--notify not set).", flush=True)

    return report_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate and upload daily portfolio report.")
    parser.add_argument("portfolio_id", nargs="?", default="pennystock")
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send Pushover notification (omit for silent/frequent runs)",
    )
    args = parser.parse_args()
    path = run(args.portfolio_id, notify=args.notify)
    print(str(path))
