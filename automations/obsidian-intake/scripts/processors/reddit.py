#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
processors/reddit.py — Extract Reddit post + top 3 comments via PRAW.

Requires Reddit app credentials in ~/.hermes/.env:
  REDDIT_APP_ID=your_client_id
  REDDIT_APP_SECRET=your_client_secret

Create a free "script" type app at: https://www.reddit.com/prefs/apps
Redirect URL (required by form, never used): http://localhost:8080
"""

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ProcessResult:
    source_type: str = ""
    title: Optional[str] = None
    summary: Optional[str] = None
    body: Optional[str] = None
    extra_frontmatter: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


def _load_env() -> None:
    """Load ~/.hermes/.env if REDDIT_APP_ID not already in environment."""
    if os.environ.get("REDDIT_APP_ID"):
        return
    env_path = Path.home() / ".hermes" / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key not in os.environ:
                os.environ[key] = val


def _resolve_share_link(url: str) -> str:
    """
    Follow Reddit share links (/s/<token>) to the canonical post URL.
    Returns the resolved URL, or the original on failure.
    """
    if "/s/" not in url:
        return url
    try:
        import requests
        resp = requests.get(
            url,
            headers={"User-Agent": "obsidian-intake/1.0"},
            timeout=10,
            allow_redirects=True,
        )
        resolved = str(resp.url).split("?")[0].split("#")[0].rstrip("/")
        print(f"  [INFO] Resolved share link → {resolved}", file=sys.stderr)
        return resolved
    except Exception as e:
        print(f"  [WARN] Could not resolve share link {url}: {e}", file=sys.stderr)
        return url


def _extract_post_id(url: str) -> Optional[str]:
    """Extract Reddit post ID from a canonical post URL."""
    match = re.search(r"/comments/([a-z0-9]+)", url, re.IGNORECASE)
    return match.group(1) if match else None


def _get_praw_instance():
    """Create a read-only PRAW Reddit instance using app credentials."""
    _load_env()
    client_id = os.environ.get("REDDIT_APP_ID")
    client_secret = os.environ.get("REDDIT_APP_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError(
            "Reddit credentials missing. Add REDDIT_APP_ID and REDDIT_APP_SECRET "
            "to ~/.hermes/.env — create a free 'script' app at "
            "https://www.reddit.com/prefs/apps (redirect URL: http://localhost:8080)"
        )

    import praw
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent="obsidian-intake/1.0 (Hermes automation; read-only)",
    )


def process(note: dict, config: dict) -> ProcessResult:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from summarizer import summarize

    url = note["frontmatter"].get(config["sourceKey"], "")

    # Resolve share links before anything else
    url = _resolve_share_link(url)

    post_id = _extract_post_id(url)
    if not post_id:
        return ProcessResult(
            source_type="reddit",
            error=f"Could not extract post ID from URL: {url}",
        )

    try:
        reddit = _get_praw_instance()
        submission = reddit.submission(id=post_id)
        # Trigger lazy load by accessing an attribute
        title = submission.title
        selftext = submission.selftext.strip()
        author = str(submission.author) if submission.author else "[deleted]"
        score = submission.score
        subreddit = f"r/{submission.subreddit.display_name}"
    except RuntimeError as e:
        return ProcessResult(source_type="reddit", error=str(e))
    except Exception as e:
        return ProcessResult(source_type="reddit", error=f"PRAW fetch failed: {e}")

    # Post summary
    post_summary = summarize(selftext if selftext else title, context_hint="Reddit post")

    # Top 3 comments by score
    comment_blocks: List[str] = []
    try:
        submission.comments.replace_more(limit=0)
        top_comments = sorted(
            [c for c in submission.comments.list() if hasattr(c, "body") and c.body],
            key=lambda c: c.score,
            reverse=True,
        )[:3]
        for i, c in enumerate(top_comments, 1):
            c_author = str(c.author) if c.author else "[deleted]"
            c_summary = summarize(c.body, context_hint="Reddit comment")
            comment_blocks.append(f"{i}. **u/{c_author}** (↑{c.score}): {c_summary}")
    except Exception as e:
        print(f"  [WARN] Comment fetch failed: {e}", file=sys.stderr)

    # Build note body
    parts = [f"# {title}\n"]
    parts.append(f"*Posted by u/{author} in {subreddit} · ↑{score}*\n")
    parts.append(f"**Summary:** {post_summary}\n")

    if selftext:
        parts.append("## Post Content\n")
        parts.append(selftext[:10_000])
        if len(selftext) > 10_000:
            parts.append("\n\n*[Post content truncated]*")
        parts.append("")

    if comment_blocks:
        parts.append("## Top Comments\n")
        parts.extend(comment_blocks)

    return ProcessResult(
        source_type="reddit",
        title=title,
        summary=post_summary,
        body="\n".join(parts),
        extra_frontmatter={},
    )
