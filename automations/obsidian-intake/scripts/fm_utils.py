"""
fm_utils.py — Minimal YAML frontmatter parser using stdlib only.

Provides a drop-in subset of the python-frontmatter API:
  load(path)        -> Post
  loads(text)       -> Post
  dumps(post)       -> str

Obsidian frontmatter format:
  ---
  key: value
  ---
  body content...
"""

import re
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict


_FENCE_RE = re.compile(r"^---\s*\n(.*?\n)---\s*\n?", re.DOTALL)


@dataclass
class Post:
    metadata: Dict[str, Any] = field(default_factory=dict)
    content: str = ""


def loads(text: str) -> Post:
    """Parse a markdown string with optional YAML frontmatter."""
    m = _FENCE_RE.match(text)
    if m:
        yaml_text = m.group(1)
        body = text[m.end():]
        try:
            meta = yaml.safe_load(yaml_text) or {}
            if not isinstance(meta, dict):
                meta = {}
        except yaml.YAMLError:
            meta = {}
        return Post(metadata=meta, content=body)
    return Post(metadata={}, content=text)


def load(path: str) -> Post:
    """Load a markdown file and parse its YAML frontmatter."""
    text = Path(path).read_text(encoding="utf-8")
    return loads(text)


def dumps(post: Post) -> str:
    """Serialize a Post back to a markdown string with YAML frontmatter."""
    if post.metadata:
        yaml_text = yaml.dump(
            post.metadata,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        return f"---\n{yaml_text}---\n\n{post.content}"
    return post.content
