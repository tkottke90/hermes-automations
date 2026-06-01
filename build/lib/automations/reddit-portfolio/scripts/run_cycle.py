#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
run_cycle.py — Main orchestrator for a single portfolio scan cycle.

Runs the full pipeline:
  1. reddit_scanner  → fetch posts, extract tickers, build context payload
  2. llm_trader      → send to LLM, get buy/sell/hold decisions
  3. trade_engine    → apply decisions to portfolio
  4. (optional) report_generator → generate HTML report

Usage:
    python3.11 run_cycle.py [portfolio_id] [--force] [--report]
    python3.11 run_cycle.py pennystock --force --report
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path.home() / ".hermes" / "reddit-portfolio"
SCRIPTS_DIR = Path(__file__).parent

sys.path.insert(0, str(SCRIPTS_DIR))


def run_cycle(portfolio_id: str = "pennystock", force: bool = False,
              generate_report: bool = False, upload_latest: bool = False):
    print(f"\n{'='*60}", flush=True)
    print(f"[run_cycle] Starting cycle for '{portfolio_id}' at {datetime.now(timezone.utc).isoformat()}", flush=True)
    print(f"{'='*60}\n", flush=True)

    if upload_latest:
        generate_report = True


    # ── Step 1: Scan Reddit ──────────────────────────────────────
    import reddit_scanner
    payload = reddit_scanner.run(portfolio_id, force=force)

    if not payload:
        # Detailed reason is printed to stderr by reddit_scanner — suppress stdout so cron stays silent
        return None

    print(f"[run_cycle] Scanned {len(payload.get('posts', []))} posts, "
          f"{len(payload.get('all_tickers', []))} tickers found.", flush=True)

    # ── Step 2: LLM Trading Decisions ────────────────────────────
    import llm_trader
    try:
        decisions = llm_trader.run(portfolio_id, payload)
    except Exception as e:
        print(f"[run_cycle] ⚠️  LLM call failed: {e}", flush=True)
        print("[run_cycle] Saving scan context for manual review...", flush=True)
        debug_path = BASE_DIR / "portfolios" / portfolio_id / "last_scan_payload.json"
        debug_path.write_text(json.dumps(payload, indent=2, default=str))
        print(f"[run_cycle] Payload saved to {debug_path}", flush=True)
        return None

    # Save raw decisions for debugging / report use
    decisions_path = BASE_DIR / "portfolios" / portfolio_id / "last_decisions.json"
    decisions_path.write_text(json.dumps(decisions, indent=2, default=str))

    print(f"\n[run_cycle] LLM decisions ({len(decisions.get('decisions', []))} actions):", flush=True)
    for d in decisions.get("decisions", []):
        action = d.get("action", "?").upper()
        ticker = d.get("ticker", "?")
        amount = f" ${d['amount_usd']:.2f}" if d.get("amount_usd") else ""
        exe = "" if d.get("execute", True) else " [QUEUED]"
        print(f"  {action} {ticker}{amount}{exe} — {d.get('reasoning', '')[:80]}", flush=True)

    # ── Step 3: Execute Trades ───────────────────────────────────
    import trade_engine
    prices = payload.get("prices", {})
    messages = trade_engine.run(portfolio_id, decisions, prices)

    print(f"\n[run_cycle] Trade execution results:", flush=True)
    for m in messages:
        print(f"  {m}", flush=True)

    # ── Step 4: Optional Report Generation ───────────────────────
    report_path = None
    if generate_report:
        import report_generator
        report_path = report_generator.generate_report(portfolio_id, latest_decisions=decisions)
        print(f"\n[run_cycle] 📄 Report: {report_path}", flush=True)

    # ── Step 5: Upload Latest (optional) ─────────────────────────
    # Run in a background thread so it doesn't add to wall-clock time.
    # MinIO is on LAN so upload completes well within the join timeout.
    if upload_latest and report_path:
        import threading

        def _upload():
            try:
                from upload_report import upload_as_latest
                ok, latest_url = upload_as_latest(Path(report_path), portfolio_id)
                if ok:
                    print(f"[run_cycle] ✅ Latest report uploaded: {latest_url}", flush=True)
                else:
                    print(f"[run_cycle] ⚠️  Latest upload returned non-success.", flush=True)
            except Exception as e:
                print(f"[run_cycle] ⚠️  Latest upload failed: {e}", flush=True)

        upload_thread = threading.Thread(target=_upload, daemon=True)
        upload_thread.start()
        upload_thread.join(timeout=15)  # cap at 15s; LAN upload should be <1s
        if upload_thread.is_alive():
            print(f"[run_cycle] ⚠️  Latest upload timed out after 15s — skipping.", flush=True)


    print(f"\n[run_cycle] Cycle complete.", flush=True)
    return {
        "decisions": decisions,
        "trade_messages": messages,
        "report_path": str(report_path) if report_path else None,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run one portfolio scan cycle.")
    parser.add_argument("portfolio_id", nargs="?", default="pennystock")
    parser.add_argument("--force", action="store_true",
                        help="Skip rate-limit check and force a scan")
    parser.add_argument("--report", action="store_true",
                        help="Generate HTML report after trades")
    parser.add_argument("--upload-latest", action="store_true",
                        help="Generate report and upload as latest (implies --report)")
    args = parser.parse_args()

    result = run_cycle(
        args.portfolio_id,
        force=args.force,
        generate_report=args.report,
        upload_latest=args.upload_latest,
    )
    if result and result.get("report_path"):
        print(f"\n📄 Report saved: {result['report_path']}")
