---
name: reddit-portfolio
description: "LLM-driven Reddit paper trading tracker — scans subreddits for tickers, makes simulated trades, and publishes daily reports to MinIO."
version: 1.0.0
author: tkottke
license: UNLICENSED
schedule: "*/15 * * * 1-5"
platforms: [macos, linux]
metadata:
  hermes:
    tags: [finance, reddit, trading, paper-trading, llm]
    scripts:
      - name: portfolio-scan
        file: cron_scan.py
        no_agent: true
        deliver: local
        schedule: "*/15 * * * 1-5"
      - name: daily-report
        file: cron_daily_report.py
        no_agent: true
        deliver: local
        schedule: "5 2 * * 1-5"
    dependencies:
      - yfinance
      - requests
      - praw
    env:
      - REDDIT_CLIENT_ID
      - REDDIT_CLIENT_SECRET
      - REDDIT_USER_AGENT
      - MINIO_ENDPOINT
      - MINIO_ACCESS_KEY
      - MINIO_SECRET_KEY
      - MINIO_BUCKET
      - PUSHOVER_TOKEN  # sourced from ~/.hermes/.env if not in shell environment
      - PUSHOVER_USER   # sourced from ~/.hermes/.env if not in shell environment
---

# Reddit Portfolio

An LLM-driven paper trading system that monitors Reddit subreddits for stock ticker mentions, uses an LLM to evaluate sentiment and make simulated buy/sell decisions, and publishes daily HTML reports to MinIO.

## Architecture

```
cron_scan.py          ← 15-min cron entry point
  └── run_cycle.py    ← orchestrates one scan cycle per portfolio
        ├── reddit_scanner.py   ← fetches posts from Reddit API
        ├── price_fetcher.py    ← gets current prices via yfinance
        ├── llm_trader.py       ← LLM buy/sell decision engine
        ├── trade_engine.py     ← applies decisions to portfolio state
        └── upload_report.py    ← uploads HTML to MinIO

cron_daily_report.py  ← 2:05 AM UTC cron entry point
  └── daily_report.py ← generates and uploads daily summary HTML
        └── report_generator.py
```

## Setup

1. Copy `config.json.example` to `data/config.json` and fill in portfolio settings
2. Ensure all environment variables are set in `~/.hermes/.env` or shell profile
3. Run `setup.py` to initialize portfolio state files

## Files

| File | Purpose |
|---|---|
| `scripts/cron_scan.py` | 15-min cron entry point |
| `scripts/cron_daily_report.py` | Daily report cron entry point |
| `scripts/run_cycle.py` | Single scan cycle orchestrator |
| `scripts/reddit_scanner.py` | Reddit API fetcher |
| `scripts/price_fetcher.py` | yfinance price lookup with market-open check |
| `scripts/llm_trader.py` | LLM buy/sell decision engine |
| `scripts/trade_engine.py` | Portfolio state management |
| `scripts/daily_report.py` | Daily HTML report generator |
| `scripts/report_generator.py` | HTML rendering library |
| `scripts/upload_report.py` | MinIO upload helper |
| `setup.py` | First-run initializer |
| `data/config.json` | Portfolio configuration (gitignored) |
| `data/portfolios/` | Per-portfolio state files (gitignored) |
| `data/reports/` | Generated HTML reports (gitignored) |

## Portfolio Configuration (`data/config.json`)

Each portfolio object in the `portfolios` array supports these fields:

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | string | Yes | — | Unique identifier for the portfolio |
| `subreddit` | string | Yes | — | Subreddit to scan (without `r/`) |
| `check_interval_minutes` | int | No | `15` | Minimum minutes between scans |
| `starting_balance` | float | Yes | — | Initial cash balance in USD |
| `max_position_pct` | float | No | `0.15` | Max portfolio % per single position |
| `max_single_trade_usd` | float | No | `300.00` | Max USD per single trade |
| `max_trades` | int\|null | No | `null` | Max buy/sell trades per calendar day (null = unlimited). Enforced by `trade_engine.py` and surfaced to the LLM so it prioritizes high-conviction trades when the limit is near. |
| `enabled` | bool | No | `true` | Whether this portfolio is active |

### Example with `max_trades`

```json
{
  "id": "pennystock",
  "subreddit": "Pennystock",
  "check_interval_minutes": 15,
  "starting_balance": 2000.00,
  "max_position_pct": 0.15,
  "max_single_trade_usd": 300.00,
  "max_trades": 3,
  "enabled": true
}
```

With `max_trades: 3`, the engine will execute at most 3 buy/sell trades per day (hold decisions don't count). The LLM is also informed of remaining trades so it can self-select only the highest-conviction setups.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `REDDIT_CLIENT_ID` | Yes | Reddit API app client ID |
| `REDDIT_CLIENT_SECRET` | Yes | Reddit API app client secret |
| `REDDIT_USER_AGENT` | Yes | Reddit API user agent string |
| `MINIO_ENDPOINT` | Yes | MinIO server URL |
| `MINIO_ACCESS_KEY` | Yes | MinIO access key |
| `MINIO_SECRET_KEY` | Yes | MinIO secret key |
| `MINIO_BUCKET` | Yes | Bucket name for reports |
| `PUSHOVER_TOKEN` | Yes | Pushover application token |
| `PUSHOVER_USER` | Yes | Pushover user key |
