#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
upload_report.py — Upload an HTML report to MinIO S3 via AWS SigV4.

Reads credentials from env vars MINIO_ACCESS_KEY and MINIO_SECRET_KEY
(or falls back to loading ~/.hermes/.env if not in environment).

Usage (standalone):
    python3.11 upload_report.py /path/to/report.html
    python3.11 upload_report.py /path/to/report.html --latest pennystock

As a module:
    from upload_report import upload_report, upload_as_latest
    ok, url = upload_report(Path("/path/to/report.html"))
    ok, url = upload_as_latest(Path("/path/to/report.html"), "pennystock")
"""

import hashlib
import hmac
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MINIO_ENDPOINT = "http://10.0.0.7:21059"
# Public-facing URL for Pushover notification links (proxied via Authentik)
PUBLIC_BASE_URL = "https://finance.tdkottke.com"
MINIO_BUCKET   = "reporting"
REGION         = "us-east-1"
SERVICE        = "s3"


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


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret_key: str, date_stamp: str) -> bytes:
    k = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k = _sign(k, REGION)
    k = _sign(k, SERVICE)
    k = _sign(k, "aws4_request")
    return k


def upload_report(report_path: Path, object_name: str | None = None) -> tuple[bool, str]:
    """
    Upload report_path to MinIO. Returns (success, public_url).
    If object_name is provided, it is used as the MinIO object filename instead
    of report_path.name — useful for uploading under a stable 'latest' key.
    Raises RuntimeError if credentials are missing.
    """
    _load_env_file()

    access_key = os.environ.get("MINIO_ACCESS_KEY")
    secret_key  = os.environ.get("MINIO_SECRET_KEY")
    if not access_key or not secret_key:
        raise RuntimeError(
            "MINIO_ACCESS_KEY and/or MINIO_SECRET_KEY not set. "
            "Add them to ~/.hermes/.env or the environment."
        )

    payload = report_path.read_bytes()
    filename = object_name if object_name is not None else report_path.name
    object_key = f"{MINIO_BUCKET}/{filename}"
    host = MINIO_ENDPOINT.replace("http://", "").replace("https://", "")

    now = datetime.now(timezone.utc)
    amz_date  = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    content_type   = "text/html; charset=utf-8"
    payload_hash   = hashlib.sha256(payload).hexdigest()

    # ── Canonical request ────────────────────────────────────────────────────
    canonical_uri     = f"/{object_key}"
    canonical_qs      = ""
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
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
    string_to_sign = "\n".join([
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

    upload_url = f"{MINIO_ENDPOINT}/{object_key}"
    public_url = f"{PUBLIC_BASE_URL}/{Path(object_key).relative_to(MINIO_BUCKET)}"
    req = urllib.request.Request(upload_url, data=payload, method="PUT")
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
    return success, public_url


def upload_as_latest(report_path: Path, portfolio_id: str) -> tuple[bool, str]:
    """
    Upload report_path under the stable '<portfolio_id>.latest.html' key.
    Overwrites any existing latest file on every call.
    Returns (success, public_url).
    """
    latest_name = f"{portfolio_id}.latest.html"
    return upload_report(report_path, object_name=latest_name)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Upload an HTML report to MinIO S3.")
    parser.add_argument("report_path", help="Path to the HTML report file")
    parser.add_argument(
        "--latest",
        metavar="PORTFOLIO_ID",
        help="Also upload under '<portfolio_id>.latest.html' stable key",
    )
    args = parser.parse_args()

    path = Path(args.report_path)
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    ok, url = upload_report(path)
    if ok:
        print(f"✅ Uploaded: {url}")
    else:
        print(f"⚠️  Upload returned non-success for: {url}")
        sys.exit(1)

    if args.latest:
        ok_latest, latest_url = upload_as_latest(path, args.latest)
        if ok_latest:
            print(f"✅ Latest uploaded: {latest_url}")
        else:
            print(f"⚠️  Latest upload returned non-success for: {latest_url}")
            sys.exit(1)
