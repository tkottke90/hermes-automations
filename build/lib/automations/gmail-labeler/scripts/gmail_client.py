#!/usr/bin/env python3
"""
gmail_client.py — Gmail API wrapper for the labeler automation.

Handles:
- OAuth credential loading and auto-refresh
- Fetching unread emails with full content
- Label ID resolution (with missing-label warnings)
- Applying labels and marking emails as read
"""

import base64
import os
import sys
from pathlib import Path
from typing import Optional, Dict, List, Any

TOKEN_PATH = Path.home() / ".hermes" / "google_token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def _load_env_key() -> str:
    """Load AUTOMATIONS_GMAIL_JSON_KEY from env or ~/.hermes/.env."""
    key = os.environ.get("AUTOMATIONS_GMAIL_JSON_KEY", "")
    if key:
        return key
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("AUTOMATIONS_GMAIL_JSON_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _get_credentials():
    """Load OAuth2 credentials, refreshing if needed."""
    try:
        from google.oauth2.credentials import Credentials  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
    except ImportError:
        print(
            "ERROR: google-auth is not installed.\n"
            "Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib",
            file=sys.stderr,
        )
        sys.exit(1)

    if not TOKEN_PATH.exists():
        print(
            f"ERROR: OAuth token not found at {TOKEN_PATH}\n"
            "Run first-time setup:\n"
            "  python3 scripts/setup_auth.py --auth-url\n"
            "  python3 scripts/setup_auth.py --auth-code \"CODE\"",
            file=sys.stderr,
        )
        sys.exit(1)

    import json
    with open(TOKEN_PATH) as f:
        token_data = json.load(f)

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes", SCOPES),
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Persist the refreshed token
        updated = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else SCOPES,
        }
        with open(TOKEN_PATH, "w") as f:
            json.dump(updated, f, indent=2)
            f.write("\n")

    return creds


def _decode_part(part: Dict[str, Any]) -> str:
    """Decode a base64url-encoded message part body."""
    data = part.get("body", {}).get("data", "")
    if not data:
        return ""
    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")


def _extract_body(payload: Dict[str, Any]) -> Dict[str, str]:
    """
    Recursively extract text/plain and text/html from a Gmail message payload.
    Returns {'plain': '...', 'html': '...'}.
    """
    result: Dict[str, str] = {"plain": "", "html": ""}
    mime = payload.get("mimeType", "")

    if mime == "text/plain" and not result["plain"]:
        result["plain"] = _decode_part(payload)
    elif mime == "text/html" and not result["html"]:
        result["html"] = _decode_part(payload)
    elif mime.startswith("multipart/"):
        for part in payload.get("parts", []):
            sub = _extract_body(part)
            if sub["plain"] and not result["plain"]:
                result["plain"] = sub["plain"]
            if sub["html"] and not result["html"]:
                result["html"] = sub["html"]

    return result


class GmailClient:
    """Authenticated Gmail API client."""

    def __init__(self) -> None:
        try:
            from googleapiclient.discovery import build  # type: ignore
        except ImportError:
            print(
                "ERROR: google-api-python-client is not installed.\n"
                "Run: pip install google-api-python-client",
                file=sys.stderr,
            )
            sys.exit(1)

        creds = _get_credentials()
        from googleapiclient.discovery import build  # type: ignore
        self._service = build("gmail", "v1", credentials=creds)
        self._label_cache: Optional[Dict[str, str]] = None  # name -> id

    def _get_all_labels(self) -> Dict[str, str]:
        """Fetch and cache all Gmail labels as {name: id}."""
        if self._label_cache is not None:
            return self._label_cache
        result = self._service.users().labels().list(userId="me").execute()
        self._label_cache = {
            lbl["name"]: lbl["id"] for lbl in result.get("labels", [])
        }
        return self._label_cache

    def resolve_label_ids(self, label_names: List[str]) -> Dict[str, Optional[str]]:
        """
        Resolve label names to IDs.
        Returns {name: id_or_None}. Logs a warning for each missing label.
        """
        all_labels = self._get_all_labels()
        resolved: Dict[str, Optional[str]] = {}
        for name in label_names:
            lid = all_labels.get(name)
            if lid is None:
                print(
                    f"[WARN] Label not found in Gmail: '{name}' — "
                    "create it in the Gmail UI and re-run.",
                    file=sys.stderr,
                )
            resolved[name] = lid
        return resolved

    def fetch_unread(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch up to `limit` unread emails.
        Returns list of dicts: {id, subject, sender, body_plain, body_html}.
        """
        emails: List[Dict[str, Any]] = []
        page_token: Optional[str] = None

        while len(emails) < limit:
            batch_size = min(100, limit - len(emails))
            kwargs: Dict[str, Any] = {
                "userId": "me",
                "q": "is:unread",
                "maxResults": batch_size,
            }
            if page_token:
                kwargs["pageToken"] = page_token

            result = self._service.users().messages().list(**kwargs).execute()
            messages = result.get("messages", [])
            if not messages:
                break

            for msg_stub in messages:
                if len(emails) >= limit:
                    break
                full_msg = (
                    self._service.users()
                    .messages()
                    .get(userId="me", id=msg_stub["id"], format="full")
                    .execute()
                )
                headers = {
                    h["name"].lower(): h["value"]
                    for h in full_msg.get("payload", {}).get("headers", [])
                }
                body = _extract_body(full_msg.get("payload", {}))
                emails.append(
                    {
                        "id": full_msg["id"],
                        "subject": headers.get("subject", "(no subject)"),
                        "sender": headers.get("from", ""),
                        "body_plain": body["plain"],
                        "body_html": body["html"],
                    }
                )

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return emails

    def apply_labels(self, email_id: str, label_ids: List[str]) -> None:
        """Apply the given label IDs to an email."""
        if not label_ids:
            return
        self._service.users().messages().modify(
            userId="me",
            id=email_id,
            body={"addLabelIds": label_ids},
        ).execute()

    def mark_as_read(self, email_id: str) -> None:
        """Remove the UNREAD label from an email."""
        self._service.users().messages().modify(
            userId="me",
            id=email_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
