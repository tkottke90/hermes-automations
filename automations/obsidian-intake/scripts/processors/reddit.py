#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
processors/reddit.py — Extract Reddit post + top 3 comments, generate summaries.

Requires Reddit API credentials in ~/.hermes/.env:
  REDDIT_CLIENT_ID=your_client_id
  REDDIT_CLIENT_SECRET=your_client_secret

Create a Reddit app at: https://www.reddit.com/prefs/apps (script type)
"""

import os
import sys
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List


@dataclass
class ProcessResult:
    source_type: str = ""
    title: Optional[str] = None
    summary: Optional[str] = None
    body: Optional[str] = None
    extra_frontmatter: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


def _load_env() -> None:
    """Load ~/.hermes/.env if REDDIT_CLIENT_ID not already in environment."""
    if os.environ.get("REDDIT_CLIENT_ID"):
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


def _extract_post_id(url: str) -> Optional[str]:
    """Extract Reddit post ID from URL."""
    # Pattern: /comments/<post_id>/
    match = re.search(r'/comments/([a-z0-9]+)', url, re.IGNORECASE)
    return match.group(1) if match else None


def _get_praw_instance():
    """Create authenticated PRAW Reddit instance."""
    _load_env()
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError(
            "Reddit credentials not found. Add REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET "
            "to ~/.hermes/.env. Create a Reddit app at https://www.reddit.com/prefs/apps"
        )

    import praw
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent="obsidian-intake/1.0 (by Hermes automation)",
    )


def process(note: dict, config: dict) -> ProcessResult:
    """Process a Reddit note: fetch post + top comments, summarize."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from summarizer import summarize

    url = note["frontmatter"].get(config["sourceKey"], "")

    post_id = _extract_post_id(url)
    if not post_id:
        return ProcessResult(
            source_type="reddit",
            error=f"Could not extract post ID from URL: {url}",
        )

    try:
        reddit = _get_praw_instance()
        submission = reddit.submission(id=post_id)
        # Force lazy load
        title = submission.title
        selftext = submission.selftext.strip()
        author = str(submission.author) if submission.author else "[deleted]"
        score = submission.score
        subreddit = f"r/{submission.subreddit.display_name}"
    except RuntimeError as e:
        return ProcessResult(source_type="reddit", error=str(e))
    except Exception as e:
        return ProcessResult(
            source_type="reddit",
            error=f"PRAW fetch failed: {e}",
        )

    # Post summary
    summarize_text = selftext if selftext else title
    post_summary = summarize(summarize_text, context_hint="Reddit post")

    # Top 3 comments by score
    comment_blocks = []
    try:
        submission.comments.replace_more(limit=0)
        top_comments = sorted(
            [c for c in submission.comments.list() if hasattr(c, 'body')],
            key=lambda c: c.score,
            reverse=True,
        )[:3]

        for i, c in enumerate(top_comments, 1):
            c_author = str(c.author) if c.author else "[deleted]"
            c_summary = summarize(c.body, context_hint="Reddit comment") if c.body else "[no content]"
            comment_blocks.append(f"{i}. **u/{c_author}** (↑{c.score}): {c_summary}")
    except Exception as e:
        print(f"  [WARN] Comment fetch failed: {e}", file=sys.stderr)

    # Build note body
    body_parts = [f"# {title}\n"]
    body_parts.append(f"*Posted by u/{author} in {subreddit} · ↑{score}*\n")
    body_parts.append(f"**Summary:** {post_summary}\n")

    if selftext:
        body_parts.append("## Post Content\n")
        body_parts.append(selftext[:10_000])
        if len(selftext) > 10_000:
            body_parts.append("\n\n*[Post content truncated]*")
        body_parts.append("")

    if comment_blocks:
        body_parts.append("## Top Comments\n")
        body_parts.extend(comment_blocks)

    return ProcessResult(
        source_type="reddit",
        title=title,
        summary=post_summary,
        body="\n".join(body_parts),
        extra_frontmatter={},
    )
