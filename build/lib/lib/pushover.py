#!/usr/bin/env python3
"""
pushover.py — Shared Pushover notification utility.

Reads credentials from env vars PUSHOVER_TOKEN and PUSHOVER_USER
(or falls back to loading ~/.hermes/.env if not in environment).

Usage (standalone):
    python pushover.py "Title" "Message"
    python pushover.py "Title" "Message" --sound cashregister --url https://example.com
    python pushover.py --dry-run "Title" "Message"   # prints payload, does not POST

As a module:
    from pathlib import Path
    import sys; sys.path.insert(0, str(Path.home() / ".hermes" / "lib"))
    from pushover import send_notification
    ok = send_notification("Title", "Hello", url="https://example.com", sound="cashregister", ttl=3600)
"""

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

_env_loaded = False


def _load_env_file():
    """Load ~/.hermes/.env into os.environ if creds not already set."""
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    env_path = Path.home() / ".hermes" / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        if key.strip() not in os.environ:
            os.environ[key.strip()] = val.strip()


def send_notification(
    title: str,
    message: str,
    *,
    url: Optional[str] = None,
    url_title: str = "Open",
    sound: str = "pushover",
    ttl: Optional[int] = None,
    priority: int = 0,
    dry_run: bool = False,
) -> bool:
    """
    Send a Pushover notification. Returns True on success.
    Reads PUSHOVER_TOKEN and PUSHOVER_USER from env (or ~/.hermes/.env).
    Raises RuntimeError if credentials are missing.
    """
    _load_env_file()

    token = os.environ.get("PUSHOVER_TOKEN")
    user = os.environ.get("PUSHOVER_USER")

    if not token or not user:
        missing = [v for v, val in [("PUSHOVER_TOKEN", token), ("PUSHOVER_USER", user)] if not val]
        raise RuntimeError(
            f"Missing Pushover credentials: {', '.join(missing)}. "
            "Set them in your shell environment or in ~/.hermes/.env."
        )

    data = {
        "token": token,
        "user": user,
        "title": title,
        "message": message,
        "sound": sound,
        "priority": priority,
    }
    if url:
        data["url"] = url
        data["url_title"] = url_title
    if ttl is not None:
        data["ttl"] = ttl

    if dry_run:
        print("[dry-run] Would POST to https://api.pushover.net/1/messages.json:")
        print(json.dumps(data, indent=2))
        return True

    encoded = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        "https://api.pushover.net/1/messages.json",
        data=encoded,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
        return result.get("status") == 1


# ── Standalone CLI ────────────────────────────────────────────────────────────

def _main():
    import argparse

    parser = argparse.ArgumentParser(description="Send a Pushover notification")
    parser.add_argument("title", help="Notification title")
    parser.add_argument("message", help="Notification message")
    parser.add_argument("--sound", default="pushover", help="Pushover sound name (default: pushover)")
    parser.add_argument("--url", default=None, help="Optional action URL")
    parser.add_argument("--url-title", default="Open", help="URL button label (default: Open)")
    parser.add_argument("--ttl", type=int, default=None, help="Message TTL in seconds")
    parser.add_argument("--priority", type=int, default=0, help="Message priority (-2..2, default: 0)")
    parser.add_argument("--dry-run", action="store_true", help="Print payload without sending")
    args = parser.parse_args()

    ok = send_notification(
        args.title,
        args.message,
        url=args.url,
        url_title=args.url_title,
        sound=args.sound,
        ttl=args.ttl,
        priority=args.priority,
        dry_run=args.dry_run,
    )
    if not args.dry_run:
        print("✓ Notification sent" if ok else "✗ Notification failed")


if __name__ == "__main__":
    _main()
