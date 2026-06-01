#!/usr/bin/env python3
"""
log-cleaner: Purge expired Hermes cron job log (.md) files.

Usage:
    python3 clean_logs.py                  # normal run
    python3 clean_logs.py --dry-run        # preview without deleting
    python3 clean_logs.py --verbose        # extra per-file detail
    python3 clean_logs.py --config <path>  # override config file location
"""

import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "data" / "config.json"


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        print(
            f"ERROR: Config file not found: {config_path}\n"
            "Create a config.json in the data/ directory. "
            "See config.example.json for the expected format.",
            file=sys.stderr,
        )
        sys.exit(1)
    with config_path.open() as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError as exc:
            print(f"ERROR: Invalid JSON in config file: {exc}", file=sys.stderr)
            sys.exit(1)


def save_config(config: dict, config_path: Path) -> None:
    """Write config atomically via temp file + rename."""
    tmp_path = config_path.with_suffix(".json.tmp")
    try:
        with tmp_path.open("w") as fh:
            json.dump(config, fh, indent=2)
            fh.write("\n")
        tmp_path.replace(config_path)
    except Exception as exc:
        # Clean up on failure — don't leave a dangling .tmp file
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to save config: {exc}") from exc


# ---------------------------------------------------------------------------
# Cleanup logic
# ---------------------------------------------------------------------------

def clean_job(
    job: dict,
    base_log_dir: Path,
    default_exp: int,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """
    Clean expired log files for a single job.

    Returns a dict with stats: {total, deleted, skipped, errors}.
    """
    cron_job_id: str = job["cron_job_id"]
    exp_days: int = job.get("exp", default_exp)

    # Resolve the log directory for this job
    log_dir_name: str = job.get("log_dir") or cron_job_id
    job_log_dir: Path = base_log_dir / log_dir_name

    stats = {"total": 0, "deleted": 0, "skipped": 0, "errors": 0}

    if not job_log_dir.exists():
        logging.warning(
            "[%s] Log directory does not exist, skipping: %s",
            cron_job_id,
            job_log_dir,
        )
        return stats

    cutoff: datetime = datetime.now(tz=timezone.utc) - timedelta(days=exp_days)
    md_files = sorted(job_log_dir.glob("*.md"))
    stats["total"] = len(md_files)

    for md_file in md_files:
        try:
            mtime = datetime.fromtimestamp(md_file.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                if verbose:
                    logging.info(
                        "[%s] %s EXPIRED (mtime: %s, cutoff: %s)",
                        cron_job_id,
                        md_file.name,
                        mtime.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    )
                if not dry_run:
                    md_file.unlink()
                stats["deleted"] += 1
            else:
                if verbose:
                    logging.debug(
                        "[%s] %s OK (mtime: %s)",
                        cron_job_id,
                        md_file.name,
                        mtime.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    )
                stats["skipped"] += 1
        except OSError as exc:
            logging.error("[%s] Error processing %s: %s", cron_job_id, md_file.name, exc)
            stats["errors"] += 1

    return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean expired Hermes cron job log files."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be deleted without actually deleting anything.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-file details.",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Path to config.json (default: {DEFAULT_CONFIG_PATH})",
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        stream=sys.stdout,
    )

    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)

    # Validate required top-level keys
    for key in ("log_dir", "default_exp", "jobs"):
        if key not in config:
            print(f"ERROR: Missing required config field: '{key}'", file=sys.stderr)
            sys.exit(1)

    base_log_dir = Path(config["log_dir"]).expanduser().resolve()
    default_exp: int = int(config["default_exp"])
    jobs: list = config["jobs"]

    if not base_log_dir.exists():
        print(f"ERROR: base log_dir does not exist: {base_log_dir}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("=== DRY RUN — no files will be deleted ===")

    now_iso = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total_deleted = 0
    total_errors = 0

    for job in jobs:
        cron_job_id: Optional[str] = job.get("cron_job_id")
        if not cron_job_id:
            logging.warning("Job entry missing 'cron_job_id', skipping: %s", job)
            continue

        exp_days: int = job.get("exp", default_exp)
        stats = clean_job(
            job=job,
            base_log_dir=base_log_dir,
            default_exp=default_exp,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )

        alias: Optional[str] = job.get("alias")
        label = f"{alias} ({cron_job_id})" if alias else cron_job_id
        action_word = "Would delete" if args.dry_run else "Deleted"
        print(
            f"[{label}] {action_word} {stats['deleted']} / {stats['total']} files "
            f"older than {exp_days} day(s)"
            + (f" — {stats['errors']} error(s)" if stats["errors"] else "")
        )

        total_deleted += stats["deleted"]
        total_errors += stats["errors"]

        # Update last_run even in dry-run so operator can see when it last ran
        job["last_run"] = now_iso

    if len(jobs) > 1:
        print(
            f"\nTotal: {'Would delete' if args.dry_run else 'Deleted'} "
            f"{total_deleted} file(s) across {len(jobs)} job(s)"
            + (f" | {total_errors} error(s)" if total_errors else "")
        )

    # Persist updated last_run timestamps back to config
    if not args.dry_run:
        try:
            save_config(config, config_path)
        except RuntimeError as exc:
            print(f"WARNING: {exc}", file=sys.stderr)

    sys.exit(1 if total_errors else 0)


if __name__ == "__main__":
    main()
