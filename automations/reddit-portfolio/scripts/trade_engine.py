#!/Users/thomaskottke/.hermes/.venv/bin/python
"""
trade_engine.py — Applies LLM decisions to the portfolio and transaction ledger.

Takes the decisions JSON from llm_trader.py, validates each trade,
fetches current prices, and updates portfolio.json + transactions.json.

Usage:
    python3.11 trade_engine.py <portfolio_id> <decisions_json_file>
    echo '{"decisions":[...]}' | python3.11 trade_engine.py pennystock
"""

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path.home() / ".hermes" / "reddit-portfolio"


def load_portfolio(portfolio_id: str) -> dict:
    path = BASE_DIR / "portfolios" / portfolio_id / "portfolio.json"
    with open(path) as f:
        return json.load(f)


def save_portfolio(portfolio_id: str, portfolio: dict):
    path = BASE_DIR / "portfolios" / portfolio_id / "portfolio.json"
    with open(path, "w") as f:
        json.dump(portfolio, f, indent=2)


def load_transactions(portfolio_id: str) -> list:
    path = BASE_DIR / "portfolios" / portfolio_id / "transactions.json"
    with open(path) as f:
        return json.load(f)


def save_transactions(portfolio_id: str, transactions: list):
    path = BASE_DIR / "portfolios" / portfolio_id / "transactions.json"
    with open(path, "w") as f:
        json.dump(transactions, f, indent=2)


def execute_buy(portfolio: dict, transactions: list, decision: dict, price_data: dict) -> tuple[bool, str]:
    """
    Execute a buy order. Returns (success, message).
    """
    ticker = decision["ticker"].upper()
    price = price_data.get("price")
    if not price or price <= 0:
        return False, f"No valid price for {ticker}"

    amount_usd = float(decision.get("amount_usd", 0))
    if amount_usd <= 0:
        return False, f"Invalid amount_usd: {amount_usd}"

    # Enforce max trade cap
    config_path = BASE_DIR / "config.json"
    with open(config_path) as f:
        config = json.load(f)
    portfolio_config = next(
        (p for p in config["portfolios"] if p["id"] == portfolio["id"]), {}
    )
    max_trade = portfolio_config.get("max_single_trade_usd", 300.0)
    max_pct = portfolio_config.get("max_position_pct", 0.15)
    portfolio_value = portfolio["current_balance"] + sum(
        h["shares"] * h.get("avg_cost", 0)
        for h in portfolio.get("holdings", {}).values()
    )
    max_by_pct = portfolio_value * max_pct
    amount_usd = min(amount_usd, max_trade, max_by_pct)

    if amount_usd > portfolio["current_balance"]:
        amount_usd = portfolio["current_balance"]  # buy what we can afford

    if amount_usd < 1.0:
        return False, f"Insufficient balance (${portfolio['current_balance']:.2f}) for {ticker}"

    shares = amount_usd / price
    total_cost = shares * price

    # Update holdings (average down if already holding)
    holdings = portfolio.setdefault("holdings", {})
    if ticker in holdings:
        existing = holdings[ticker]
        total_shares = existing["shares"] + shares
        avg_cost = (existing["shares"] * existing["avg_cost"] + shares * price) / total_shares
        holdings[ticker]["shares"] = total_shares
        holdings[ticker]["avg_cost"] = avg_cost
    else:
        holdings[ticker] = {
            "shares": shares,
            "avg_cost": price,
            "first_bought_utc": datetime.now(timezone.utc).isoformat(),
            "source_post_url": decision.get("source_post_url", ""),
        }

    portfolio["current_balance"] -= total_cost

    # Record transaction
    transactions.append({
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "type": "buy",
        "unit_price": round(price, 4),
        "quantity": round(shares, 4),
        "total": round(total_cost, 2),
        "profit_loss": None,
        "llm_reasoning": decision.get("reasoning", ""),
        "source_post_url": decision.get("source_post_url", ""),
        "signal_quality": decision.get("signal_quality", ""),
    })

    return True, f"BUY {shares:.2f} shares of {ticker} @ ${price:.4f} = ${total_cost:.2f}"


def execute_sell(portfolio: dict, transactions: list, decision: dict, price_data: dict) -> tuple[bool, str]:
    """
    Execute a sell order (full position). Returns (success, message).
    """
    ticker = decision["ticker"].upper()
    price = price_data.get("price")
    if not price or price <= 0:
        return False, f"No valid price for {ticker}"

    holdings = portfolio.get("holdings", {})
    if ticker not in holdings:
        return False, f"No position in {ticker} to sell"

    holding = holdings[ticker]
    shares = holding["shares"]
    avg_cost = holding["avg_cost"]
    total_proceeds = shares * price
    profit_loss = round((price - avg_cost) * shares, 2)
    profit_loss_pct = round(((price - avg_cost) / avg_cost) * 100, 2) if avg_cost > 0 else 0

    # Update portfolio
    portfolio["current_balance"] += total_proceeds
    del holdings[ticker]

    # Record transaction
    transactions.append({
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "type": "sell",
        "unit_price": round(price, 4),
        "quantity": round(shares, 4),
        "total": round(total_proceeds, 2),
        "profit_loss": profit_loss,
        "profit_loss_pct": profit_loss_pct,
        "avg_cost": round(avg_cost, 4),
        "llm_reasoning": decision.get("reasoning", ""),
        "source_post_url": decision.get("source_post_url", ""),
    })

    emoji = "✅" if profit_loss >= 0 else "❌"
    return True, f"SELL {shares:.2f} shares of {ticker} @ ${price:.4f} = ${total_proceeds:.2f} | P/L: {emoji} ${profit_loss:+.2f} ({profit_loss_pct:+.1f}%)"


def apply_decisions(portfolio_id: str, decisions: dict, prices: dict) -> list[str]:
    """
    Apply all LLM decisions to the portfolio.
    Returns list of execution messages.
    """
    portfolio = load_portfolio(portfolio_id)
    transactions = load_transactions(portfolio_id)
    messages = []

    decision_list = decisions.get("decisions", [])
    if not decision_list:
        msg = "[trade_engine] No trades to execute."
        print(msg, file=sys.stderr)
        return [msg]

    for decision in decision_list:
        action = decision.get("action", "").lower()
        ticker = decision.get("ticker", "").upper()
        execute = decision.get("execute", True)

        if not execute:
            msg = f"[SKIPPED] {action.upper()} {ticker} — LLM set execute=false (market closed or low confidence)"
            print(msg, file=sys.stderr)
            messages.append(msg)
            continue

        if action == "hold":
            msg = f"[HOLD] {ticker} — {decision.get('reasoning', '')[:100]}"
            messages.append(msg)
            continue

        if not ticker:
            messages.append(f"[SKIP] Decision missing ticker: {decision}")
            continue

        price_data = prices.get(ticker, {})
        if not price_data or not price_data.get("price"):
            # Try to fetch on demand
            sys.path.insert(0, str(Path(__file__).parent))
            from price_fetcher import get_price
            price_data = get_price(ticker) or {}

        if action == "buy":
            success, msg = execute_buy(portfolio, transactions, decision, price_data)
        elif action == "sell":
            success, msg = execute_sell(portfolio, transactions, decision, price_data)
        else:
            msg = f"[SKIP] Unknown action '{action}' for {ticker}"
            success = False

        status = "✅" if success else "❌"
        full_msg = f"{status} {msg}"
        print(full_msg, file=sys.stderr)
        messages.append(full_msg)

    # Save updated state
    save_portfolio(portfolio_id, portfolio)
    save_transactions(portfolio_id, transactions)

    print(f"\n[trade_engine] Portfolio updated. Cash: ${portfolio['current_balance']:.2f}", file=sys.stderr)
    return messages


def run(portfolio_id: str, decisions: dict, prices: dict) -> list[str]:
    return apply_decisions(portfolio_id, decisions, prices)


if __name__ == "__main__":
    portfolio_id = sys.argv[1] if len(sys.argv) > 1 else "pennystock"
    sys.path.insert(0, str(Path(__file__).parent))

    if not sys.stdin.isatty():
        data = json.load(sys.stdin)
        decisions = data.get("decisions_payload", data)
        prices = data.get("prices", {})
    else:
        print("Usage: echo '{...}' | python3.11 trade_engine.py pennystock", file=sys.stderr)
        sys.exit(1)

    messages = run(portfolio_id, decisions, prices)
    for m in messages:
        print(m)
