#!/Users/thomaskottke/.hermes-automations/.venv/bin/python3
"""
classifier.py — Rule engine + Hermes LLM interest bridge.

Classification order per label:
  1. Check sender domain against `domains` list
  2. Check OCR text against `keywords` list (case-insensitive)
  3. If `interest` list is non-empty, call Hermes LLM for semantic check
  4. Apply `xkeywords` disqualification (checked last — overrides everything)

A label is applied only if at least one positive signal fired AND no xkeyword matched.

classify_email() returns Dict[str, str]: label_name → human-readable justification string.
"""

import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple


def _extract_domain(sender: str) -> str:
    """Extract the domain from a sender string like 'Name <user@domain.com>'."""
    match = re.search(r"@([\w.\-]+)", sender)
    return match.group(1).lower() if match else ""


def _keywords_match(text: str, keywords: List[str]) -> bool:
    """Return True if any keyword appears in text (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _check_interest_llm(
    text: str,
    interests: List[str],
    label_name: str,
    verbose: bool = False,
) -> Tuple[bool, Optional[str]]:
    """
    Ask the Hermes LLM whether the email content is relevant to the given interests.

    Uses the `hermes` CLI in headless mode.
    Returns (matched: bool, reason: str | None). reason is None on error/no-match.
    """
    interests_str = ", ".join(f'"{i}"' for i in interests)

    prompt = (
        f"You are an email classifier. Analyze the following email content and determine "
        f"if it is genuinely relevant to these interests: [{interests_str}].\n\n"
        f"Rules:\n"
        f"- Consider the user's specific intent (e.g. 'jeans' means men's jeans unless context says otherwise)\n"
        f"- Return ONLY a JSON object with two fields:\n"
        f"  {{\"relevant\": true, \"reason\": \"brief one-sentence explanation\"}}\n"
        f"  or {{\"relevant\": false, \"reason\": \"brief one-sentence explanation\"}}\n"
        f"- Do not include any other text, explanation, or formatting\n\n"
        f"Email content:\n---\n{text[:3000]}\n---"
    )

    try:
        hermes_bin = _find_hermes_bin()
        if not hermes_bin:
            if verbose:
                print(
                    f"  [LLM] hermes CLI not found — skipping interest check for '{label_name}'",
                    file=sys.stderr,
                )
            return False, None

        result = subprocess.run(
            [hermes_bin, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = result.stdout.strip()
        if verbose:
            print(f"  [LLM] Interest check for '{label_name}': raw output = {output!r}")

        # Parse the JSON response — find the first {...} block
        match = re.search(r'\{[^}]+\}', output)
        if match:
            data = json.loads(match.group(0))
            relevant = bool(data.get("relevant", False))
            reason = data.get("reason") or None
            return relevant, reason if relevant else None

        # Fallback: check for plain true/false keywords in output
        lower = output.lower()
        if '"relevant": true' in lower or "'relevant': true" in lower:
            return True, "LLM confirmed relevance (no structured reason returned)"

        return False, None

    except subprocess.TimeoutExpired:
        print(
            f"  [WARN] LLM interest check timed out for label '{label_name}'",
            file=sys.stderr,
        )
        return False, None
    except Exception as e:
        print(
            f"  [WARN] LLM interest check failed for label '{label_name}': {e}",
            file=sys.stderr,
        )
        return False, None


def _find_hermes_bin() -> str:
    """Locate the hermes CLI binary."""
    import shutil

    # Try common locations
    candidates = [
        shutil.which("hermes"),
        os.path.expanduser("~/.local/bin/hermes"),
        "/usr/local/bin/hermes",
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return ""


def classify_email(
    text: str,
    sender: str,
    label_rules: Dict[str, Any],
    verbose: bool = False,
) -> Dict[str, str]:
    """
    Classify an email and return the list of label names to apply.

    Args:
        text:         Full OCR/plain text of the email.
        sender:       Raw 'From' header value.
        label_rules:  Config section from config.json.
        verbose:      Print per-rule debug output.

    Returns:
        Dict mapping label_name → justification string (may be empty dict).
    """
    domain = _extract_domain(sender)
    matched_labels: Dict[str, str] = {}

    for label_name, rule in label_rules.items():
        keywords: List[str] = rule.get("keywords", [])
        xkeywords: List[str] = rule.get("xkeywords", [])
        domains: List[str] = [d.lower() for d in rule.get("domains", [])]
        interests: List[str] = rule.get("interest", [])

        positive_signal = False
        justification: Optional[str] = None

        # 1. Domain match
        if domain and any(domain == d or domain.endswith("." + d) for d in domains):
            positive_signal = True
            justification = f"domain match ({domain})"
            if verbose:
                print(f"  [RULE] '{label_name}': domain match ({domain})")

        # 2. Keyword match
        if not positive_signal and _keywords_match(text, keywords):
            positive_signal = True
            matched_kws = [kw for kw in keywords if kw.lower() in text.lower()]
            justification = f"keyword match {matched_kws}"
            if verbose:
                print(f"  [RULE] '{label_name}': keyword match {matched_kws}")

        # 3. Interest / LLM check (only if other signals didn't already fire OR interest is standalone)
        if interests and not positive_signal:
            if verbose:
                print(
                    f"  [RULE] '{label_name}': running LLM interest check "
                    f"for interests {interests}"
                )
            llm_match, llm_reason = _check_interest_llm(text, interests, label_name, verbose=verbose)
            if llm_match:
                positive_signal = True
                justification = f"LLM interest match: {llm_reason or ', '.join(interests)}"
                if verbose:
                    print(f"  [RULE] '{label_name}': LLM interest matched")

        if not positive_signal:
            continue

        # 4. xkeywords disqualification (checked after any positive signal)
        if xkeywords and _keywords_match(text, xkeywords):
            if verbose:
                matched_xkws = [xk for xk in xkeywords if xk.lower() in text.lower()]
                print(
                    f"  [RULE] '{label_name}': DISQUALIFIED by xkeywords {matched_xkws}"
                )
            continue

        matched_labels[label_name] = justification or "unknown"
        if verbose:
            print(f"  [RULE] '{label_name}': ✓ MATCHED")

    return matched_labels
