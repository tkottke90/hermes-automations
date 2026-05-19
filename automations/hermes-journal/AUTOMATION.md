---
name: hermes-journal
description: "Daily Obsidian journaling automation — summarizes today's interactive Hermes sessions and appends them to the daily note under ## Developer."
version: 1.0.0
schedule: "0 9,12,15,18,21 * * *"
platforms: [macos]
metadata:
  hermes:
    tags: [journal, obsidian, sessions, daily-note]
    scripts:
      - name: get_journal_state
        file: scripts/get_journal_state.py
        no_agent: true
        description: "Helper — reads daily note state, returns JSON with next_session_index and logged_times"
    cron_jobs:
      - id: TBD
        schedule: "0 9,12,15,18,21 * * *"
        mode: agent
        description: "Main journal writer — runs 5x daily"
    dependencies: []
    env: []
---

# hermes-journal

Reads today's interactive Hermes sessions (source: `tui` or `cli`) via
`session_search`, filters out sessions already logged, and appends concise
2–4 sentence summaries to the daily Obsidian note under `## Developer`.

Runs at 9 AM, 12 PM, 3 PM, 6 PM, and 9 PM every day.

## State Management

Session counter state is stored directly in the daily note's YAML frontmatter:

```yaml
next_session_index: 4
```

Deduplication is time-based: the helper script parses existing
`### Session N - H:MM AM/PM` headers from the `## Developer` section
and returns those times as `logged_times`. The agent skips any session
whose `started_at` matches a logged time.

## Helper Script

`scripts/get_journal_state.py` — reads the daily note and returns:

```json
{
  "exists": true,
  "next_session_index": 3,
  "logged_times": ["9:00 AM", "11:30 AM"]
}
```

Called via `terminal` from inside the agent cron prompt using the
delegator stub at `~/.hermes/scripts/hermes_journal_state.py`.

## Output Format

```markdown
## Developer

### Session 1 - 9:15 AM

Worked on the hermes-journal automation, building a scheduled cron job
that summarises daily Hermes sessions into the Obsidian daily note...
```
