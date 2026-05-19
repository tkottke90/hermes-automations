---
name: stock-monitor
description: "Stock price threshold monitor — alerts when prices cross configured thresholds or spike >20% in 24h, and sends a daily close summary."
version: 1.0.0
author: tkottke
license: UNLICENSED
schedule: "*/15 8-17 * * 1-5"
platforms: [macos, linux]
metadata:
  hermes:
    tags: [finance, stocks, alerts, monitoring]
    scripts:
      - name: stock-monitor
        file: stock_monitor.py
        no_agent: true
        deliver: origin
        schedule: "*/15 8-17 * * 1-5"
    dependencies:
      - yfinance
    env:
      - PUSHOVER_TOKEN
      - PUSHOVER_USER
---

# Stock Monitor

Monitors stock tickers for price threshold crossings and significant single-day moves. Runs every 15 minutes during market hours (Mon–Fri 8–17 CT) and sends Pushover notifications when conditions are met. Generates a daily close summary after market close.

A companion `stock_report.py` script generates and uploads an HTML dashboard to MinIO on demand.

## Files

| File | Purpose |
|---|---|
| `scripts/stock_monitor.py` | Cron entry point — threshold checks + daily summary |
| `scripts/stock_report.py` | HTML report generator + MinIO uploader |
| `data/tickers.json` | Ticker configuration with alert thresholds |
| `data/tickers/` | Per-ticker state files (day-open price, alert history) |
| `data/reports/` | Generated HTML reports (gitignored) |

## Ticker Configuration

`data/tickers.json` defines which tickers to monitor and their alert thresholds. Example:

```json
[
  {
    "symbol": "AAPL",
    "alert_above": 200.00,
    "alert_below": 150.00
  }
]
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `PUSHOVER_TOKEN` | Yes | Pushover application token |
| `PUSHOVER_USER` | Yes | Pushover user key |
| `MINIO_ENDPOINT` | For report only | MinIO server URL |
| `MINIO_ACCESS_KEY` | For report only | MinIO access key |
| `MINIO_SECRET_KEY` | For report only | MinIO secret key |
| `MINIO_BUCKET` | For report only | Bucket name |
