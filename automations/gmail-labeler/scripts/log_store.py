#!/Users/thomaskottke/.hermes-automations/.venv/bin/python3
"""
log_store.py — JSON processing log with deduplication and retention pruning.

All writes are atomic (tempfile + os.replace) to prevent corruption.
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any


class LogStore:
    """Read/write the processed_log.json file for deduplication and observability."""

    def __init__(self, path: Path, retention_days: int = 30):
        self.path = path
        self.retention_days = retention_days
        self._cache: Optional[Dict[str, Any]] = None

    def _load(self) -> Dict[str, Any]:
        if self._cache is not None:
            return self._cache
        if not self.path.exists():
            self._cache = {}
            return self._cache
        try:
            with open(self.path) as f:
                self._cache = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[WARN] Could not load log file {self.path}: {e}", file=sys.stderr)
            self._cache = {}
        return self._cache  # type: ignore[return-value]

    def get_entry(self, md5: str, dry_run: bool = False) -> Optional[Dict[str, Any]]:
        """Return the log entry for this md5 if exists, otherwise None."""
        data = self._load()
        key = self._make_key(md5, dry_run)
        return data.get(key)

    def _save(self, data: Dict[str, Any]) -> None:
        """Atomically write data to the log file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self.path.parent, prefix=".log_tmp_", suffix=".json"
        )
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.replace(tmp_path, self.path)
            self._cache = data
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _make_key(self, md5: str, dry_run: bool) -> str:
        return f"DR-{md5}" if dry_run else md5

    def has_entry(self, md5: str, dry_run: bool = False) -> bool:
        """Return True if this md5 has already been processed (in the same mode)."""
        data = self._load()
        key = self._make_key(md5, dry_run)
        return key in data

    def write_entry(self, entry: Dict[str, Any], dry_run: bool = False) -> None:
        """Write a log entry. entry must contain 'md5' key."""
        data = self._load()
        key = self._make_key(entry["md5"], dry_run)
        data[key] = entry
        self._save(data)

    def prune_expired(self) -> int:
        """Remove entries older than retention_days. Returns count removed."""
        data = self._load()
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        to_remove = []
        for key, entry in data.items():
            try:
                ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                if ts < cutoff:
                    to_remove.append(key)
            except (KeyError, ValueError):
                pass  # malformed entry — leave it alone

        if to_remove:
            for key in to_remove:
                del data[key]
            self._save(data)

        return len(to_remove)

    def entry_count(self) -> int:
        return len(self._load())
