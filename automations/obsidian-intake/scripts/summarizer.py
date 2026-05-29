#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
summarizer.py — Generate a 1-sentence summary via hermes -z CLI.
"""

import subprocess
import sys
from pathlib import Path


HERMES_BIN = "hermes"
MAX_INPUT_CHARS = 30_000


def summarize(text: str, context_hint: str = "") -> str:
    """
    Return a 1-sentence summary of the given text.
    Falls back to '[Summary unavailable]' on any error — never raises.
    """
    if not text or not text.strip():
        return "[Summary unavailable — no content provided]"

    # Truncate to avoid huge prompts
    truncated = text[:MAX_INPUT_CHARS]
    if len(text) > MAX_INPUT_CHARS:
        truncated += "\n[... content truncated for summarization ...]"

    context_str = f" The content is a {context_hint}." if context_hint else ""
    prompt = (
        f"Summarize the following content in exactly one concise sentence.{context_str}"
        f" Respond with only the sentence, no preamble or explanation.\n\n"
        f"---\n{truncated}\n---"
    )

    try:
        result = subprocess.run(
            [HERMES_BIN, "-z", prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"  [WARN] hermes -z returned non-zero: {result.stderr[:200]}", file=sys.stderr)
            return "[Summary unavailable]"
        summary = result.stdout.strip()
        return summary if summary else "[Summary unavailable]"
    except FileNotFoundError:
        print("  [WARN] hermes CLI not found, cannot generate summary", file=sys.stderr)
        return "[Summary unavailable — hermes CLI not found]"
    except subprocess.TimeoutExpired:
        print("  [WARN] hermes -z timed out", file=sys.stderr)
        return "[Summary unavailable — timeout]"
    except Exception as e:
        print(f"  [WARN] summarize() error: {e}", file=sys.stderr)
        return "[Summary unavailable]"
