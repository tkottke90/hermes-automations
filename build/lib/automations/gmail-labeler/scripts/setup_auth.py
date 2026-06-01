#!/usr/bin/env python3
"""
setup_auth.py — First-run OAuth 2.0 setup for the Gmail Labeler automation.

Usage:
  python3 setup_auth.py --auth-url          # Print the browser authorization URL
  python3 setup_auth.py --auth-code "CODE"  # Complete the flow with the auth code

Token is saved to ~/.hermes/google_token.json (shared with other Gmail automations).
"""

import argparse
import os
import sys
from pathlib import Path

# Credentials and token paths
TOKEN_PATH = Path.home() / ".hermes" / "google_token.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
]

_REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"  # Out-of-band — no local server needed


def _get_client_secrets_path() -> Path:
    key = os.environ.get("AUTOMATIONS_GMAIL_JSON_KEY", "")
    if not key:
        # Try loading from ~/.hermes/.env
        env_file = Path.home() / ".hermes" / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("AUTOMATIONS_GMAIL_JSON_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not key:
        print(
            "ERROR: AUTOMATIONS_GMAIL_JSON_KEY is not set.\n"
            "Add it to ~/.hermes/.env:\n"
            "  AUTOMATIONS_GMAIL_JSON_KEY=/path/to/oauth_client_secrets.json",
            file=sys.stderr,
        )
        sys.exit(1)
    path = Path(key)
    if not path.exists():
        print(f"ERROR: Client secrets file not found: {path}", file=sys.stderr)
        sys.exit(1)
    return path


def cmd_auth_url() -> None:
    """Print the browser authorization URL."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
    except ImportError:
        print(
            "ERROR: google-auth-oauthlib is not installed.\n"
            "Run: pip install google-auth-oauthlib",
            file=sys.stderr,
        )
        sys.exit(1)

    secrets_path = _get_client_secrets_path()
    flow = InstalledAppFlow.from_client_secrets_file(
        str(secrets_path), scopes=SCOPES, redirect_uri=_REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    print("\n=== Gmail Labeler — OAuth Setup ===\n")
    print("1. Open the following URL in your browser:")
    print(f"\n   {auth_url}\n")
    print("2. Grant access, then copy the authorization code shown.")
    print("3. Run:")
    print('   python3 setup_auth.py --auth-code "PASTE_CODE_HERE"\n')


def cmd_auth_code(code: str) -> None:
    """Complete the OAuth flow with the provided code and save the token."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
        import google.oauth2.credentials  # type: ignore
    except ImportError:
        print(
            "ERROR: google-auth-oauthlib is not installed.\n"
            "Run: pip install google-auth-oauthlib",
            file=sys.stderr,
        )
        sys.exit(1)

    secrets_path = _get_client_secrets_path()
    flow = InstalledAppFlow.from_client_secrets_file(
        str(secrets_path), scopes=SCOPES, redirect_uri=_REDIRECT_URI
    )
    flow.fetch_token(code=code)
    creds = flow.credentials

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }
    import json

    with open(TOKEN_PATH, "w") as f:
        json.dump(token_data, f, indent=2)
        f.write("\n")

    print(f"\n✓ Token saved to {TOKEN_PATH}")
    print("You can now run the gmail-labeler automation.\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gmail Labeler — OAuth setup helper"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--auth-url",
        action="store_true",
        help="Print the browser authorization URL",
    )
    group.add_argument(
        "--auth-code",
        metavar="CODE",
        help="Complete OAuth flow with the authorization code",
    )
    args = parser.parse_args()

    if args.auth_url:
        cmd_auth_url()
    elif args.auth_code:
        cmd_auth_code(args.auth_code)


if __name__ == "__main__":
    main()
