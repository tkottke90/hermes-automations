#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
llm_trader.py — Sends Reddit scan context to the Hermes LLM and parses trade decisions.

The LLM receives full Reddit post content + current portfolio state + live prices
and returns structured JSON with buy/sell/hold decisions and reasoning.

Usage:
    python3.11 llm_trader.py <portfolio_id>
    python3.11 llm_trader.py pennystock
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path.home() / ".hermes" / "reddit-portfolio"
HERMES_BIN = "hermes"  # hermes CLI must be on PATH


def build_prompt(payload: dict) -> str:
    """Build the LLM prompt from the scan context payload."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from price_fetcher import is_market_open
    now_utc = datetime.now(timezone.utc)
    market_status = "OPEN" if is_market_open() else "CLOSED (outside regular trading hours)"

    holdings_text = payload.get("holdings_summary", "  (none)")
    prices_text = payload.get("prices_summary", "  (none)")
    posts_text = payload.get("posts_text", "  (no posts)")

    cash = payload["cash_balance"]
    starting = payload["starting_balance"]
    total_invested = sum(
        h.get("shares", 0) * h.get("avg_cost", 0)
        for h in payload.get("holdings", {}).values()
        if isinstance(payload.get("holdings"), dict)
    )
    max_trade = payload.get("max_single_trade_usd", 300.0)
    max_pct = payload.get("max_position_pct", 0.15) * 100
    max_trades = payload.get("max_trades")  # None = unlimited
    trades_today = payload.get("trades_today", 0)

    if max_trades is not None:
        trades_remaining = max_trades - trades_today
        trade_limit_line = f"Trade limit: {trades_today}/{max_trades} trades used today ({trades_remaining} remaining)"
    else:
        trades_remaining = None
        trade_limit_line = "Trade limit: unlimited"

    prompt = f"""You are managing a paper trading portfolio for r/{payload["subreddit"]}.
Your goal is to test whether Reddit penny stock discussions contain genuine trading signals.
This is simulated — no real money is at risk. Make realistic trading decisions.

=== PORTFOLIO STATE ===
Starting balance: ${starting:.2f}
Cash available: ${cash:.2f}
Max per trade: ${max_trade:.2f} (or {max_pct:.0f}% of portfolio, whichever is less)
{trade_limit_line}

Current holdings:
{holdings_text}

=== MARKET STATUS ===
{market_status} — {now_utc.strftime("%A %Y-%m-%d %H:%M UTC")}

=== CURRENT PRICES (for tickers mentioned in posts + holdings) ===
{prices_text}

=== REDDIT POSTS FROM r/{payload["subreddit"]} ===
{posts_text}

=== YOUR TASK ===
Review the above Reddit posts and make trading decisions for the portfolio.

GUIDELINES:
1. Only consider tickers with a confirmed current price — skip anything with "price unavailable"
2. Strongly prefer posts with specific DD: named catalysts, financial data, defined price levels
3. Be highly skeptical of: vague hype, anonymous claims, posts with "shill"/"pump"/"avoid" language
4. Check if you already hold a position before buying more (avoid doubling up unless thesis is strong)
5. Consider current P/L on existing holdings — don't panic-sell on noise, but cut clear losers
6. If market is CLOSED: you may recommend actions but set "execute": false — they queue for next open
7. Max position size: ${max_trade:.2f} per trade
8. You may decide to do NOTHING if the posts don't present compelling setups — that is valid
{f"9. IMPORTANT: You have {trades_remaining} trade(s) remaining today (limit: {max_trades}). Only recommend the highest-conviction trades — prioritize quality over quantity." if max_trades is not None else ""}

Respond ONLY with valid JSON in exactly this format (no markdown, no commentary outside JSON):
{{
  "decisions": [
    {{
      "action": "buy",
      "ticker": "XXXX",
      "amount_usd": 150.00,
      "execute": true,
      "reasoning": "Specific reason referencing the post content..."
    }},
    {{
      "action": "sell",
      "ticker": "YYYY",
      "execute": true,
      "reasoning": "Reason for selling..."
    }},
    {{
      "action": "hold",
      "ticker": "ZZZZ",
      "execute": false,
      "reasoning": "Why holding is correct right now..."
    }}
  ],
  "summary": "One paragraph summary of market conditions on r/{payload['subreddit']} and your overall strategy this scan.",
  "signal_quality": "low|medium|high",
  "shill_warnings": ["TICKER1", "TICKER2"]
}}

If no trades are warranted, return an empty decisions array with a summary explaining why.
"""
    return prompt


def call_llm(prompt: str) -> str:
    """
    Call the Hermes LLM via CLI and return the raw text response.
    Uses `hermes -z <prompt>` for single-turn non-interactive inference.
    """
    try:
        result = subprocess.run(
            [HERMES_BIN, "-z", prompt],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            raise RuntimeError(f"hermes -z failed: {result.stderr[:500]}")
        return result.stdout.strip()
    except FileNotFoundError:
        # Fallback: try the OpenAI-compatible API directly if hermes CLI not available
        return _call_llm_api_fallback(prompt)


def _call_llm_api_fallback(prompt: str) -> str:
    """
    Fallback: call the LLM via the Hermes internal API endpoint.
    Hermes runs a local API server that we can hit directly.
    """
    import urllib.request
    import urllib.parse

    # Check for hermes API config
    config_path = Path.home() / ".hermes" / "config.yaml"
    if not config_path.exists():
        raise RuntimeError("Neither hermes CLI nor config found. Cannot call LLM.")

    # Try to use the hermes Python SDK if available
    try:
        # Use a simple subprocess approach with hermes run
        result = subprocess.run(
            ["hermes", "run", "--once", prompt],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    raise RuntimeError(
        "Could not call LLM. Ensure 'hermes' is on PATH and configured."
    )


def parse_decisions(raw_response: str) -> dict:
    """Extract and parse JSON from LLM response."""
    # Strip markdown code fences if present
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```(?:json)?\n?', '', cleaned)
        cleaned = re.sub(r'\n?```$', '', cleaned)
    cleaned = cleaned.strip()

    # Find JSON object in response
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in LLM response:\n{raw_response[:500]}")

    return json.loads(match.group(0))


def run(portfolio_id: str, payload: dict) -> dict:
    """
    Main entry: build prompt, call LLM, parse decisions.
    Returns the parsed decisions dict.
    """
    print(f"[llm_trader] Building prompt for r/{payload['subreddit']}...", file=sys.stderr)
    prompt = build_prompt(payload)

    print(f"[llm_trader] Calling LLM ({len(prompt)} chars)...", file=sys.stderr)
    raw = call_llm(prompt)
    print(f"[llm_trader] LLM responded ({len(raw)} chars).", file=sys.stderr)

    decisions = parse_decisions(raw)
    print(f"[llm_trader] Parsed {len(decisions.get('decisions', []))} decisions.", file=sys.stderr)
    print(f"[llm_trader] Summary: {decisions.get('summary', '')[:200]}", file=sys.stderr)

    # Attach metadata
    decisions["scan_utc"] = payload.get("scan_utc")
    decisions["subreddit"] = payload.get("subreddit")
    decisions["portfolio_id"] = portfolio_id
    decisions["raw_llm_response"] = raw

    return decisions


if __name__ == "__main__":
    portfolio_id = sys.argv[1] if len(sys.argv) > 1 else "pennystock"
    sys.path.insert(0, str(Path(__file__).parent))

    # Load a pre-built payload from stdin or run scanner inline
    if not sys.stdin.isatty():
        payload = json.load(sys.stdin)
    else:
        from reddit_scanner import run as scan_run
        payload = scan_run(portfolio_id, force="--force" in sys.argv)
        if not payload:
            print("[llm_trader] Scanner returned nothing (rate limited).", file=sys.stderr)
            sys.exit(0)

    decisions = run(portfolio_id, payload)
    print(json.dumps(decisions, indent=2))
