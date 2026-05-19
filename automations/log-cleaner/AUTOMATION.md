---
name: log-cleaner
description: "Purge expired Hermes cron job log files based on per-job or global expiration config."
version: 1.0.0
author: tkottke
license: UNLICENSED
schedule: "0 3 * * *"
platforms: [macos, linux]
metadata:
  hermes:
    tags: [maintenance, logs, cleanup, cron]
    scripts:
      - name: main
        file: clean_logs.py
        no_agent: true
        deliver: origin
        schedule: "0 3 * * *"
    dependencies: []
    env: []
---

# log-cleaner

Periodically deletes expired Hermes cron job log (`.md`) files from
`~/.hermes/cron/output/`. Expiration is configurable globally and per-job
via `data/config.json`.

## How It Works

1. Reads `data/config.json` to get the base log directory, default expiration,
   and per-job configuration.
2. For each job entry, resolves the log subdirectory
   (`<log_dir>/<log_dir_field ?? cron_job_id>`).
3. Scans all `.md` files and deletes any whose modification time is older than
   the job's expiration threshold.
4. Updates each job's `last_run` timestamp and writes `config.json` back
   atomically.
5. Prints a one-line summary per job to stdout (delivered verbatim by the
   Hermes cron system).

## Files

| File | Purpose |
|---|---|
| `scripts/clean_logs.py` | Main cleanup script |
| `data/config.json` | Live runtime config (gitignored) |
| `config.example.json` | Committed example config |

## Setup

See `README.md` for full configuration instructions.
