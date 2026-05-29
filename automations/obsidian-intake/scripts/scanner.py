#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
scanner.py — Find pending intake notes in the Obsidian vault.
"""

from pathlib import Path
from typing import List, Dict, Any

import frontmatter


def find_pending_notes(
    vault_path: str,
    intake_folder: str,
    pending_key: str,
    source_key: str,
) -> List[Dict[str, Any]]:
    """
    Scan the intake folder for notes with task == pending_key and a source URL.

    Returns a list of dicts:
      {
        "path": Path,
        "frontmatter": dict,
        "body": str,
      }
    """
    intake_dir = Path(vault_path) / intake_folder
    if not intake_dir.exists():
        print(f"  [WARN] Intake folder not found: {intake_dir}")
        return []

    results = []
    for md_file in sorted(intake_dir.glob("*.md")):
        try:
            post = frontmatter.load(str(md_file))
        except Exception as e:
            print(f"  [WARN] Could not parse frontmatter in {md_file.name}: {e}")
            continue

        task_val = post.metadata.get("task", "")
        # Normalize: strip quotes, compare case-insensitively
        if isinstance(task_val, str):
            task_val = task_val.strip().strip('"').strip("'")
        else:
            task_val = str(task_val)

        source_val = post.metadata.get(source_key, "")
        if not isinstance(source_val, str):
            source_val = str(source_val) if source_val else ""
        source_val = source_val.strip()

        if task_val.lower() == pending_key.lower() and source_val:
            results.append({
                "path": md_file,
                "frontmatter": dict(post.metadata),
                "body": post.content,
            })

    return results


if __name__ == "__main__":
    import json
    from pathlib import Path

    config_path = Path(__file__).parent.parent / "data" / "config.json"
    with open(config_path) as f:
        config = json.load(f)

    notes = find_pending_notes(
        config["vault_path"],
        config["intake_folder"],
        config["task"]["pendingKey"],
        config["sourceKey"],
    )
    print(f"Found {len(notes)} pending note(s):")
    for n in notes:
        print(f"  {n['path'].name}  source={n['frontmatter'].get('source', '')}")
