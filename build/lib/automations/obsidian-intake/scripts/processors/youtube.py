#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
processors/youtube.py — Extract YouTube title + transcript, generate 1-sentence summary.
"""

import subprocess
import sys
import json
import urllib.request
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


def _get_title_oembed(url: str) -> Optional[str]:
    """Fetch video title via YouTube oEmbed API (no auth needed)."""
    try:
        import urllib.parse
        api = f"https://www.youtube.com/oembed?url={urllib.parse.quote(url)}&format=json"
        req = urllib.request.Request(api, headers={"User-Agent": "obsidian-intake/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("title")
    except Exception as e:
        print(f"  [WARN] oEmbed title fetch failed: {e}", file=sys.stderr)
        return None


def _get_transcript_via_script(url: str, script_path: str) -> Optional[str]:
    """Run the user's download-translation.sh script and capture transcript text."""
    try:
        result = subprocess.run(
            [script_path, url],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        if result.returncode != 0:
            print(f"  [WARN] transcript script exited {result.returncode}: {result.stderr[:200]}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("  [WARN] transcript script timed out", file=sys.stderr)
    except Exception as e:
        print(f"  [WARN] transcript script error: {e}", file=sys.stderr)
    return None


def _get_transcript_via_api(url: str) -> Optional[str]:
    """Fallback: use youtube-transcript-api Python package."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        video_id = None

        if "v" in qs:
            video_id = qs["v"][0]
        elif parsed.hostname in ("youtu.be",):
            video_id = parsed.path.lstrip("/")

        if not video_id:
            print(f"  [WARN] Could not extract video ID from URL: {url}", file=sys.stderr)
            return None

        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
        return " ".join(chunk["text"] for chunk in transcript_list)
    except Exception as e:
        print(f"  [WARN] youtube-transcript-api failed: {e}", file=sys.stderr)
        return None


def process(note: dict, config: dict) -> ProcessResult:
    """Process a YouTube note: fetch title + transcript, generate summary."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from summarizer import summarize

    url = note["frontmatter"].get(config["sourceKey"], "")
    youtube_cfg = config.get("processors", {}).get("youtube", {})
    script_path = youtube_cfg.get(
        "transcriptDownloader",
        "/Users/thomaskottke/Nextcloud/Documents/Vault_v2/bin/download-translation.sh",
    )

    # --- Title ---
    title = _get_title_oembed(url)

    # --- Transcript ---
    transcript = None
    if Path(script_path).exists():
        transcript = _get_transcript_via_script(url, script_path)
    else:
        print(f"  [WARN] transcriptDownloader not found at {script_path}, using API fallback", file=sys.stderr)

    if not transcript:
        transcript = _get_transcript_via_api(url)

    if not transcript:
        return ProcessResult(
            source_type="youtube",
            title=title,
            error="Could not retrieve transcript",
            extra_frontmatter={},
        )

    # --- Summary ---
    summary = summarize(transcript, context_hint="YouTube video transcript")

    # Build body
    body_parts = []
    if title:
        body_parts.append(f"# {title}\n")
    if summary:
        body_parts.append(f"**Summary:** {summary}\n")

    return ProcessResult(
        source_type="youtube",
        title=title,
        summary=summary,
        body="\n".join(body_parts) if body_parts else None,
        extra_frontmatter={},
    )
