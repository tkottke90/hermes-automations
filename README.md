# hermes-automations

Version-controlled automations and custom skills for the [Hermes Agent](https://hermes-agent.nousresearch.com).

## Structure

```
.
├── automations/          # Scheduled automations (cron jobs, scripts)
│   └── <automation>/
│       ├── AUTOMATION.md   # Metadata, schedule, and documentation
│       ├── scripts/        # Executable scripts for this automation
│       └── data/           # Runtime data, state files (gitignored)
├── skills/               # Custom Hermes skills
│   └── <skill>/
│       ├── SKILL.md        # Skill definition (see Hermes skill format)
│       └── ...
├── lib/                  # Shared Python utilities used across automations
├── setup.sh              # Create ~/.hermes symlinks
├── teardown.sh           # Remove ~/.hermes symlinks
└── README.md
```

## Setup

Clone this repo to `~/.hermes-automations`, then run:

```sh
cd ~/.hermes-automations
./setup.sh
```

This creates two symlinks:
- `~/.hermes/automations` → `~/.hermes-automations/automations`
- `~/.hermes/skills/custom` → `~/.hermes-automations/skills`

To remove the symlinks (e.g., before moving the repo):

```sh
./teardown.sh
```

Both scripts support `--dry-run` to preview what they would do without making changes.

## Automations

| Automation | Schedule | Description |
|---|---|---|
| [reddit-portfolio](automations/reddit-portfolio/AUTOMATION.md) | `*/15 * * * 1-5` (scan) / `5 2 * * 1-5` (report) | LLM-driven Reddit paper trading tracker |
| [stock-monitor](automations/stock-monitor/AUTOMATION.md) | `*/15 8-17 * * 1-5` | Stock price threshold & daily summary alerts |
| [server-update-monitor](automations/server-update-monitor/AUTOMATION.md) | `0 9 * * *` | SSH-based Linux server package update checker |

## Shared Library

Shared Python utilities live in `lib/`. They are symlinked to `~/.hermes/lib/` by `setup.sh`.

| Module | Purpose |
|---|---|
| `report-publisher.py` | MinIO S3 upload with SigV4 auth, dry-run support |

## Adding a New Automation

See [automations/README.md](automations/README.md) for the full guide.

## Adding a New Skill

Create a directory under `skills/<name>/` with a `SKILL.md` file following the [Hermes skill format](https://hermes-agent.nousresearch.com/docs/skills).
After `setup.sh` is run (or the symlink already exists), Hermes will discover the skill automatically.
