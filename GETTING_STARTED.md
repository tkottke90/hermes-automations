# Getting Started with hermes-automations

This guide is written for **Hermes Agent instances** that need to work with this repository — adding automations, registering cron jobs, authoring skills, or maintaining existing workflows.

---

## What Is This Repository?

`~/.hermes-automations` is the **version-controlled source of truth** for all Hermes automations and custom skills. It is wired into Hermes via symlinks so that Hermes can discover automations and skills automatically.

- **Automations** = scheduled cron jobs backed by scripts  
- **Skills** = reusable Hermes procedural memory (SKILL.md files)  
- **lib/** = shared Python utilities available to all automation scripts  

---

## Prerequisites

- Hermes Agent is installed and the `~/.hermes/` directory exists
- `git` is available
- Python 3.9+ is available as `python3` (macOS ships 3.9; use `Optional` not `str | None`)

---

## Initial Setup

Clone the repo to the expected location and run the setup script:

```sh
git clone <repo-url> ~/.hermes-automations
cd ~/.hermes-automations
./setup.sh --dry-run   # preview what will be linked
./setup.sh             # apply symlinks
```

### What `setup.sh` Does

| `~/.hermes` path | → Repo path |
|---|---|
| `~/.hermes/automations` | `~/.hermes-automations/automations` |
| `~/.hermes/skills/custom` | `~/.hermes-automations/skills` |
| `~/.hermes/lib/<file>` | `~/.hermes-automations/lib/<file>` (per-file) |

> **Note:** `~/.hermes/lib/` already existed as a real directory. `setup.sh` symlinks **individual files** rather than replacing the directory. Re-run `./setup.sh` after adding any new file to `lib/`.

To remove symlinks (e.g., before moving the repo):

```sh
./teardown.sh
```

---

## Repository Structure

```
~/.hermes-automations/
├── README.md
├── GETTING_STARTED.md       # ← you are here
├── setup.sh                 # Creates ~/.hermes symlinks
├── teardown.sh              # Removes symlinks
├── .gitignore
├── automations/
│   ├── README.md            # AUTOMATION.md schema reference
│   └── <name>/
│       ├── AUTOMATION.md    # Metadata, schedule, and documentation (required)
│       ├── scripts/         # Executable scripts
│       └── data/            # Runtime state — gitignored
├── skills/                  # Custom Hermes skills (symlinked to ~/.hermes/skills/custom)
└── lib/                     # Shared Python utilities
    ├── pushover.py          # Pushover push notifications
    └── report-publisher.py  # MinIO S3 uploads (AWS SigV4)
```

---

## Current Automations

| Automation | Schedule | Description |
|---|---|---|
| `reddit-portfolio` | `*/15 * * * 1-5` (scan) / `5 2 * * 1-5` (report) | LLM-driven Reddit paper trading tracker |
| `stock-monitor` | `*/15 8-17 * * 1-5` | Stock price threshold & daily summary alerts |
| `server-update-monitor` | `0 9 * * *` | SSH-based Linux server package update checker |
| `log-cleaner` | `0 3 * * *` | Cleans old Hermes cron output logs |
| `hermes-journal` | `0 9,12,15,18,21 * * *` | Appends session summaries to Obsidian daily notes |

---

## Adding a New Automation

### 1. Create the directory scaffold

```sh
mkdir -p ~/.hermes-automations/automations/<name>/{scripts,data}
```

### 2. Write `AUTOMATION.md`

Use this minimal template (see `automations/README.md` for the full schema):

```yaml
---
name: my-automation
description: "One-line description"
version: 1.0.0
author: tkottke
license: UNLICENSED
schedule: "*/15 * * * 1-5"
platforms: [macos, linux]
metadata:
  hermes:
    tags: [example]
    scripts:
      - name: main
        file: cron_entry.py
        no_agent: true      # true = stdout delivered verbatim; false = LLM agent runs it
        deliver: origin
    dependencies: []
    env: []
---

# My Automation

Description of what this automation does, how it works, and how to configure it.
```

### 3. Write scripts

Place your entry script at `scripts/cron_entry.py`. Always support `--dry-run`:

```python
#!/usr/bin/env python3
"""Entry point for the my-automation cron job."""
import sys
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv

# ... your logic here ...

if DRY_RUN:
    print("[DRY RUN] Would have done X")
else:
    print("Did X")
```

### 4. Create the Hermes cron delegator stub

> ⚠️ **Critical constraint:** The Hermes scheduler uses `realpath()` to verify that cron scripts physically reside inside `~/.hermes/scripts/`. Symlinks into `~/.hermes-automations/` are rejected. You must place a **thin delegator stub** in `~/.hermes/scripts/` that calls the real script.

Create `~/.hermes/scripts/<name>_entry.py`:

```python
#!/usr/bin/env python3
"""Thin delegator — forwards to ~/.hermes/automations/<name>/scripts/cron_entry.py"""
import subprocess, sys
from pathlib import Path

script = Path.home() / ".hermes" / "automations" / "<name>" / "scripts" / "cron_entry.py"
if not script.exists():
    print(f"ERROR: Delegated script not found: {script}", file=sys.stderr)
    sys.exit(1)
result = subprocess.run([sys.executable, str(script)] + sys.argv[1:])
sys.exit(result.returncode)
```

Test the stub before registering the cron job:

```sh
python3 ~/.hermes/scripts/<name>_entry.py --dry-run
```

### 5. Register the cron job in Hermes

Use `cronjob(action='create')` with the stub path as the `script` field. Example:

```
schedule: "*/15 * * * 1-5"
script: <name>_entry.py
no_agent: true
```

### 6. Commit

```sh
cd ~/.hermes-automations
git add automations/<name>/
git commit -m "feat(<name>): add automation"
```

---

## Adding a New Skill

1. Create `skills/<name>/SKILL.md` following the [Hermes skill format](https://hermes-agent.nousresearch.com/docs/skills)
2. Once the symlink exists (`~/.hermes/skills/custom` → `skills/`), Hermes discovers the skill automatically — no restart required
3. Commit: `git add skills/<name>/ && git commit -m "feat(skills): add <name>"`

---

## Using Shared lib/ Utilities

Import shared utilities with `sys.path.insert` at the top of any script:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "lib"))

from pushover import send_notification         # push notifications
from report_publisher import publish_report    # MinIO uploads
```

### `pushover.py`

```python
send_notification(
    title="My Alert",
    message="Something happened",
    dry_run=DRY_RUN,
)
```

Reads `PUSHOVER_TOKEN` / `PUSHOVER_USER` from env or `~/.hermes/.env`.

### `report-publisher.py`

```python
success, url = publish_report(Path("/path/to/report.html"), "reports/my-report.html")
```

Reads `MINIO_*` credentials from env or `~/.hermes/.env`.

---

## Config-Driven Automation Pattern

For automations that need per-job config and `last_run` state tracking:

- `data/config.json` — live runtime config (gitignored)  
- `config.example.json` — committed example (no secrets)  
- Write state atomically with `tempfile.mkstemp` + `os.replace` to prevent corruption  

---

## Cron Log Location

Hermes stores cron job output at:

```
~/.hermes/cron/output/<cron_job_id>/YYYY-MM-DD_HH-MM-SS.md
```

Logs are **not** auto-cleaned by Hermes. The `log-cleaner` automation handles periodic cleanup.

---

## Key Pitfalls

### Python 3.9 Compatibility
macOS ships Python 3.9. Do **not** use `str | None` union syntax — use `Optional` from `typing`:

```python
# ❌ Breaks on Python 3.9
def fn(x: str | None = None): ...

# ✅ Works on Python 3.9+
from typing import Optional
def fn(x: Optional[str] = None): ...
```

### Sibling Script Imports
Use `Path(__file__).parent` — never hardcode `~/.hermes/<name>/scripts/`:

```python
# ✅ Always correct, regardless of where the script lives
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from my_module import helper
```

### data/ Is Gitignored
`**/data/` is in `.gitignore`. To commit seed data: `git add -f automations/<name>/data/<file>`.

### macOS Ships bash 3
`declare -A` (associative arrays) is not available. Shell scripts use pipe-separated strings instead — follow the pattern in `setup.sh`.

### Never `rm -rf` Symlink Targets
Always check `[[ -L "$target" ]]` before removing. The setup/teardown scripts already do this — preserve the guard pattern.

---

## Quick Reference

| Task | Command |
|---|---|
| Preview symlinks | `./setup.sh --dry-run` |
| Apply symlinks | `./setup.sh` |
| Remove symlinks | `./teardown.sh` |
| Test a delegator stub | `python3 ~/.hermes/scripts/<name>.py --dry-run` |
| Run an automation script directly | `python3 ~/.hermes/automations/<name>/scripts/<entry>.py --dry-run` |
| Commit a new automation | `git add automations/<name>/ && git commit -m "feat(<name>): add automation"` |
| Add a lib module | Create `lib/<module>.py`, re-run `./setup.sh` |
