#!/usr/bin/env python3
"""
get_journal_state.py — Hermes Journal State Helper

Reads a daily Obsidian note and returns JSON state for the hermes-journal
automation agent:
  - exists: whether the file exists
  - next_session_index: value from frontmatter (default 1)
  - logged_times: list of session times already written under ## Developer

Usage:
  python3 get_journal_state.py <path_to_daily_note>
  python3 get_journal_state.py <path_to_daily_note> --dry-run

Output (stdout):
  JSON blob, e.g.:
  {"exists": true, "next_session_index": 3, "logged_times": ["9:00 AM", "11:30 AM"]}
  {"exists": false}
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Optional


FRONTMATTER_KEY = "next_session_index"
SESSION_HEADER_RE = re.compile(
    r"^###\s+Session\s+\d+\s+-\s+(.+)$", re.IGNORECASE
)
FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL
)
FRONTMATTER_PROP_RE = re.compile(
    r"^(" + re.escape(FRONTMATTER_KEY) + r"\s*:\s*)(.+)$", re.MULTILINE
)


def parse_frontmatter_index(content: str) -> int:
    """Extract next_session_index from YAML frontmatter. Returns 1 if absent."""
    fm_match = FRONTMATTER_RE.match(content)
    if not fm_match:
        return 1
    fm_block = fm_match.group(1)
    prop_match = FRONTMATTER_PROP_RE.search(fm_block)
    if not prop_match:
        return 1
    try:
        return max(1, int(prop_match.group(2).strip()))
    except (ValueError, TypeError):
        return 1


def parse_logged_times(content: str) -> List[str]:
    """
    Scan the ## Developer section for existing ### Session headers
    and return the list of times already logged.
    """
    times = []
    in_developer = False

    for line in content.splitlines():
        stripped = line.strip()

        # Enter ## Developer section
        if re.match(r"^##\s+Developer\s*$", stripped):
            in_developer = True
            continue

        # Exit on next ## section
        if in_developer and re.match(r"^##\s+", stripped) and not re.match(r"^###", stripped):
            break

        if in_developer:
            m = SESSION_HEADER_RE.match(stripped)
            if m:
                times.append(m.group(1).strip())

    return times


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args:
        print(json.dumps({"error": "Usage: get_journal_state.py <path> [--dry-run]"}))
        sys.exit(1)

    path = Path(args[0]).expanduser()

    if not path.exists():
        print(json.dumps({"exists": False}))
        return

    content = path.read_text(encoding="utf-8")
    next_index = parse_frontmatter_index(content)
    logged_times = parse_logged_times(content)

    state = {
        "exists": True,
        "next_session_index": next_index,
        "logged_times": logged_times,
    }

    if dry_run:
        # Pretty-print for human inspection
        print(json.dumps(state, indent=2))
    else:
        print(json.dumps(state))


if __name__ == "__main__":
    main()
