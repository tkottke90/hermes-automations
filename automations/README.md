# Automations

This directory contains all Hermes automations — scheduled scripts managed by the Hermes cron system.

## What is an Automation?

An automation is a self-contained directory that groups together:
- An `AUTOMATION.md` metadata file (required)
- A `scripts/` directory containing the executable code
- A `data/` directory for runtime state (gitignored)
- Any supporting config files

Automations are discovered by Hermes via the `~/.hermes/automations` symlink created by `setup.sh`.

---

## AUTOMATION.md Schema

Every automation must have an `AUTOMATION.md` at its root. This file follows the same YAML frontmatter format as Hermes `SKILL.md` files, with one additional field: `schedule`.

### Full Schema

```yaml
---
name: my-automation           # kebab-case, matches directory name
description: "One-line description of what this automation does"
version: 1.0.0                # semver
author: Your Name
license: MIT                  # or UNLICENSED for private automations

# Schedule in cron format (required)
# Examples:
#   "*/15 * * * 1-5"   = every 15 min, Mon-Fri
#   "0 9 * * *"        = daily at 9 AM
#   "5 2 * * 1-5"      = 2:05 AM UTC, Mon-Fri
schedule: "*/15 * * * 1-5"

platforms: [macos, linux]     # platforms this runs on

metadata:
  hermes:
    tags: [tag1, tag2]        # freeform tags for discovery
    scripts:                  # cron entry point scripts (relative to scripts/)
      - name: main            # logical name
        file: cron_entry.py   # filename under scripts/
        no_agent: true        # true = script output delivered verbatim (no LLM)
                              # false = LLM agent runs the script + prompt
        deliver: origin       # delivery target (origin, local, telegram, etc.)
    dependencies:             # pip packages required
      - yfinance
      - requests
    env:                      # required environment variables
      - MINIO_ENDPOINT
      - MINIO_ACCESS_KEY
---

# My Automation

Longer description of the automation's purpose, logic, and behavior.

## Setup

Steps to configure this automation for first use.

## Files

| File | Purpose |
|---|---|
| `scripts/cron_entry.py` | Cron entry point |
| `data/state.json` | Runtime state (gitignored) |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `MINIO_ENDPOINT` | Yes | MinIO server URL |
```

### Required Fields

| Field | Type | Description |
|---|---|---|
| `name` | string | Kebab-case, must match directory name |
| `description` | string | One-line summary |
| `version` | semver | e.g. `1.0.0` |
| `schedule` | cron string | When the automation runs |

### Optional Fields

| Field | Type | Description |
|---|---|---|
| `author` | string | Who maintains this |
| `platforms` | list | `[macos, linux, windows]` |
| `metadata.hermes.tags` | list | Discovery tags |
| `metadata.hermes.scripts` | list | Cron entry point definitions |
| `metadata.hermes.dependencies` | list | pip packages |
| `metadata.hermes.env` | list | Required env var names |

---

## Creating a New Automation

1. Create a directory: `automations/<your-automation-name>/`
2. Add an `AUTOMATION.md` using the schema above
3. Add your scripts under `scripts/`
4. Add a `data/` directory (it will be gitignored automatically)
5. Commit and push
6. Register the cron job in Hermes using the schedule from your `AUTOMATION.md`

### Gitignore

The root `.gitignore` excludes `data/` directories and common runtime artifacts:
- `**/data/` — state files, reports, logs
- `**/__pycache__/`
- `**/*.pyc`
- `**/.env`

If you need to commit seed data files, use `git add -f automations/<name>/data/<file>`.
