#!/usr/bin/env python3
"""
report-publisher.py — Shared MinIO report upload utility (AWS SigV4).

Reads credentials from env vars MINIO_ACCESS_KEY and MINIO_SECRET_KEY
(or falls back to loading ~/.hermes/.env if not in environment).

Usage (standalone):
    python report-publisher.py <report_path> [object_name] [--dry-run]

    <report_path>   Local file to upload
    [object_name]   Override the object name in MinIO (default: basename of report_path)
    --dry-run       Print what would be uploaded without making the HTTP request

As a module:
    from pathlib import Path
    import sys; sys.path.insert(0, str(Path.home() / ".hermes" / "lib"))
    from report_publisher import publish_report
    ok, url = publish_report(Path("/path/to/file.html"))
    ok, url = publish_report(Path("/tmp/data.json"), object_name="server-update-report.json")
"""

import hashlib
import hmac
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MINIO_ENDPOINT = "http://10.0.0.7:21059"
MINIO_BUCKET   = "reporting"
REGION         = "us-east-1"
SERVICE        = "s3"

# Content-type map by file extension
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm":  "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".txt":  "text/plain; charset=utf-8",
    ".csv":  "text/csv; charset=utf-8",
    ".xml":  "application/xml; charset=utf-8",
    ".pdf":  "application/pdf",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _load_env_file():
    """Load ~/.hermes/.env into os.environ if creds not already set."""
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


def _content_type_for(path: Path) -> str:
    """Return content-type based on file extension."""
    return _CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret_key: str, date_stamp: str) -> bytes:
    k = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k = _sign(k, REGION)
    k = _sign(k, SERVICE)
    k = _sign(k, "aws4_request")
    return k


def publish_report(
    report_path: Path,
    object_name: str | None = None,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """
    Upload report_path to MinIO. Returns (success, public_url).

    Args:
        report_path:  Local file to upload.
        object_name:  Object name (key) in the bucket. Defaults to report_path.name.
        dry_run:      If True, print what would be uploaded and return (True, url) without uploading.

    Raises:
        RuntimeError: If credentials are missing or the upload fails.
    """
    _load_env_file()

    access_key = os.environ.get("MINIO_ACCESS_KEY")
    secret_key  = os.environ.get("MINIO_SECRET_KEY")
    if not access_key or not secret_key:
        raise RuntimeError(
            "MINIO_ACCESS_KEY and/or MINIO_SECRET_KEY not set. "
            "Add them to ~/.hermes/.env or the environment."
        )

    name         = object_name or report_path.name
    content_type = _content_type_for(Path(name))  # sniff from target name, not source path
    object_key   = f"{MINIO_BUCKET}/{name}"
    url          = f"{MINIO_ENDPOINT}/{object_key}"

    if dry_run:
        print(f"[DRY RUN] Would upload: {report_path}")
        print(f"[DRY RUN]   → {url}")
        print(f"[DRY RUN]   Content-Type: {content_type}")
        print(f"[DRY RUN]   Size: {report_path.stat().st_size:,} bytes")
        return True, url

    payload      = report_path.read_bytes()
    host         = MINIO_ENDPOINT.replace("http://", "").replace("https://", "")

    now          = datetime.now(timezone.utc)
    amz_date     = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp   = now.strftime("%Y%m%d")

    payload_hash = hashlib.sha256(payload).hexdigest()

    # ── Canonical request ────────────────────────────────────────────────────
    canonical_uri     = f"/{object_key}"
    canonical_qs      = ""
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers    = "content-type;host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join([
        "PUT",
        canonical_uri,
        canonical_qs,
        canonical_headers,
        signed_headers,
        payload_hash,
    ])

    # ── String to sign ───────────────────────────────────────────────────────
    credential_scope = f"{date_stamp}/{REGION}/{SERVICE}/aws4_request"
    string_to_sign   = "\n".join([
        "AWS4-HMAC-SHA256",
        amz_date,
        credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])

    # ── Signature ────────────────────────────────────────────────────────────
    signing_key = _signing_key(secret_key, date_stamp)
    signature   = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    auth_header = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    req = urllib.request.Request(url, data=payload, method="PUT")
    req.add_header("Content-Type", content_type)
    req.add_header("Host", host)
    req.add_header("x-amz-content-sha256", payload_hash)
    req.add_header("x-amz-date", amz_date)
    req.add_header("Authorization", auth_header)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"MinIO PUT failed HTTP {e.code}: {body}") from e

    success = status in (200, 204)
    return success, url


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry  = "--dry-run" in sys.argv

    if not args:
        print("Usage: report-publisher.py <report_path> [object_name] [--dry-run]")
        sys.exit(1)

    path = Path(args[0])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    obj_name = args[1] if len(args) > 1 else None

    try:
        ok, url = publish_report(path, object_name=obj_name, dry_run=dry)
    except RuntimeError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

    if ok:
        print(f"✅ Published: {url}")
    else:
        print(f"⚠️  Upload returned non-success for: {url}")
        sys.exit(1)
