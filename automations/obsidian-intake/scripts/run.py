#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
run.py — Obsidian Intake Processor cron entry point.

Usage:
  python3 run.py [--dry-run] [--note PATH]

  --dry-run    Scan and classify; do NOT modify files or call LLM
  --note PATH  Process a single note file (for manual testing)
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

from scanner import find_pending_notes
from note_writer import update_note
from processors import classify_url
import processors.youtube as youtube_processor
import processors.article as article_processor
import processors.reddit as reddit_processor

CONFIG_PATH = SCRIPTS_DIR.parent / "data" / "config.json"

DRY_RUN = "--dry-run" in sys.argv

# Single-note override
SINGLE_NOTE: Optional[Path] = None
if "--note" in sys.argv:
    idx = sys.argv.index("--note")
    if idx + 1 < len(sys.argv):
        SINGLE_NOTE = Path(sys.argv[idx + 1])


PROCESSOR_MAP = {
    "youtube": youtube_processor,
    "article": article_processor,
    "reddit": reddit_processor,
}


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def process_note(note: dict, config: dict) -> dict:
    """
    Classify, process, and update a single note.
    Returns a result dict: {path, status, source_type, error}
    """
    source_url = note["frontmatter"].get(config["sourceKey"], "")
    source_type = classify_url(
        source_url,
        config["sourceKeyMap"],
        config["defaultSourceKey"],
    )
    print(f"  [{source_type.upper()}] {note['path'].name}")
    print(f"    source: {source_url}")

    if DRY_RUN:
        print(f"    [DRY-RUN] would process as {source_type}")
        return {"path": note["path"], "status": "dry-run", "source_type": source_type, "error": None}

    processor = PROCESSOR_MAP.get(source_type)
    if not processor:
        # Unknown type → article fallback
        print(f"  [WARN] No processor for type '{source_type}', falling back to article")
        processor = article_processor

    try:
        result = processor.process(note, config)
    except Exception as e:
        error_msg = str(e)
        print(f"  [ERROR] Processor exception: {error_msg}", file=sys.stderr)
        result = processor.ProcessResult(source_type=source_type, error=error_msg)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if result.error:
        print(f"  [ERROR] {result.error}")
        new_fm = {
            "source_type": result.source_type or source_type,
            "task": "error",
            "intake_error": result.error,
            "last_updated": now_iso,
        }
        update_note(note["path"], new_fm, append_body=None)
        return {"path": note["path"], "status": "error", "source_type": source_type, "error": result.error}

    # Success
    new_fm = {
        "source_type": result.source_type or source_type,
        "task": config["task"]["completedKey"],
        "last_updated": now_iso,
    }
    if result.extra_frontmatter:
        new_fm.update(result.extra_frontmatter)

    update_note(note["path"], new_fm, append_body=result.body)
    print(f"  ✓ Done — task=completed, source_type={result.source_type}")
    return {"path": note["path"], "status": "completed", "source_type": source_type, "error": None}


def main() -> None:
    config = load_config()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    mode = "[DRY-RUN] " if DRY_RUN else ""
    print(f"{mode}obsidian-intake — {now}")

    # Get notes to process
    if SINGLE_NOTE:
        if not SINGLE_NOTE.exists():
            print(f"ERROR: --note file not found: {SINGLE_NOTE}", file=sys.stderr)
            sys.exit(1)
        import frontmatter
        post = frontmatter.load(str(SINGLE_NOTE))
        notes = [{
            "path": SINGLE_NOTE,
            "frontmatter": dict(post.metadata),
            "body": post.content,
        }]
        print(f"Single-note mode: {SINGLE_NOTE.name}")
    else:
        notes = find_pending_notes(
            config["vault_path"],
            config["intake_folder"],
            config["task"]["pendingKey"],
            config["sourceKey"],
        )
        print(f"Found {len(notes)} pending note(s) in Intake\n")

    if not notes:
        print("Nothing to process.")
        sys.exit(0)

    processed = 0
    errors = 0
    skipped = 0

    for note in notes:
        result = process_note(note, config)
        print()
        if result["status"] == "completed":
            processed += 1
        elif result["status"] == "error":
            errors += 1
        else:
            skipped += 1

    print(f"Done. processed={processed} errors={errors} skipped={skipped}")
    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
