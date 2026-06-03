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
from classifier import classify_email, explain_no_match, recommend_labels
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
    seen_md5_dates: Optional[Dict[str, str]] = None,
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
    date = email.get("date", "")

    # Step 1: Compute MD5
    md5 = compute_md5(email)

    # Step 2: Deduplication check with date tracking
    if log.has_entry(md5, dry_run=dry_run):
        # Check if date differs from first occurrence
        logged_entry = log.get_entry(md5, dry_run=dry_run)
        if logged_entry:
            logged_date = logged_entry.get("date", "")
            if date and logged_date and date != logged_date:
                # Different date → trash the older duplicate
                if not dry_run:
                    try:
                        gmail.trash_message(email_id)
                        print(f"  [DUPLICATE] Same content, different date — email TRASHED")
                    except Exception as e:
                        print(f"  [ERROR] Failed to trash email: {e}", file=sys.stderr)
                        return {
                            "status": "error",
                            "applied_labels": [],
                            "message": f"Trash failed: {e}",
                        }
                else:
                    print(f"  [DRY-RUN] Would TRASH email (different date than first)")
                return {
                    "status": "duplicate",
                    "applied_labels": [],
                    "message": "Already processed (duplicate MD5, different date)",
                }
            else:
                # Same date or no date in either → just mark as read
                if not dry_run:
                    try:
                        gmail.mark_as_read(email_id)
                        print(f"  [DUPLICATE] Same content, same date — marked as read")
                    except Exception as e:
                        print(f"  [ERROR] Failed to mark as read: {e}", file=sys.stderr)
                        return {
                            "status": "error",
                            "applied_labels": [],
                            "message": f"Mark as read failed: {e}",
                        }
                else:
                    print(f"  [DRY-RUN] Would mark as read (duplicate MD5)")
                return {
                    "status": "duplicate",
                    "applied_labels": [],
                    "message": "Already processed (duplicate MD5)",
                }

    # Track first-seen date for future duplicate checks
    if seen_md5_dates is not None:
        seen_md5_dates[md5] = date

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
        no_match_reasons = explain_no_match(text, sender, label_rules)
        recommendations = recommend_labels(
            text=text,
            sender=sender,
            subject=subject,
            existing_label_names=list(label_rules.keys()),
            verbose=verbose,
        )
        if verbose:
            print(f"  [NO_MATCH] Reasons: {no_match_reasons}")
            print(f"  [NO_MATCH] Recommendations: {recommendations}")
        _write_log_entry(log, email_id, subject, sender, md5, [], {}, False, dry_run,
                         date=email.get("date", ""),
                         no_match_reasons=no_match_reasons, recommendations=recommendations, marked_read=True)
        if not dry_run:
            try:
                gmail.mark_as_read(email_id)
                print(f"  → Marked as read")
            except Exception as e:
                return {"status": "error", "applied_labels": [], "message": f"Mark as read failed: {e}"}
        return {"status": "no_match", "applied_labels": [], "message": "No labels matched"}

    # Step 5: Resolve label IDs
    resolved = gmail.resolve_label_ids(matched_labels)
    # matched_labels is now Dict[name, justification]; split for downstream use
    justifications: Dict[str, str] = {name: matched_labels[name] for name in matched_labels}
    valid_label_ids = [lid for lid in resolved.values() if lid is not None]
    valid_label_names = [name for name, lid in resolved.items() if lid is not None]
    missing_labels = [name for name, lid in resolved.items() if lid is None]

    # Determine if any matched rule requests trashing
    should_trash = any(
        label_rules.get(name, {}).get("trash", False)
        for name in valid_label_names
    )

    # If ALL matched labels are missing → leave unread, log nothing
    if not valid_label_ids:
        print(
            f"  [SKIP] All matched labels missing in Gmail for '{subject}' — "
            f"email marked as read for next run.",
            file=sys.stderr,
        )
        if not dry_run:
            try:
                gmail.mark_as_read(email_id)
                print(f"  → Marked as read")
            except Exception as e:
                return {
                    "status": "error",
                    "applied_labels": [],
                    "message": f"Mark as read failed: {e}",
                }
        return {
            "status": "skipped_missing_labels",
            "applied_labels": [],
            "message": f"All labels missing: {missing_labels}",
        }

    # Step 6: Apply labels and mark as read (unless dry-run)
    if not dry_run:
        try:
            gmail.apply_labels(email_id, valid_label_ids)
            if should_trash:
                gmail.trash_message(email_id)  # also removes INBOX/UNREAD implicitly
            else:
                gmail.mark_as_read(email_id)
        except Exception as e:
            return {"status": "error", "applied_labels": [], "message": f"Gmail API error: {e}"}

    # Step 7: Log
    # Step 7: Log
    _write_log_entry(log, email_id, subject, sender, md5, valid_label_names, justifications, should_trash, dry_run, date=email.get("date", ""), marked_read=True)
    status_msg = (
        f"{'[DRY-RUN] Would apply' if dry_run else 'Applied'} labels: {valid_label_names}"
        + (" + TRASH" if should_trash else "")
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
    trashed: bool,
    dry_run: bool,
    date: str = "",
    no_match_reasons: Optional[Dict[str, str]] = None,
    recommendations: Optional[List[Dict[str, str]]] = None,
    marked_read: bool = False,
) -> None:
    entry: Dict[str, Any] = {
        "email_id": email_id,
        "email_title": subject,
        "sender": sender,
        "applied_labels": applied_labels,
        "justification": justifications,
        "trashed": trashed,
        "marked_read": marked_read,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "md5": md5,
        "date": date,
        "dry_run": dry_run,
    }
    if no_match_reasons is not None:
        entry["no_match_reasons"] = no_match_reasons
    if recommendations is not None:
        entry["label_recommendations"] = recommendations
    log.write_entry(entry, dry_run=dry_run)


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
    gmail = None
    try:
        gmail = GmailClient()
    except Exception as e:
        print(f"ERROR: Failed to initialize Gmail client: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    log = None
    try:
        log = LogStore(LOG_PATH, retention_days=retention_days)
    except Exception as e:
        print(f"ERROR: Failed to initialize log store: {e}", file=sys.stderr)
        sys.exit(1)

    # Fetch unread emails
    print(f"Fetching up to {processing_limit} unread emails...")
    try:
        emails = gmail.fetch_unread(limit=processing_limit)
    except Exception as e:
        print(f"ERROR: Failed to fetch emails: {e}", file=sys.stderr)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
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
    seen_md5_dates: Dict[str, str] = {}

    for i, email in enumerate(emails, 1):
        subject = email.get("subject", "(no subject)")
        sender = email.get("sender", "")
        print(f"[{i}/{len(emails)}] {subject!r} — {sender}")

        try:
            result = process_email(
                email=email,
                gmail=gmail,
                log=log,
                label_rules=label_rules,
                dry_run=dry_run,
                verbose=args.verbose,
                seen_md5_dates=seen_md5_dates,
            )

            status = result["status"]
            counts[status] = counts.get(status, 0) + 1
            print(f"  → {result['message']}")
            print()
        except Exception as e:
            counts["error"] += 1
            print(f"  [ERROR] Failed to process email: {e}", file=sys.stderr)
            if args.verbose:
                import traceback
                traceback.print_exc()
            print()

    # Prune expired log entries
    try:
        pruned = log.prune_expired()
        if pruned:
            print(f"Pruned {pruned} expired log entries (>{retention_days} days old)\n")
    except Exception as e:
        print(f"  [WARN] Failed to prune log: {e}", file=sys.stderr)

    # Summary
    try:
        total_entries = log.entry_count() if log else 0
    except Exception:
        total_entries = 0

    print("─" * 50)
    print(f"{run_prefix}Run complete")
    print(f"  Labeled:               {counts['labeled']}")
    print(f"  No match:              {counts['no_match']}")
    print(f"  Duplicates skipped:    {counts['duplicate']}")
    print(f"  Skipped (bad labels):  {counts['skipped_missing_labels']}")
    print(f"  Errors:                {counts['error']}")
    print(f"  Log entries total:     {total_entries}")

    if counts["error"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
