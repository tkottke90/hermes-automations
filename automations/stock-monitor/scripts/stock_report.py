#!/usr/bin/env python3
"""
stock_report.py — Generate and upload a stock ticker monitor HTML report.

Reads all tickers from ~/.hermes/finance/stocks/tickers.json and their
state files, then renders a dark-themed HTML dashboard and uploads it to
MinIO at reporting/ticker-monitor.html (overwrites on every run).

Usage:
    python3 stock_report.py              # generate + upload
    python3 stock_report.py --dry-run    # generate, save locally, skip upload
"""

import hashlib
import hmac
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR      = Path.home() / ".hermes" / "finance" / "stocks"
TICKERS_FILE  = BASE_DIR / "tickers.json"
TICKERS_DIR   = BASE_DIR / "tickers"
REPORTS_DIR   = BASE_DIR / "reports"
REPORT_NAME   = "ticker-monitor.html"

# ── MinIO ────────────────────────────────────────────────────────────────────
MINIO_ENDPOINT = "http://10.0.0.7:21059"
MINIO_BUCKET   = "reporting"
REGION         = "us-east-1"
SERVICE        = "s3"

# ── Market hours (ET, rough) ─────────────────────────────────────────────────
MARKET_OPEN_UTC  = 13   # 9:30 AM ET ≈ 13:30 UTC (CDT) / 14:30 UTC (CST)
MARKET_CLOSE_UTC = 21   # 4:00 PM ET ≈ 20:00 UTC (CDT) / 21:00 UTC (CST)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_env_file():
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


def _pct_change(new_val, old_val):
    if old_val and old_val != 0:
        return ((new_val - old_val) / old_val) * 100
    return None


def _is_market_open(now: datetime) -> bool:
    if now.weekday() >= 5:  # Sat/Sun
        return False
    return MARKET_OPEN_UTC <= now.hour < MARKET_CLOSE_UTC


# ─────────────────────────────────────────────────────────────────────────────
# Data collection
# ─────────────────────────────────────────────────────────────────────────────

def collect_ticker_data(tickers_config: dict, now: datetime) -> list[dict]:
    """
    Build a list of ticker data dicts from config + state files.
    Uses last_price from state (the monitor already fetched it this run)
    to avoid redundant API calls. Falls back to a live fetch if state is missing.
    """
    try:
        import yfinance as yf
    except ImportError:
        os.system(f"{sys.executable} -m pip install yfinance -q")
        import yfinance as yf

    rows = []
    for ticker, config in tickers_config.items():
        state_path = TICKERS_DIR / f"{ticker.lower()}_state.json"
        state = {}
        if state_path.exists():
            with open(state_path) as f:
                state = json.load(f)

        price = state.get("last_price")
        if price is None:
            # No state yet — try a live fetch
            try:
                price = round(float(yf.Ticker(ticker).fast_info.last_price), 4)
            except Exception:
                price = None

        # Company name — try yfinance info, fall back to ticker symbol
        company_name = ticker
        try:
            info = yf.Ticker(ticker).info
            company_name = info.get("shortName") or info.get("longName") or ticker
        except Exception:
            pass

        day_open    = state.get("day_open_price")
        day_chg_pct = _pct_change(price, day_open) if price else None

        baseline_price     = state.get("price")
        baseline_time_str  = state.get("timestamp")
        baseline_chg_pct   = None
        if price and baseline_price and baseline_time_str:
            hours = (now - datetime.fromisoformat(baseline_time_str)).total_seconds() / 3600
            if hours >= 1:  # Only show if meaningful time has elapsed
                baseline_chg_pct = _pct_change(price, baseline_price)

        last_checked = state.get("last_checked")
        if last_checked:
            try:
                last_checked = datetime.fromisoformat(last_checked).strftime("%Y-%m-%d %H:%M UTC")
            except Exception:
                pass

        rows.append({
            "ticker":          ticker,
            "company":         company_name,
            "price":           price,
            "day_open":        day_open,
            "day_chg_pct":     day_chg_pct,
            "baseline_price":  baseline_price,
            "baseline_chg_pct": baseline_chg_pct,
            "threshold_low":   config.get("threshold_low"),
            "threshold_high":  config.get("threshold_high"),
            "change_alert_pct": config.get("change_alert_pct", 20.0),
            "crossed_low":     state.get("crossed_low", False),
            "crossed_high":    state.get("crossed_high", False),
            "last_checked":    last_checked or "—",
            "day_open_date":   state.get("day_open_date", "—"),
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# HTML rendering
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_price(val):
    if val is None:
        return "—"
    return f"${val:,.4f}" if val < 100 else f"${val:,.2f}"


def _fmt_pct(val, show_sign=True):
    if val is None:
        return "—"
    sign = "+" if val >= 0 and show_sign else ""
    return f"{sign}{val:.2f}%"


def _pct_color_class(val):
    if val is None:
        return "neutral"
    return "positive" if val >= 0 else "negative"


def _threshold_bar_html(price, low, high):
    """Render a simple visual bar showing where price sits vs thresholds."""
    if price is None or (low is None and high is None):
        return ""

    if low is None:
        low = price * 0.5
    if high is None:
        high = price * 1.5

    span = high - low
    if span <= 0:
        return ""

    pct = min(max((price - low) / span * 100, 0), 100)
    bar_color = "#22c55e" if price >= high else ("#ef4444" if price <= low else "#f59e0b")

    return f"""
    <div class="threshold-bar-wrap">
      <div class="threshold-bar-labels">
        <span>Low {_fmt_price(low)}</span>
        <span>High {_fmt_price(high)}</span>
      </div>
      <div class="threshold-bar-track">
        <div class="threshold-bar-fill" style="width:{pct:.1f}%; background:{bar_color};"></div>
        <div class="threshold-bar-marker" style="left:{pct:.1f}%;"></div>
      </div>
    </div>"""


def _alert_badges_html(crossed_low, crossed_high, threshold_low, threshold_high):
    badges = []
    if threshold_low is not None:
        if crossed_low:
            badges.append('<span class="badge badge-above-low">▲ Above Low Threshold</span>')
        else:
            badges.append('<span class="badge badge-below-low">▼ Below Low Threshold</span>')
    if threshold_high is not None:
        if crossed_high:
            badges.append('<span class="badge badge-above-high">🚀 Above High Threshold</span>')
        else:
            badges.append('<span class="badge badge-normal">● Within Range</span>')
    if not badges:
        badges.append('<span class="badge badge-normal">● Monitoring</span>')
    return " ".join(badges)


def render_html(rows: list[dict], now: datetime) -> str:
    market_open = _is_market_open(now)
    market_status_label = "🟢 Market Open" if market_open else "🔴 Market Closed"
    market_status_class = "open" if market_open else "closed"
    generated = now.strftime("%Y-%m-%d %H:%M UTC")
    ticker_count = len(rows)

    # Overview stats
    tickers_with_price = [r for r in rows if r["price"] is not None]
    gainers = sum(1 for r in tickers_with_price if (r["day_chg_pct"] or 0) >= 0)
    losers  = len(tickers_with_price) - gainers

    cards_html = ""
    for r in rows:
        price_str       = _fmt_price(r["price"])
        day_open_str    = _fmt_price(r["day_open"])
        day_chg_str     = _fmt_pct(r["day_chg_pct"])
        day_chg_class   = _pct_color_class(r["day_chg_pct"])
        b_price_str     = _fmt_price(r["baseline_price"])
        b_chg_str       = _fmt_pct(r["baseline_chg_pct"])
        b_chg_class     = _pct_color_class(r["baseline_chg_pct"])
        threshold_bar   = _threshold_bar_html(r["price"], r["threshold_low"], r["threshold_high"])
        alert_badges    = _alert_badges_html(r["crossed_low"], r["crossed_high"], r["threshold_low"], r["threshold_high"])

        cards_html += f"""
    <div class="card">
      <div class="card-header">
        <div>
          <div class="ticker-symbol">{r["ticker"]}</div>
          <div class="company-name">{r["company"]}</div>
        </div>
        <div class="price-block">
          <div class="current-price">{price_str}</div>
          <div class="day-change {day_chg_class}">{day_chg_str} today</div>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat">
          <div class="stat-label">Day Open</div>
          <div class="stat-value">{day_open_str}</div>
        </div>
        <div class="stat">
          <div class="stat-label">Day Change</div>
          <div class="stat-value {day_chg_class}">{day_chg_str}</div>
        </div>
        <div class="stat">
          <div class="stat-label">24h Baseline</div>
          <div class="stat-value">{b_price_str}</div>
        </div>
        <div class="stat">
          <div class="stat-label">24h Change</div>
          <div class="stat-value {b_chg_class}">{b_chg_str}</div>
        </div>
        <div class="stat">
          <div class="stat-label">Low Threshold</div>
          <div class="stat-value">{_fmt_price(r["threshold_low"])}</div>
        </div>
        <div class="stat">
          <div class="stat-label">High Threshold</div>
          <div class="stat-value">{_fmt_price(r["threshold_high"])}</div>
        </div>
      </div>

      {threshold_bar}

      <div class="badges">{alert_badges}</div>

      <div class="last-checked">Last checked: {r["last_checked"]}</div>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ticker Monitor</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f1117;
      color: #e2e8f0;
      min-height: 100vh;
      padding: 2rem 1.5rem;
    }}

    .page-header {{
      max-width: 1100px;
      margin: 0 auto 2rem;
    }}
    .page-header-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .page-title {{
      font-size: 1.75rem;
      font-weight: 700;
      color: #f8fafc;
      letter-spacing: -0.02em;
    }}
    .page-subtitle {{
      color: #94a3b8;
      font-size: 0.875rem;
      margin-top: 0.25rem;
    }}
    .refresh-btn {{
      background: #1e2433;
      border: 1px solid #2d3748;
      color: #94a3b8;
      font-size: 0.875rem;
      font-weight: 600;
      padding: 0.5rem 1rem;
      border-radius: 8px;
      cursor: pointer;
      transition: background 0.15s, color 0.15s, border-color 0.15s;
    }}
    .refresh-btn:hover {{
      background: #2d3748;
      color: #f1f5f9;
      border-color: #4a5568;
    }}

    /* ── Overview ── */
    .overview {{
      max-width: 1100px;
      margin: 0 auto 2rem;
      background: #1e2433;
      border: 1px solid #2d3748;
      border-radius: 12px;
      padding: 1.25rem 1.5rem;
      display: flex;
      flex-wrap: wrap;
      gap: 1.5rem;
      align-items: center;
    }}
    .overview-stat {{
      display: flex;
      flex-direction: column;
      gap: 0.15rem;
    }}
    .overview-stat-label {{
      font-size: 0.75rem;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .overview-stat-value {{
      font-size: 1.1rem;
      font-weight: 600;
      color: #f1f5f9;
    }}
    .market-status {{
      margin-left: auto;
      font-size: 0.85rem;
      font-weight: 600;
      padding: 0.35rem 0.85rem;
      border-radius: 999px;
    }}
    .market-status.open  {{ background: #14532d; color: #4ade80; }}
    .market-status.closed {{ background: #450a0a; color: #f87171; }}

    /* ── Cards grid ── */
    .cards {{
      max-width: 1100px;
      margin: 0 auto;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 1.25rem;
    }}
    .card {{
      background: #1e2433;
      border: 1px solid #2d3748;
      border-radius: 12px;
      padding: 1.25rem 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }}

    /* ── Card header ── */
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
    }}
    .ticker-symbol {{
      font-size: 1.4rem;
      font-weight: 700;
      color: #f8fafc;
      letter-spacing: 0.03em;
    }}
    .company-name {{
      font-size: 0.8rem;
      color: #64748b;
      margin-top: 0.15rem;
    }}
    .price-block {{
      text-align: right;
    }}
    .current-price {{
      font-size: 1.5rem;
      font-weight: 700;
      color: #f8fafc;
    }}
    .day-change {{
      font-size: 0.85rem;
      font-weight: 600;
      margin-top: 0.2rem;
    }}

    /* ── Stats grid ── */
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 0.75rem;
    }}
    .stat {{
      background: #141824;
      border-radius: 8px;
      padding: 0.6rem 0.75rem;
    }}
    .stat-label {{
      font-size: 0.7rem;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.2rem;
    }}
    .stat-value {{
      font-size: 0.95rem;
      font-weight: 600;
      color: #e2e8f0;
    }}

    /* ── Colors ── */
    .positive {{ color: #4ade80; }}
    .negative {{ color: #f87171; }}
    .neutral  {{ color: #94a3b8; }}

    /* ── Threshold bar ── */
    .threshold-bar-wrap {{
      display: flex;
      flex-direction: column;
      gap: 0.3rem;
    }}
    .threshold-bar-labels {{
      display: flex;
      justify-content: space-between;
      font-size: 0.7rem;
      color: #64748b;
    }}
    .threshold-bar-track {{
      position: relative;
      height: 6px;
      background: #2d3748;
      border-radius: 999px;
      overflow: visible;
    }}
    .threshold-bar-fill {{
      height: 100%;
      border-radius: 999px;
      transition: width 0.3s;
    }}
    .threshold-bar-marker {{
      position: absolute;
      top: -3px;
      width: 12px;
      height: 12px;
      background: #f8fafc;
      border-radius: 50%;
      transform: translateX(-50%);
      border: 2px solid #0f1117;
    }}

    /* ── Badges ── */
    .badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
    }}
    .badge {{
      font-size: 0.7rem;
      font-weight: 600;
      padding: 0.25rem 0.6rem;
      border-radius: 999px;
      letter-spacing: 0.02em;
    }}
    .badge-above-low   {{ background: #14532d; color: #4ade80; }}
    .badge-below-low   {{ background: #450a0a; color: #f87171; }}
    .badge-above-high  {{ background: #1e3a5f; color: #60a5fa; }}
    .badge-normal      {{ background: #292524; color: #a8a29e; }}

    /* ── Last checked ── */
    .last-checked {{
      font-size: 0.7rem;
      color: #475569;
      margin-top: auto;
    }}

    /* ── Footer ── */
    .footer {{
      max-width: 1100px;
      margin: 2rem auto 0;
      text-align: center;
      font-size: 0.75rem;
      color: #334155;
    }}
  </style>
</head>
<body>

  <div class="page-header">
    <div class="page-header-top">
      <div>
        <div class="page-title">📈 Ticker Monitor</div>
        <div class="page-subtitle">Generated {generated} · Refreshes every 15 min on market days</div>
      </div>
      <button class="refresh-btn" onclick="window.location.reload()">↻ Refresh</button>
    </div>
  </div>

  <div class="overview">
    <div class="overview-stat">
      <div class="overview-stat-label">Tickers Tracked</div>
      <div class="overview-stat-value">{ticker_count}</div>
    </div>
    <div class="overview-stat">
      <div class="overview-stat-label">Gainers Today</div>
      <div class="overview-stat-value positive">{gainers}</div>
    </div>
    <div class="overview-stat">
      <div class="overview-stat-label">Losers Today</div>
      <div class="overview-stat-value negative">{losers}</div>
    </div>
    <div class="overview-stat">
      <div class="overview-stat-label">Report Time</div>
      <div class="overview-stat-value">{generated}</div>
    </div>
    <span class="market-status {market_status_class}">{market_status_label}</span>
  </div>

  <div class="cards">
    {cards_html}
  </div>

  <div class="footer">
    Stock data via Yahoo Finance · Alerts delivered via Pushover · Hosted on MinIO
  </div>

</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# MinIO upload (SigV4, stdlib only)
# ─────────────────────────────────────────────────────────────────────────────

def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret_key: str, date_stamp: str) -> bytes:
    k = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k = _sign(k, REGION)
    k = _sign(k, SERVICE)
    k = _sign(k, "aws4_request")
    return k


def upload_report(report_path: Path) -> tuple[bool, str]:
    """Upload report_path to MinIO reporting bucket. Returns (success, url)."""
    _load_env_file()
    access_key = os.environ.get("MINIO_ACCESS_KEY")
    secret_key  = os.environ.get("MINIO_SECRET_KEY")
    if not access_key or not secret_key:
        raise RuntimeError(
            "MINIO_ACCESS_KEY and/or MINIO_SECRET_KEY not set. "
            "Add them to ~/.hermes/.env or the environment."
        )

    payload     = report_path.read_bytes()
    object_key  = report_path.name          # "ticker-monitor.html"
    host        = MINIO_ENDPOINT.replace("http://", "").replace("https://", "")

    now_dt      = datetime.now(timezone.utc)
    amz_date    = now_dt.strftime("%Y%m%dT%H%M%SZ")
    date_stamp  = now_dt.strftime("%Y%m%d")

    content_type  = "text/html; charset=utf-8"
    payload_hash  = hashlib.sha256(payload).hexdigest()

    canonical_uri     = f"/{MINIO_BUCKET}/{object_key}"
    canonical_qs      = ""
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers    = "content-type;host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join([
        "PUT", canonical_uri, canonical_qs,
        canonical_headers, signed_headers, payload_hash,
    ])

    credential_scope = f"{date_stamp}/{REGION}/{SERVICE}/aws4_request"
    string_to_sign   = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])

    signing_key = _signing_key(secret_key, date_stamp)
    signature   = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    auth_header = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    url = f"{MINIO_ENDPOINT}/{MINIO_BUCKET}/{object_key}"
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

    return status in (200, 204), url


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def generate_report() -> Path:
    """Build HTML report, save locally, return path."""
    if not TICKERS_FILE.exists():
        raise FileNotFoundError(f"Tickers config not found: {TICKERS_FILE}")

    with open(TICKERS_FILE) as f:
        tickers_config = json.load(f)

    if not tickers_config:
        raise ValueError("No tickers found in tickers.json")

    now  = datetime.now(timezone.utc)
    rows = collect_ticker_data(tickers_config, now)
    html = render_html(rows, now)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / REPORT_NAME
    report_path.write_text(html, encoding="utf-8")
    print(f"[stock_report] 📄 Report saved: {report_path}", flush=True)
    return report_path


def main():
    dry_run = "--dry-run" in sys.argv

    try:
        report_path = generate_report()
    except Exception as e:
        print(f"[stock_report] ❌ Report generation failed: {e}", flush=True)
        sys.exit(1)

    if dry_run:
        print(f"[stock_report] 🔍 Dry-run — skipping upload. Open: {report_path}", flush=True)
        return

    try:
        ok, url = upload_report(report_path)
        if ok:
            print(f"[stock_report] ✅ Uploaded: {url}", flush=True)
        else:
            print(f"[stock_report] ⚠️  Upload returned non-success for: {url}", flush=True)
    except Exception as e:
        print(f"[stock_report] ❌ Upload failed: {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
