#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
processors/reddit.py — Extract Reddit post + top 3 comments via Reddit JSON API.

No credentials required. Uses the public /<post_url>.json endpoint with a
browser-style User-Agent.
"""

import json
import sys
import re
import urllib.request
import urllib.parse
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


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


def _to_json_url(url: str) -> str:
    """Convert a Reddit post URL to its /.json endpoint."""
    url = url.split("?")[0].split("#")[0].rstrip("/")
    url = re.sub(r"^https?://(old\.|new\.)?reddit\.com", "https://www.reddit.com", url)
    if not url.endswith(".json"):
        url += ".json"
    return url


def _fetch(url: str) -> Optional[list]:
    """Fetch Reddit JSON data, trying with and without cookies."""
    json_url = _to_json_url(url)
    params = "?raw_json=1&limit=10"

    # Attempt 1: try requests (better TLS/cookie handling)
    try:
        import requests
        s = requests.Session()
        s.headers.update(_HEADERS)
        # Brief homepage visit to pick up consent cookie (avoids GDPR redirect)
        try:
            s.get("https://www.reddit.com", timeout=8, allow_redirects=True)
        except Exception:
            pass
        resp = s.get(json_url + params, timeout=15, allow_redirects=True)
        if resp.status_code == 200:
            return resp.json()
        print(f"  [WARN] Reddit JSON API returned {resp.status_code} (requests)", file=sys.stderr)
    except ImportError:
        pass
    except Exception as e:
        print(f"  [WARN] Reddit fetch (requests) failed: {e}", file=sys.stderr)

    # Attempt 2: urllib fallback
    try:
        req = urllib.request.Request(json_url + params, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  [WARN] Reddit fetch (urllib) failed: {e}", file=sys.stderr)
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
    data = _fetch(url)

    if not data:
        return ProcessResult(
            source_type="reddit",
            error=(
                "Could not fetch Reddit post via JSON API. "
                "Reddit may be blocking requests from this environment."
            ),
        )

    post = _extract_post(data)
    if not post:
        return ProcessResult(source_type="reddit", error="Could not parse Reddit JSON response")

    title = post.get("title", "")
    selftext = post.get("selftext", "").strip()
    author = post.get("author", "[deleted]")
    score = post.get("score", 0)
    subreddit = f"r/{post.get('subreddit', '')}"

    # Post summary
    post_summary = summarize(selftext if selftext else title, context_hint="Reddit post")

    # Top comments
    comments = _extract_top_comments(data)
    comment_blocks = []
    for i, c in enumerate(comments, 1):
        c_summary = summarize(c["body"], context_hint="Reddit comment") if c["body"] else "[no content]"
        comment_blocks.append(f"{i}. **u/{c['author']}** (↑{c['score']}): {c_summary}")

    # Build body
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
