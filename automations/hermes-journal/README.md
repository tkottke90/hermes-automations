# hermes-journal

Automated daily session journaling for Obsidian. Runs five times a day and
appends concise summaries of today's interactive Hermes sessions to the
daily note under `## Developer`.

## How It Works

1. The Hermes agent cron job fires at 9, 12, 15, 18, and 21 every day.
2. It calls `get_journal_state.py` to read the current session counter and
   already-logged session times from the daily note.
3. It calls `session_search` with today's date (`YYYYMMDD`) to find sessions.
4. Sessions from non-interactive sources (`cron`, `telegram`, etc.) are filtered out.
5. Sessions whose start times already appear in `## Developer` are skipped.
6. For each new session, the agent writes a `### Session N - H:MM AM/PM` header
   and a 2–4 sentence summary.
7. The agent appends all new content under `## Developer` and updates
   `next_session_index` in the frontmatter.

## Setup

The helper script is wired via a delegator stub:

```
~/.hermes/scripts/hermes_journal_state.py  →  scripts/get_journal_state.py
```

If you need to re-wire after a fresh clone:
```bash
cd ~/.hermes-automations
./setup.sh
```

## Manual Test

```bash
# Test the helper directly
python3 ~/.hermes-automations/automations/hermes-journal/scripts/get_journal_state.py \
  /Users/thomaskottke/Nextcloud/Documents/Vault_v2/Scheduled/Daily/$(date +%Y%m%d).md \
  --dry-run

# Test via delegator stub
python3 ~/.hermes/scripts/hermes_journal_state.py \
  /Users/thomaskottke/Nextcloud/Documents/Vault_v2/Scheduled/Daily/$(date +%Y%m%d).md \
  --dry-run
```

## Deduplication

Sessions are deduplicated by matching the `started_at` timestamp (formatted
as `H:MM AM/PM`) against existing `### Session N - ` headers in the file.

If a run produces a duplicate (e.g. the frontmatter patch failed), re-running
is safe — the time-based check will skip already-logged sessions.

## Frontmatter

The automation adds one property to the daily note frontmatter:

```yaml
next_session_index: 4   # increments each time a new session is logged
```

This resets naturally each day because each daily note starts fresh.
