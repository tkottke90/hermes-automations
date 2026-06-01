#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
note_writer.py — Atomically update frontmatter and append body content to a note.
"""

import os
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

import frontmatter
import yaml


def update_note(
    path: Path,
    new_frontmatter: Dict[str, Any],
    append_body: Optional[str] = None,
) -> None:
    """
    Merge new_frontmatter into the note's existing frontmatter.
    If append_body is provided, append it after existing body content.
    Writes atomically using tempfile + os.replace.
    """
    post = frontmatter.load(str(path))

    # Merge new frontmatter (new values win)
    for key, value in new_frontmatter.items():
        post.metadata[key] = value

    # Build body
    body = post.content
    if append_body:
        if body.strip():
            body = body.rstrip() + "\n\n" + append_body.strip()
        else:
            body = append_body.strip()

    post.content = body

    # Serialize
    output = frontmatter.dumps(post)

    # Atomic write
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, prefix=".intake_tmp_", suffix=".md"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(output)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
