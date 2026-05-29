#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
processors/article.py — Fetch article as markdown, generate 1-sentence summary.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any


@dataclass
class ProcessResult:
    source_type: str = ""
    title: Optional[str] = None
    summary: Optional[str] = None
    body: Optional[str] = None
    extra_frontmatter: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


MAX_BODY_CHARS = 50_000


def _fetch_html(url: str) -> Optional[tuple]:
    """Returns (html_str, final_url) or None on failure."""
    try:
        import requests
        resp = requests.get(url, timeout=15, headers={"User-Agent": "obsidian-intake/1.0"}, allow_redirects=True)
        resp.raise_for_status()
        return resp.text, str(resp.url)
    except Exception as e:
        print(f"  [WARN] requests fetch failed: {e}", file=sys.stderr)
        return None


def _html_to_markdown_trafilatura(html: str, url: str) -> tuple:
    """Returns (title, markdown) via trafilatura."""
    try:
        import trafilatura
        metadata = trafilatura.extract_metadata(html, default_url=url)
        md = trafilatura.extract(html, output_format="markdown", include_links=False)
        title = metadata.title if metadata else None
        return title, md
    except Exception as e:
        print(f"  [WARN] trafilatura failed: {e}", file=sys.stderr)
        return None, None


def _html_to_markdown_markdownify(html: str) -> tuple:
    """Returns (title, markdown) via markdownify + BeautifulSoup for title."""
    try:
        from markdownify import markdownify
        from html.parser import HTMLParser

        class TitleParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self._in_title = False
                self.title = None
            def handle_starttag(self, tag, attrs):
                if tag.lower() == "title":
                    self._in_title = True
            def handle_endtag(self, tag):
                if tag.lower() == "title":
                    self._in_title = False
            def handle_data(self, data):
                if self._in_title and not self.title:
                    self.title = data.strip()

        tp = TitleParser()
        tp.feed(html)
        md = markdownify(html, heading_style="ATX", strip=["script", "style"])
        return tp.title, md
    except Exception as e:
        print(f"  [WARN] markdownify failed: {e}", file=sys.stderr)
        return None, None


def process(note: dict, config: dict) -> ProcessResult:
    """Process an article note: fetch as markdown, generate summary."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from summarizer import summarize

    url = note["frontmatter"].get(config["sourceKey"], "")

    fetched = _fetch_html(url)
    if not fetched:
        return ProcessResult(
            source_type="article",
            error="Could not fetch article content",
        )

    html, final_url = fetched

    # Try trafilatura first, fall back to markdownify
    title, markdown = _html_to_markdown_trafilatura(html, final_url)
    if not markdown:
        title, markdown = _html_to_markdown_markdownify(html)

    if not markdown or not markdown.strip():
        return ProcessResult(
            source_type="article",
            title=title,
            error="Could not extract article content",
        )

    # Truncate body
    body_md = markdown[:MAX_BODY_CHARS]
    if len(markdown) > MAX_BODY_CHARS:
        body_md += "\n\n*[Content truncated — see original source for full article]*"

    # Summary
    summary = summarize(body_md, context_hint="web article")

    # Build appended body
    body_parts = []
    if title:
        body_parts.append(f"# {title}\n")
    if summary:
        body_parts.append(f"**Summary:** {summary}\n")
    body_parts.append("## Article Content\n")
    body_parts.append(body_md)

    return ProcessResult(
        source_type="article",
        title=title,
        summary=summary,
        body="\n".join(body_parts),
        extra_frontmatter={},
    )
