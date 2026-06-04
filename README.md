# hermes-automations

Version-controlled automations and custom skills for the [Hermes Agent](https://hermes-agent.nousresearch.com).

## Structure

```
.
├── automations/          # Scheduled automations (cron jobs, scripts)
│   ├── <automation>/
│   │   ├── AUTOMATION.md   # Metadata, schedule, and documentation
│   │   ├── scripts/        # Executable scripts for this automation
│   │   └── data/           # Runtime data, state files (gitignored)
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

This creates three symlinks:
- `~/.hermes/automations` → `~/.hermes-automations/automations`
- `~/.hermes/skills/custom` → `~/.hermes-automations/skills`
- `~/.hermes/lib` → `~/.hermes-automations/lib`

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
| [gmail-labeler](automations/gmail-labeler/AUTOMATION.md) | `0 * * * *` (hourly) | Gmail email classification with OCR + LLM |
| [log-cleaner](automations/log-cleaner/AUTOMATION.md) | `0 3 * * *` | Expired Hermes cron job log cleanup |
| [obsidian-intake](automations/obsidian-intake/AUTOMATION.md) | `*/30 * * * *` | Process incoming articles/videos into Obsidian |
| [hermes-journal](automations/hermes-journal/AUTOMATION.md) | `0 9,12,15,18,21 * * *` | Daily session summary to Obsidian journal |

### Dependencies & Environment Variables

| Automation | Python Packages | Env Vars (required) |
|---|---|---|
| **reddit-portfolio** | yfinance, requests, praw | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, `PUSHOVER_TOKEN`, `PUSHOVER_USER` |
| **stock-monitor** | yfinance | `PUSHOVER_TOKEN`, `PUSHOVER_USER`, `MINIO_ENDPOINT` (report only), `MINIO_ACCESS_KEY` (report only), `MINIO_SECRET_KEY` (report only), `MINIO_BUCKET` (report only) |
| **server-update-monitor** | (none) | SSH key at `~/.ssh/hermes-agent` |
| **gmail-labeler** | google-api-python-client, google-auth-httplib2, google-auth-oauthlib, weasyprint, pdf2image, pytesseract | `AUTOMATIONS_GMAIL_JSON_KEY` |
| **log-cleaner** | (none) | (none) |
| **obsidian-intake** | python-frontmatter, trafilatura, markdownify, youtube-transcript-api, requests, openai | (none) |
| **hermes-journal** | (none) | (none) |

*All automations use shared library utilities from `~/.hermes/lib/` for Pushover notifications and MinIO uploads.*

## Shared Library

Shared Python utilities live in `lib/`. They are symlinked to `~/.hermes/lib/` by `setup.sh`.

| Module | Purpose |
|---|---|
| `pushover.py` | Pushover notification utility with dry-run support; credentials sourced from env vars or `~/.hermes/.env` |
| `report-publisher.py` | MinIO S3 upload utility with AWS SigV4 auth; supports `--dry-run` mode |

## Skills

| Skill | Category | Description |
|---|---|---|
| [llm-wiki](skills/llm-wiki/SKILL.md) | research | Karpathy's LLM Wiki: build/query interlinked markdown KB with routing, indexing, and query support |

## Adding a New Automation

See [automations/README.md](automations/README.md) for the full guide.

## Adding a New Skill

Create a directory under `skills/<name>/` with a `SKILL.md` file following the [Hermes skill format](https://hermes-agent.nousresearch.com/docs/skills).
After `setup.sh` is run (or the symlink already exists), Hermes will discover the skill automatically.

## Documentation

Each automation includes detailed documentation in its `AUTOMATION.md` file, covering:
- Architecture and file structure
- Setup and configuration steps
- CLI usage examples
- Environment variable requirements

## Maintenance Notes

- Cron job scripts must physically reside in `~/.hermes/scripts/` — symlinks into this repo will fail due to Hermes's use of `realpath()`.
- **Workaround**: place a thin delegator stub in `~/.hermes/scripts/` that subprocess-calls the real script in this repo.
- The canonical source for automation scripts is `~/.hermes-automations/automations/<name>/scripts/`.
- The automation repo is symlinked to `~/.hermes-automations/` for compatibility with Hermes's directory structure requirements.