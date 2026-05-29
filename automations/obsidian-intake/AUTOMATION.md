---
name: obsidian-intake
description: "Scan Obsidian /Intake folder for notes with task: intake, enrich with content (title, summary, article body, transcript, Reddit comments), and mark as completed."
version: 1.0.0
schedule: "*/30 * * * *"
platforms: [macos]
metadata:
  hermes:
    tags: [obsidian, intake, automation, youtube, articles, reddit]
    scripts:
      - name: main
        file: run.py
        no_agent: true
        deliver: origin
        schedule: "*/30 * * * *"
    dependencies:
      - python-frontmatter
      - trafilatura
      - markdownify
      - youtube-transcript-api
      - requests
      - openai
    env: []
---

# Obsidian Intake Processor

Scans the Obsidian Vault `/Intake` folder every 30 minutes for notes tagged `task: intake`. For each pending note, it:

1. Reads the `source` URL from frontmatter
2. Classifies the URL type (youtube, reddit, article, or `defaultSourceKey` fallback)
3. Extracts relevant content:
   - **YouTube**: Downloads transcript via `download-translation.sh` (or `youtube-transcript-api` fallback), fetches title via oEmbed, generates 1-sentence summary
   - **Article**: Fetches HTML, converts to Markdown via `trafilatura`/`markdownify`, generates summary + saves full article to note
   - **Reddit**: Fetches post + top 3 comments via Reddit JSON API, summarizes each
4. Updates the note with extracted content and frontmatter
5. Sets `task: completed`, `source_type`, and `last_updated`
6. On error: sets `task: error` and `intake_error` — pipeline continues

## Config (`data/config.json`)

See `data/config.example.json` for the full config shape. Key fields:

- `task.pendingKey` — value of `task` field that triggers processing (default: `"intake"`)
- `task.completedKey` — value written on success (default: `"completed"`)
- `sourceKey` — frontmatter key containing the URL (default: `"source"`)
- `sourceKeyMap` — map of content type to list of domain substrings
- `defaultSourceKey` — fallback type when no domain matches (default: `"article"`)
- `processors.youtube.transcriptDownloader` — path to transcript shell script

## Usage

```bash
# Dry run (no files modified)
python3 ~/.hermes-automations/automations/obsidian-intake/scripts/run.py --dry-run

# Process all pending notes
python3 ~/.hermes-automations/automations/obsidian-intake/scripts/run.py

# Process a single note
python3 ~/.hermes-automations/automations/obsidian-intake/scripts/run.py --note "/path/to/note.md"
```

## Trigger a Note

Create a note in `/Intake/` with:
```yaml
---
source: https://www.youtube.com/watch?v=dQw4w9WgXcQ
task: "intake"
---
```

The automation will pick it up on its next run.
