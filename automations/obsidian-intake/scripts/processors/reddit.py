#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
processors/reddit.py — Extract Reddit post + top 3 comments via the public JSON API.

No credentials required. Uses the public /<post_url>.json endpoint.

Share links (reddit.com/r/<sub>/s/<token>) are automatically resolved to canonical
post URLs (reddit.com/r/<sub>/comments/<id>/<slug>) before fetching.
"""

import json
import re
import sys
import urllib.request
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


_HEADERS = {
    "User-Agent": "obsidian-intake/1.0",
    "Accept": "application/json",
}

_SHARE_LINK_RE = re.compile(r"reddit\.com/r/[^/]+/s/", re.IGNORECASE)


def _resolve_share_link(url: str) -> str:
    """
    Detect Reddit share links (r/<sub>/s/<token>) and follow the redirect to
    get the canonical post URL (r/<sub>/comments/<id>/<slug>).
    Returns the resolved URL, or the original on failure.
    """
    if not _SHARE_LINK_RE.search(url):
        return url

    print(f"  [INFO] Detected share link, resolving: {url}", file=sys.stderr)
    try:
        import requests
        resp = requests.get(url, headers=_HEADERS, timeout=10, allow_redirects=True)
        # Strip query params / fragments — we only want the clean post URL
        resolved = str(resp.url).split("?")[0].split("#")[0].rstrip("/")
        print(f"  [INFO] Resolved → {resolved}", file=sys.stderr)
        return resolved
    except Exception as e:
        print(f"  [WARN] Share link resolution failed: {e}", file=sys.stderr)
        return url


def _to_json_url(url: str) -> str:
    """Append .json to a canonical Reddit post URL."""
    url = url.split("?")[0].split("#")[0].rstrip("/")
    if not url.endswith(".json"):
        url += ".json"
    return url


def _fetch(url: str) -> Optional[list]:
    """Fetch and parse the Reddit post JSON."""
    json_url = _to_json_url(url)
    try:
        req = urllib.request.Request(json_url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  [WARN] Reddit JSON fetch failed for {json_url}: {e}", file=sys.stderr)
        return None


def _extract_post(data: list) -> Optional[dict]:
    try:
        return data[0]["data"]["children"][0]["data"]
    except (IndexError, KeyError, TypeError):
        return None


def _extract_top_comments(data: list, top_n: int = 3) -> List[dict]:
    try:
        children = data[1]["data"]["children"]
        comments = [
            {
                "author": c["data"].get("author", "[deleted]"),
                "score": c["data"].get("score", 0),
                "body": c["data"].get("body", ""),
            }
            for c in children
            if c.get("kind") == "t1" and c.get("data", {}).get("body")
        ]
        return sorted(comments, key=lambda c: c["score"], reverse=True)[:top_n]
    except Exception as e:
        print(f"  [WARN] Comment extraction failed: {e}", file=sys.stderr)
        return []


def process(note: dict, config: dict) -> ProcessResult:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from summarizer import summarize

    url = note["frontmatter"].get(config["sourceKey"], "")

    # Self-heal share links before anything else
    url = _resolve_share_link(url)

    data = _fetch(url)
    if not data:
        return ProcessResult(
            source_type="reddit",
            error=f"Could not fetch Reddit JSON for: {url}",
        )

    post = _extract_post(data)
    if not post:
        return ProcessResult(source_type="reddit", error="Could not parse Reddit JSON response")

    title = post.get("title", "")
    selftext = post.get("selftext", "").strip()
    author = post.get("author", "[deleted]")
    score = post.get("score", 0)
    subreddit = f"r/{post.get('subreddit', '')}"

    post_summary = summarize(selftext if selftext else title, context_hint="Reddit post")

    comments = _extract_top_comments(data)
    comment_blocks: List[str] = []
    for i, c in enumerate(comments, 1):
        c_summary = summarize(c["body"], context_hint="Reddit comment") if c["body"] else "[no content]"
        comment_blocks.append(f"{i}. **u/{c['author']}** (↑{c['score']}): {c_summary}")

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
