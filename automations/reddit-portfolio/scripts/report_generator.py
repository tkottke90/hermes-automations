#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
report_generator.py — Generates a daily HTML report for a portfolio.

Usage:
    python3.11 report_generator.py <portfolio_id>
    python3.11 report_generator.py pennystock
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path.home() / ".hermes" / "reddit-portfolio"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>r/{subreddit} Portfolio Report — {date_label}</title>
<style>
  :root {{
    --bg: #0f0f13;
    --card: #1a1a22;
    --border: #2a2a38;
    --accent: #6c63ff;
    --green: #22c55e;
    --red: #ef4444;
    --yellow: #f59e0b;
    --text: #e2e8f0;
    --muted: #8892a4;
    --font: 'Segoe UI', system-ui, -apple-system, sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--font); padding: 24px; }}
  h1 {{ font-size: 1.6rem; color: var(--accent); margin-bottom: 4px; }}
  .subtitle {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 28px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 28px; }}
  .stat-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }}
  .stat-label {{ font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }}
  .stat-value {{ font-size: 1.5rem; font-weight: 700; margin-top: 4px; }}
  .green {{ color: var(--green); }}
  .red {{ color: var(--red); }}
  .yellow {{ color: var(--yellow); }}
  .neutral {{ color: var(--text); }}
  .section {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 20px; }}
  .section h2 {{ font-size: 1rem; color: var(--accent); margin-bottom: 14px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
  th {{ text-align: left; color: var(--muted); font-weight: 600; font-size: 0.75rem; text-transform: uppercase; padding: 6px 10px; }}
  td {{ padding: 8px 10px; border-top: 1px solid var(--border); }}
  tr:hover td {{ background: rgba(108,99,255,0.06); }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 99px; font-size: 0.7rem; font-weight: 600; }}
  .badge-buy {{ background: rgba(34,197,94,0.15); color: var(--green); }}
  .badge-sell {{ background: rgba(239,68,68,0.15); color: var(--red); }}
  .badge-hold {{ background: rgba(245,158,11,0.15); color: var(--yellow); }}
  .reasoning {{ font-size: 0.8rem; color: var(--muted); max-width: 400px; }}
  .summary-box {{ background: rgba(108,99,255,0.08); border: 1px solid rgba(108,99,255,0.25); border-radius: 8px; padding: 14px; font-size: 0.9rem; line-height: 1.6; color: var(--text); margin-bottom: 16px; }}
  .warn-list {{ list-style: none; }}
  .warn-list li {{ padding: 4px 0; font-size: 0.85rem; color: var(--red); }}
  .warn-list li::before {{ content: "⚠️ "; }}
  .empty {{ color: var(--muted); font-style: italic; font-size: 0.9rem; padding: 12px 0; }}
  .footer {{ text-align: center; color: var(--muted); font-size: 0.75rem; margin-top: 32px; }}
</style>
</head>
<body>
<h1>📊 r/{subreddit} Paper Portfolio</h1>
<p class="subtitle">Daily Report — {date_label} &nbsp;|&nbsp; Generated {generated_utc} UTC</p>

<div class="grid">
  <div class="stat-card">
    <div class="stat-label">Cash Balance</div>
    <div class="stat-value neutral">${cash_balance}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Portfolio Value</div>
    <div class="stat-value neutral">${portfolio_value}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Total P/L</div>
    <div class="stat-value {pnl_class}">{pnl_signed} ({pnl_pct}%)</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Open Positions</div>
    <div class="stat-value neutral">{open_positions}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Total Trades</div>
    <div class="stat-value neutral">{total_trades}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Win Rate</div>
    <div class="stat-value {winrate_class}">{win_rate}%</div>
  </div>
</div>

<div class="section">
  <h2>🤖 LLM Trading Summary</h2>
  {llm_summary_html}
  {shill_warnings_html}
</div>

<div class="section">
  <h2>📦 Open Positions</h2>
  {holdings_table}
</div>

<div class="section">
  <h2>📋 Today's Trades</h2>
  {todays_trades_table}
</div>

<div class="section">
  <h2>📜 Full Transaction History</h2>
  {all_trades_table}
</div>

<div class="footer">
  Paper trading only — no real money involved &nbsp;|&nbsp; <a href="https://reddit.com/r/{subreddit}" style="color:var(--muted)" target="_blank">r/{subreddit}</a> &nbsp;|&nbsp; Hermes Reddit Portfolio Tracker
</div>
</body>
</html>
"""

def fmt_usd(val: float) -> str:
    return f"{val:,.2f}"

def fmt_signed(val: float) -> str:
    return f"+${val:,.2f}" if val >= 0 else f"-${abs(val):,.2f}"

def build_holdings_table(portfolio: dict, prices: dict) -> str:
    holdings = portfolio.get("holdings", {})
    if not holdings:
        return '<p class="empty">No open positions.</p>'

    rows = ""
    for ticker, h in sorted(holdings.items()):
        shares = h.get("shares", 0)
        avg_cost = h.get("avg_cost", 0)
        current_price = prices.get(ticker, {}).get("price") if prices else None
        cost_basis = shares * avg_cost

        if current_price:
            current_val = shares * current_price
            pnl = current_val - cost_basis
            pnl_pct = (pnl / cost_basis * 100) if cost_basis else 0
            pnl_class = "green" if pnl >= 0 else "red"
            pnl_str = f'<span class="{pnl_class}">{fmt_signed(pnl)} ({pnl_pct:+.1f}%)</span>'
            cur_price_str = f"${current_price:.4f}"
            cur_val_str = f"${fmt_usd(current_val)}"
        else:
            pnl_str = '<span class="yellow">N/A</span>'
            cur_price_str = "—"
            cur_val_str = "—"

        first_bought = h.get("first_bought_utc", "")[:10]
        rows += f"""
        <tr>
          <td><strong>{ticker}</strong></td>
          <td>{shares:.2f}</td>
          <td>${avg_cost:.4f}</td>
          <td>${fmt_usd(cost_basis)}</td>
          <td>{cur_price_str}</td>
          <td>{cur_val_str}</td>
          <td>{pnl_str}</td>
          <td>{first_bought}</td>
        </tr>"""

    return f"""
    <table>
      <thead><tr>
        <th>Ticker</th><th>Shares</th><th>Avg Cost</th><th>Cost Basis</th>
        <th>Current Price</th><th>Current Value</th><th>P/L</th><th>Bought</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>"""


def build_trades_table(transactions: list, today_only: bool = False) -> str:
    items = transactions
    if today_only:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        items = [t for t in transactions if t.get("timestamp", "").startswith(today)]

    if not items:
        return '<p class="empty">No trades today.</p>' if today_only else '<p class="empty">No transactions yet.</p>'

    rows = ""
    for t in reversed(items):
        action = t.get("type", "buy")
        badge_class = f"badge-{action}"
        ts = t.get("timestamp", "")[:16].replace("T", " ")
        ticker = t.get("ticker", "")
        price = t.get("unit_price", 0)
        qty = t.get("quantity", 0)
        total = t.get("total", 0)
        pnl = t.get("profit_loss")
        reasoning = t.get("llm_reasoning", "")[:120]

        if pnl is not None:
            pnl_class = "green" if pnl >= 0 else "red"
            pnl_str = f'<span class="{pnl_class}">{fmt_signed(pnl)}</span>'
        else:
            pnl_str = "—"

        rows += f"""
        <tr>
          <td>{ts}</td>
          <td><span class="badge {badge_class}">{action.upper()}</span></td>
          <td><strong>{ticker}</strong></td>
          <td>${price:.4f}</td>
          <td>{qty:.2f}</td>
          <td>${fmt_usd(total)}</td>
          <td>{pnl_str}</td>
          <td class="reasoning">{reasoning}</td>
        </tr>"""

    return f"""
    <table>
      <thead><tr>
        <th>Time (UTC)</th><th>Action</th><th>Ticker</th><th>Price</th>
        <th>Shares</th><th>Total</th><th>P/L</th><th>Reasoning</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>"""


def generate_report(portfolio_id: str, latest_decisions: dict = None) -> Path:
    portfolio_dir = BASE_DIR / "portfolios" / portfolio_id
    portfolio = json.loads((portfolio_dir / "portfolio.json").read_text())
    transactions = json.loads((portfolio_dir / "transactions.json").read_text())

    # Fetch current prices for open positions
    holdings = portfolio.get("holdings", {})
    prices = {}
    if holdings:
        sys.path.insert(0, str(Path(__file__).parent))
        from price_fetcher import get_prices
        prices = get_prices(list(holdings.keys()))

    subreddit = portfolio.get("subreddit", portfolio_id)
    starting = portfolio.get("starting_balance", 2000.0)
    cash = portfolio.get("current_balance", starting)

    # Compute portfolio value
    holdings_value = sum(
        h["shares"] * (prices.get(ticker, {}).get("price") or h.get("avg_cost", 0))
        for ticker, h in holdings.items()
    )
    portfolio_value = cash + holdings_value
    total_pnl = portfolio_value - starting
    pnl_pct = (total_pnl / starting * 100) if starting else 0
    pnl_class = "green" if total_pnl >= 0 else "red"
    pnl_signed = fmt_signed(total_pnl)

    # Win rate from closed trades
    closed = [t for t in transactions if t.get("type") == "sell" and t.get("profit_loss") is not None]
    wins = sum(1 for t in closed if t.get("profit_loss", 0) >= 0)
    win_rate = round(wins / len(closed) * 100) if closed else 0
    winrate_class = "green" if win_rate >= 50 else "red" if closed else "neutral"

    # LLM summary block
    if latest_decisions and latest_decisions.get("summary"):
        llm_summary_html = f'<div class="summary-box">{latest_decisions["summary"]}</div>'
        signal_q = latest_decisions.get("signal_quality", "")
        if signal_q:
            llm_summary_html += f'<p style="font-size:0.8rem;color:var(--muted)">Signal quality: <strong>{signal_q}</strong></p>'
    else:
        llm_summary_html = '<p class="empty">No LLM summary for this run.</p>'

    # Shill warnings
    shills = (latest_decisions or {}).get("shill_warnings", [])
    if shills:
        items = "".join(f"<li>{s} flagged as potential shill/pump</li>" for s in shills)
        shill_warnings_html = f'<ul class="warn-list" style="margin-top:12px">{items}</ul>'
    else:
        shill_warnings_html = ""

    now = datetime.now(timezone.utc)
    date_label = now.strftime("%B %d, %Y")
    generated_utc = now.strftime("%Y-%m-%d %H:%M")
    date_slug = now.strftime("%Y%m%d")

    html = HTML_TEMPLATE.format(
        subreddit=subreddit,
        date_label=date_label,
        generated_utc=generated_utc,
        cash_balance=fmt_usd(cash),
        portfolio_value=fmt_usd(portfolio_value),
        pnl_class=pnl_class,
        pnl_signed=pnl_signed,
        pnl_pct=f"{pnl_pct:+.1f}",
        open_positions=len(holdings),
        total_trades=len(transactions),
        win_rate=win_rate,
        winrate_class=winrate_class,
        llm_summary_html=llm_summary_html,
        shill_warnings_html=shill_warnings_html,
        holdings_table=build_holdings_table(portfolio, prices),
        todays_trades_table=build_trades_table(transactions, today_only=True),
        all_trades_table=build_trades_table(transactions, today_only=False),
    )

    report_dir = BASE_DIR / "reports"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / f"{portfolio_id}.{date_slug}.html"
    report_path.write_text(html)
    print(f"[report] Written: {report_path}", file=sys.stderr)
    return report_path


if __name__ == "__main__":
    portfolio_id = sys.argv[1] if len(sys.argv) > 1 else "pennystock"
    sys.path.insert(0, str(Path(__file__).parent))

    # Optionally accept decisions JSON from stdin
    decisions = None
    if not sys.stdin.isatty():
        try:
            decisions = json.load(sys.stdin)
        except Exception:
            pass

    path = generate_report(portfolio_id, latest_decisions=decisions)
    print(str(path))
