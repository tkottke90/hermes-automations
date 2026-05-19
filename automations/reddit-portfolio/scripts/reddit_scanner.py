#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
reddit_scanner.py — Fetches Reddit posts, extracts tickers, builds LLM context payload.

Usage:
    python3.11 reddit_scanner.py <portfolio_id>
    python3.11 reddit_scanner.py pennystock

Respects 5-minute minimum poll interval via last_read_utc in portfolio.json.
Outputs a context payload JSON to stdout for use by llm_trader.py.
"""

import json
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path.home() / ".hermes" / "reddit-portfolio"
CONFIG_PATH = BASE_DIR / "config.json"

# Tickers that are common English words / false positives to ignore
TICKER_STOPLIST = {
    "A", "AI", "ALL", "AM", "AN", "ARE", "AS", "AT", "BE", "BY", "CEO", "CFO",
    "CTO", "DO", "FOR", "GO", "HE", "I", "IF", "IN", "IS", "IT", "ME", "MY",
    "NO", "OF", "ON", "OR", "PM", "PR", "RE", "SO", "TO", "UP", "US", "WE",
    "DD", "IPO", "ETF", "SEC", "OTC", "NYSE", "NASDAQ", "EPS", "PE", "ATH",
    "AH", "EOD", "IMO", "FOMO", "YOLO", "WTF", "LOL", "TBH", "FYI", "DM",
    "RH", "TD", "BC", "CA", "NY", "LA", "DC", "SP", "USA",
    # Common English words that appear in ALL CAPS in posts
    "NOT", "READ", "THAT", "THIS", "THEY", "WITH", "FROM", "HAVE", "BEEN",
    "WILL", "YOUR", "WHEN", "ALSO", "MORE", "THAN", "JUST", "SOME", "INTO",
    "OVER", "BACK", "ONLY", "MOST", "VERY", "EVEN", "WHAT", "WELL", "LIKE",
    "YEAR", "WEEK", "DAYS", "TIME", "SAID", "WANT", "POST", "HYPE", "NEWS",
    "PRICE", "ONCE", "THEN", "EACH", "BOTH", "MANY", "MUCH", "LAST", "NEXT",
    "LONG", "HARD", "REAL", "GOOD", "MAKE", "BEEN", "SUCH", "SAME", "TAKE",
    "HIGH", "DOWN", "HOLD", "SELL", "BUYS", "BUYI", "NEAR", "PUSH", "MOVE",
    "HUGE", "EVER", "PUMP", "DUMP", "SHOW", "TELL", "FEEL", "CALL", "PUTS",
    "ALSO", "COPY", "DONT", "ISNT", "CANT", "WONT", "LETS", "HERE", "WELL",
    "SEGG", "THAT", "HYPE", "FAR", "HOD", "MAY", "NOT", "POSTS", "READ",
    "HEAVY", "THAT",
}

BULLISH_KEYWORDS = [
    "dd", "earnings", "squeeze", "catalyst", "breakout", "accumulation",
    "institutional", "fda", "merger", "acquisition", "revenue", "profit",
    "contract", "partnership", "patent", "buyout", "short interest",
    "low float", "runner", "momentum", "volume", "gap up",
]

BEARISH_KEYWORDS = [
    "shill", "pump", "dump", "scam", "avoid", "warning", "fraud", "fake",
    "beware", "manipulation", "bagholders", "dilution", "reverse split",
    "toxic", "halt",
]


def load_config(portfolio_id: str) -> dict:
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    for p in config["portfolios"]:
        if p["id"] == portfolio_id:
            return p
    raise ValueError(f"Portfolio '{portfolio_id}' not found in config.json")


def load_portfolio(portfolio_id: str) -> dict:
    path = BASE_DIR / "portfolios" / portfolio_id / "portfolio.json"
    with open(path) as f:
        return json.load(f)


def save_portfolio_last_read(portfolio_id: str, ts: str):
    path = BASE_DIR / "portfolios" / portfolio_id / "portfolio.json"
    with open(path) as f:
        portfolio = json.load(f)
    portfolio["last_read_utc"] = ts
    with open(path, "w") as f:
        json.dump(portfolio, f, indent=2)


def check_rate_limit(portfolio: dict, min_interval_minutes: int = 5) -> bool:
    """Return True if enough time has passed since last scan."""
    last_read = portfolio.get("last_read_utc")
    if not last_read:
        return True
    last_dt = datetime.fromisoformat(last_read.replace("Z", "+00:00"))
    elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
    return elapsed >= min_interval_minutes


_rl_remaining: float = 100.0   # updated from x-ratelimit-remaining headers
_rl_reset_at: float = 0.0      # epoch time when the rate limit window resets


def fetch_reddit_json(url: str, _retries: int = 3) -> dict | None:
    """Fetch Reddit JSON, respecting rate-limit headers and retrying on 5xx.

    Reddit returns three rate-limit headers on every response:
      x-ratelimit-used      — requests used in this window
      x-ratelimit-remaining — requests left (float)
      x-ratelimit-reset     — seconds until window resets

    We read these on every successful response and back off proactively
    when remaining < 10 to avoid triggering 429s or overloading their edge.
    On 5xx we retry up to _retries times with exponential backoff.
    """
    import time
    global _rl_remaining, _rl_reset_at

    # Proactive back-off: if we're almost out of budget, sleep until reset
    if _rl_remaining < 10 and _rl_reset_at > time.time():
        wait = _rl_reset_at - time.time()
        print(f"[scanner] rate-limit budget low ({_rl_remaining:.0f} remaining) — sleeping {wait:.0f}s until reset", file=sys.stderr)
        time.sleep(max(0, wait))

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        },
    )

    for attempt in range(1, _retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                # Read and store rate-limit headers for next call
                try:
                    _rl_remaining = float(resp.headers.get("x-ratelimit-remaining", _rl_remaining))
                    reset_secs    = float(resp.headers.get("x-ratelimit-reset", 0))
                    _rl_reset_at  = time.time() + reset_secs
                    used          = resp.headers.get("x-ratelimit-used", "?")
                    print(f"[scanner] ratelimit: used={used}, remaining={_rl_remaining:.0f}, reset_in={reset_secs:.0f}s", file=sys.stderr)
                except Exception:
                    pass  # headers missing — not fatal
                return json.loads(resp.read().decode())

        except urllib.error.HTTPError as e:
            if e.code in (500, 502, 503, 504) and attempt < _retries:
                wait = 2 ** attempt  # 2s, 4s, 8s
                print(f"[scanner] HTTP {e.code} on attempt {attempt}/{_retries} — retrying in {wait}s: {url}", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"[scanner] fetch error {url}: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"[scanner] fetch error {url}: {e}", file=sys.stderr)
            return None

    return None


def extract_tickers(text: str) -> list[str]:
    """
    Extract stock ticker symbols from text.
    Primarily uses $TICKER pattern (most reliable).
    Also catches plain tickers only when preceded by known context words.
    """
    tickers = set()

    # $TICKER pattern — most reliable signal
    for match in re.finditer(r'\$([A-Z]{1,5})', text.upper()):
        t = match.group(1)
        if t not in TICKER_STOPLIST and len(t) >= 2:
            tickers.add(t)

    # Plain 2-5 char ALL-CAPS word that appears as a standalone token (not sentence words)
    # Only match if the word appears in ALL CAPS in the original text (not uppercased by us)
    for match in re.finditer(r'\b([A-Z]{2,5})\b', text):  # search original case text
        t = match.group(1)
        if t not in TICKER_STOPLIST and len(t) >= 2:
            tickers.add(t)

    return sorted(tickers)


def score_post(post: dict) -> int:
    """
    Score a post 1–10 for trading signal quality.
    Higher = more worth the LLM's attention.
    """
    score = 3  # baseline
    text = (post.get("title", "") + " " + post.get("body", "")).lower()

    # Engagement
    upvotes = post.get("score", 0)
    comments = post.get("num_comments", 0)
    if upvotes >= 20:
        score += 2
    elif upvotes >= 10:
        score += 1
    if comments >= 20:
        score += 2
    elif comments >= 10:
        score += 1

    # Bullish signals
    bull_hits = sum(1 for kw in BULLISH_KEYWORDS if kw in text)
    score += min(bull_hits, 2)

    # Bearish / shill signals (lower score)
    bear_hits = sum(1 for kw in BEARISH_KEYWORDS if kw in text)
    score -= min(bear_hits, 3)

    return max(1, min(10, score))


def fetch_post_comments(permalink: str, limit: int = 5) -> list[str]:
    """Fetch top comments for a post."""
    url = f"https://www.reddit.com{permalink}.json?limit={limit}&sort=top"
    data = fetch_reddit_json(url)
    if not data or len(data) < 2:
        return []
    comments = []
    for child in data[1]["data"]["children"]:
        body = child["data"].get("body", "")
        if body and body != "[deleted]" and body != "[removed]":
            comments.append(body[:300])
    return comments[:limit]


def fetch_posts(subreddit: str, limit_hot: int = 25, limit_new: int = 10) -> list[dict]:
    """Fetch hot + new posts from a subreddit, deduplicated."""
    seen_ids = set()
    posts = []

    for endpoint in [f"hot.json?limit={limit_hot}", f"new.json?limit={limit_new}"]:
        url = f"https://www.reddit.com/r/{subreddit}/{endpoint}"
        data = fetch_reddit_json(url)
        if not data:
            continue
        for child in data["data"]["children"]:
            d = child["data"]
            if d["id"] in seen_ids:
                continue
            seen_ids.add(d["id"])
            posts.append({
                "id": d["id"],
                "title": d["title"],
                "body": d.get("selftext", "")[:1500],
                "author": d.get("author", ""),
                "score": d.get("score", 0),
                "num_comments": d.get("num_comments", 0),
                "permalink": d.get("permalink", ""),
                "url": f"https://reddit.com{d.get('permalink', '')}",
                "created_utc": d.get("created_utc", 0),
                "tickers": extract_tickers(d["title"] + " " + d.get("selftext", "")),
            })
        time.sleep(1)  # be polite between requests

    # Skip comment fetching to stay within rate limits and keep scans fast.
    # Post body + title provides sufficient signal for the LLM.
    for post in posts:
        post["top_comments"] = []

    # Add signal score
    for post in posts:
        post["signal_score"] = score_post(post)

    # Sort by signal score desc
    posts.sort(key=lambda p: p["signal_score"], reverse=True)
    return posts


def build_context_payload(portfolio: dict, posts: list[dict], prices: dict) -> dict:
    """Build the full context payload for the LLM."""
    # Gather all unique tickers mentioned
    all_tickers = set()
    for post in posts:
        all_tickers.update(post["tickers"])

    # Build holdings summary
    holdings_lines = []
    for ticker, h in portfolio.get("holdings", {}).items():
        price_data = prices.get(ticker, {})
        current_price = price_data.get("price") if price_data else None
        avg_cost = h.get("avg_cost", 0)
        shares = h.get("shares", 0)
        if current_price:
            pnl = (current_price - avg_cost) * shares
            pnl_pct = ((current_price - avg_cost) / avg_cost * 100) if avg_cost else 0
            holdings_lines.append(
                f"  {ticker}: {shares} shares @ avg ${avg_cost:.4f} | "
                f"current ${current_price:.4f} | P/L: ${pnl:+.2f} ({pnl_pct:+.1f}%)"
            )
        else:
            holdings_lines.append(
                f"  {ticker}: {shares} shares @ avg ${avg_cost:.4f} | price unavailable"
            )

    # Build prices section for mentioned tickers
    price_lines = []
    for ticker in sorted(all_tickers):
        pd = prices.get(ticker, {})
        if pd and pd.get("price"):
            price_lines.append(
                f"  {ticker}: ${pd['price']:.4f} (prev close: ${pd.get('prev_close', 'N/A')}, "
                f"vol: {pd.get('volume', 'N/A'):,})"
            )
        else:
            price_lines.append(f"  {ticker}: price unavailable / not listed")

    # Build posts section
    post_lines = []
    for i, post in enumerate(posts[:20], 1):  # cap at 20 posts for token efficiency
        lines = [
            f"\n--- Post {i} [Signal: {post['signal_score']}/10 | "
            f"Score: {post['score']} | Comments: {post['num_comments']}] ---",
            f"Title: {post['title']}",
            f"Author: u/{post['author']}",
            f"Tickers mentioned: {', '.join(post['tickers']) if post['tickers'] else 'none detected'}",
        ]
        if post["body"]:
            lines.append(f"Body: {post['body'][:800]}")
        if post["top_comments"]:
            lines.append("Top comments:")
            for c in post["top_comments"][:3]:
                lines.append(f"  > {c[:200]}")
        lines.append(f"URL: {post['url']}")
        post_lines.append("\n".join(lines))

    return {
        "portfolio_id": portfolio["id"],
        "subreddit": portfolio["subreddit"],
        "scan_utc": datetime.now(timezone.utc).isoformat(),
        "cash_balance": portfolio["current_balance"],
        "starting_balance": portfolio["starting_balance"],
        "holdings_summary": "\n".join(holdings_lines) if holdings_lines else "  (none)",
        "prices_summary": "\n".join(price_lines) if price_lines else "  (none)",
        "posts_text": "\n".join(post_lines),
        "all_tickers": sorted(all_tickers),
        "max_position_pct": 0.15,
        "max_single_trade_usd": 300.0,
        "posts": posts,
        "prices": prices,
    }


def run(portfolio_id: str, force: bool = False) -> dict | None:
    """
    Main entry point. Returns context payload or None if rate-limited.
    """
    config = load_config(portfolio_id)
    portfolio = load_portfolio(portfolio_id)
    # Use 14 min instead of 15 to account for scan runtime (~30-60s).
    # The cron fires every 15 min but last_read_utc is set ~1 min into the cycle,
    # causing the next tick to be only ~14 min later and trip the rate limit.
    configured = config.get("check_interval_minutes", 15)
    min_interval = max(5, configured - 1)

    if not force and not check_rate_limit(portfolio, min_interval):
        last = portfolio.get("last_read_utc", "never")
        from datetime import datetime, timezone
        try:
            last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
            print(f"[scanner] Rate limited. Last scan: {last} ({elapsed:.1f}m ago). Min interval: {min_interval}m. Need {min_interval - elapsed:.1f}m more.", file=sys.stderr)
        except Exception:
            print(f"[scanner] Rate limited. Last scan: {last}. Min interval: {min_interval}m.", file=sys.stderr)
        return None

    subreddit = config["subreddit"]
    print(f"[scanner] Scanning r/{subreddit}...", file=sys.stderr)

    posts = fetch_posts(subreddit)
    print(f"[scanner] Fetched {len(posts)} posts. Tickers found: {set(t for p in posts for t in p['tickers'])}", file=sys.stderr)

    # Fetch prices for all mentioned tickers + existing holdings
    from price_fetcher import get_prices
    all_tickers = list(set(t for p in posts for t in p["tickers"]) | set(portfolio.get("holdings", {}).keys()))
    prices = get_prices(all_tickers)

    payload = build_context_payload(portfolio, posts, prices)

    # Update last_read_utc
    save_portfolio_last_read(portfolio_id, payload["scan_utc"])

    return payload


if __name__ == "__main__":
    portfolio_id = sys.argv[1] if len(sys.argv) > 1 else "pennystock"
    force = "--force" in sys.argv
    import os
    os.chdir(Path(__file__).parent)

    payload = run(portfolio_id, force=force)
    if payload:
        # Print a clean summary (not the full payload — that goes to llm_trader)
        print(f"\n=== Scan Summary: r/{payload['subreddit']} ===")
        print(f"Cash: ${payload['cash_balance']:.2f}")
        print(f"Holdings:\n{payload['holdings_summary']}")
        print(f"\nTop tickers mentioned: {', '.join(payload['all_tickers'][:15])}")
        print(f"\nPrices:\n{payload['prices_summary']}")
        print(f"\nTop posts preview:")
        for p in payload["posts"][:5]:
            print(f"  [{p['signal_score']}/10] {p['title'][:80]} — {', '.join(p['tickers'])}")
