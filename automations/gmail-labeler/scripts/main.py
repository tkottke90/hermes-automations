#!/Users/thomaskottke/.hermes-automations/.venv/bin/python3
"""
main.py — Gmail Labeler automation entry point.

Orchestrates the full pipeline:
  1. Load config and validate environment
  2. Fetch unread emails from Gmail
  3. For each email: deduplicate → OCR → classify → label → log
  4. Prune expired log entries

Usage:
  python3 main.py [--dry-run] [--limit N] [--verbose]
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Resolve paths relative to this script's location
SCRIPT_DIR = Path(__file__).parent
AUTOMATION_DIR = SCRIPT_DIR.parent
DATA_DIR = AUTOMATION_DIR / "data"
CONFIG_PATH = DATA_DIR / "config.json"
LOG_PATH = DATA_DIR / "processed_log.json"

# Add scripts dir to path for sibling imports
sys.path.insert(0, str(SCRIPT_DIR))

from gmail_client import GmailClient
from ocr_pipeline import email_to_text, _check_system_deps
from classifier import classify_email
from log_store import LogStore


# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        example = DATA_DIR / "config.example.json"
        print(
            f"ERROR: config.json not found at {CONFIG_PATH}\n"
            f"Copy the example and configure your label rules:\n"
            f"  cp {example} {CONFIG_PATH}",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return json.load(f)


# ── Email content → MD5 ───────────────────────────────────────────────────────

def compute_md5(email: Dict[str, Any]) -> str:
    """Compute MD5 of subject + sender + body (plain preferred, html fallback)."""
    body = email.get("body_plain") or email.get("body_html") or ""
    raw = "\n".join([
        email.get("subject", ""),
        email.get("sender", ""),
        body,
    ])
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ── Pipeline ──────────────────────────────────────────────────────────────────

def process_email(
    email: Dict[str, Any],
    gmail: GmailClient,
    log: LogStore,
    label_rules: Dict[str, Any],
    dry_run: bool,
    verbose: bool,
) -> Dict[str, Any]:
    """
    Process a single email through the full pipeline.

    Returns a result dict with keys:
      status: 'labeled' | 'no_match' | 'duplicate' | 'skipped_missing_labels' | 'error'
      applied_labels: list of label names applied
      message: human-readable summary
    """
    email_id = email["id"]
    subject = email.get("subject", "(no subject)")
    sender = email.get("sender", "")

    # Step 1: Compute MD5
    md5 = compute_md5(email)

    # Step 2: Deduplication check
    if log.has_entry(md5, dry_run=dry_run):
        return {"status": "duplicate", "applied_labels": [], "message": "Already processed (duplicate MD5)"}

    # Step 3: OCR / text extraction
    try:
        text = email_to_text(
            body_html=email.get("body_html", ""),
            body_plain=email.get("body_plain", ""),
            verbose=verbose,
        )
    except Exception as e:
        return {"status": "error", "applied_labels": [], "message": f"OCR failed: {e}"}

    if verbose:
        print(f"  [TEXT] Extracted {len(text)} chars")

    # Step 4: Classify
    try:
        matched_labels = classify_email(
            text=text,
            sender=sender,
            label_rules=label_rules,
            verbose=verbose,
        )
    except Exception as e:
        return {"status": "error", "applied_labels": [], "message": f"Classification failed: {e}"}

    if not matched_labels:
        _write_log_entry(log, email_id, subject, sender, md5, [], {}, dry_run)
        return {"status": "no_match", "applied_labels": [], "message": "No labels matched"}

    # Step 5: Resolve label IDs
    resolved = gmail.resolve_label_ids(matched_labels)
    # matched_labels is now Dict[name, justification]; split for downstream use
    justifications: Dict[str, str] = {name: matched_labels[name] for name in matched_labels}
    valid_label_ids = [lid for lid in resolved.values() if lid is not None]
    valid_label_names = [name for name, lid in resolved.items() if lid is not None]
    missing_labels = [name for name, lid in resolved.items() if lid is None]

    # If ALL matched labels are missing → leave unread, log nothing
    if not valid_label_ids:
        print(
            f"  [SKIP] All matched labels missing in Gmail for '{subject}' — "
            "email left unread for next run.",
            file=sys.stderr,
        )
        return {
            "status": "skipped_missing_labels",
            "applied_labels": [],
            "message": f"All labels missing: {missing_labels}",
        }

    # Step 6: Apply labels and mark as read (unless dry-run)
    if not dry_run:
        try:
            gmail.apply_labels(email_id, valid_label_ids)
            gmail.mark_as_read(email_id)
        except Exception as e:
            return {"status": "error", "applied_labels": [], "message": f"Gmail API error: {e}"}

    # Step 7: Log
    _write_log_entry(log, email_id, subject, sender, md5, valid_label_names, justifications, dry_run)

    status_msg = (
        f"{'[DRY-RUN] Would apply' if dry_run else 'Applied'} labels: {valid_label_names}"
    )
    if missing_labels:
        status_msg += f" (skipped missing: {missing_labels})"

    return {
        "status": "labeled",
        "applied_labels": valid_label_names,
        "message": status_msg,
    }


def _write_log_entry(
    log: LogStore,
    email_id: str,
    subject: str,
    sender: str,
    md5: str,
    applied_labels: List[str],
    justifications: Dict[str, str],
    dry_run: bool,
) -> None:
    log.write_entry(
        {
            "email_id": email_id,
            "email_title": subject,
            "sender": sender,
            "applied_labels": applied_labels,
            "justification": justifications,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "md5": md5,
            "dry_run": dry_run,
        },
        dry_run=dry_run,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gmail Labeler — classify and label unread emails"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze and log without applying labels or marking emails as read",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max emails to process (overrides config processing_limit)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-email debug output",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dry_run = args.dry_run

    run_prefix = "[DRY-RUN] " if dry_run else ""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{run_prefix}Gmail Labeler — {now_str}")
    print()

    # Check system deps before doing any API calls
    _check_system_deps()

    # Load config
    config = load_config()
    label_rules: Dict[str, Any] = config.get("label_rules", {})
    processing_limit: int = args.limit or config.get("processing_limit", 50)
    retention_days: int = config.get("retention_period_days", 30)

    if not label_rules:
        print("ERROR: No label_rules defined in config.json", file=sys.stderr)
        sys.exit(1)

    print(f"Config: {len(label_rules)} label rules, limit={processing_limit}, retention={retention_days}d")
    if dry_run:
        print("Mode: DRY-RUN (no labels applied, emails left unread)")
    print()

    # Initialize components
    gmail = GmailClient()
    log = LogStore(LOG_PATH, retention_days=retention_days)

    # Fetch unread emails
    print(f"Fetching up to {processing_limit} unread emails...")
    emails = gmail.fetch_unread(limit=processing_limit)
    print(f"Found {len(emails)} unread emails\n")

    if not emails:
        print("Nothing to process.")
        return

    # Process each email
    counts = {
        "labeled": 0,
        "no_match": 0,
        "duplicate": 0,
        "skipped_missing_labels": 0,
        "error": 0,
    }

    for i, email in enumerate(emails, 1):
        subject = email.get("subject", "(no subject)")
        sender = email.get("sender", "")
        print(f"[{i}/{len(emails)}] {subject!r} — {sender}")

        result = process_email(
            email=email,
            gmail=gmail,
            log=log,
            label_rules=label_rules,
            dry_run=dry_run,
            verbose=args.verbose,
        )

        status = result["status"]
        counts[status] = counts.get(status, 0) + 1
        print(f"  → {result['message']}")
        print()

    # Prune expired log entries
    pruned = log.prune_expired()
    if pruned:
        print(f"Pruned {pruned} expired log entries (>{retention_days} days old)\n")

    # Summary
    print("─" * 50)
    print(f"{run_prefix}Run complete")
    print(f"  Labeled:               {counts['labeled']}")
    print(f"  No match:              {counts['no_match']}")
    print(f"  Duplicates skipped:    {counts['duplicate']}")
    print(f"  Skipped (bad labels):  {counts['skipped_missing_labels']}")
    print(f"  Errors:                {counts['error']}")
    print(f"  Log entries total:     {log.entry_count()}")

    if counts["error"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
