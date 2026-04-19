"""Alpaca Trading extension for Sutra OS.

Drop this file into backend/app/tools/extensions/ and configure
via the Integrations page with your Alpaca API credentials.

Provides six tools:
  - alpaca_get_portfolio: Fetch account value and open positions
  - alpaca_place_order: Place simple market/limit orders (day, no brackets)
  - alpaca_get_quote: Fetch latest bid/ask/trade for any symbol
  - alpaca_place_bracket_order: Place a bracket order with take-profit + stop-loss
  - alpaca_list_orders: List open/closed orders, optionally filtered by symbol
  - alpaca_cancel_order: Cancel an open order by ID
"""

import httpx
from langchain_core.tools import tool

EXTENSION_MANIFEST = {
    "id": "alpaca",
    "name": "Alpaca Trading",
    "description": "Fetch portfolio positions, live quotes, and place trades (incl. bracket orders) via Alpaca Markets API",
    "icon": "bar-chart-3",
    "version": "1.1.0",
    "author": "Sutra Community",
    "credential_fields": [
        {"key": "api_key", "label": "API Key ID", "secret": True, "placeholder": "PK..."},
        {"key": "api_secret", "label": "Secret Key", "secret": True, "placeholder": "your-secret-key"},
    ],
    "config_fields": [
        {
            "key": "base_url",
            "label": "API Base URL",
            "secret": False,
            "placeholder": "https://paper-api.alpaca.markets",
        },
    ],
    "tool_ids": [
        "alpaca_get_portfolio",
        "alpaca_place_order",
        "alpaca_get_quote",
        "alpaca_place_bracket_order",
        "alpaca_list_orders",
        "alpaca_cancel_order",
    ],
    "is_dangerous": True,
}

_DATA_BASE = "https://data.alpaca.markets"


def create_tools(agent_id: str):
    from app.tools.extensions._helpers import get_extension_creds

    async def _get_headers() -> tuple[dict[str, str], str]:
        creds, config = await get_extension_creds("alpaca", agent_id)
        base = (config.get("base_url") or "https://paper-api.alpaca.markets").rstrip("/")
        headers = {
            "APCA-API-KEY-ID": creds["api_key"],
            "APCA-API-SECRET-KEY": creds["api_secret"],
        }
        return headers, base

    @tool
    async def alpaca_get_portfolio() -> str:
        """Get current Alpaca account value and open positions."""
        headers, base = await _get_headers()
        async with httpx.AsyncClient(timeout=15) as client:
            acct_resp = await client.get(f"{base}/v2/account", headers=headers)
            acct_resp.raise_for_status()
            pos_resp = await client.get(f"{base}/v2/positions", headers=headers)
            pos_resp.raise_for_status()

        acct = acct_resp.json()
        positions = pos_resp.json()

        lines = [
            f"Portfolio Value: ${acct['portfolio_value']}",
            f"Cash: ${acct['cash']}",
            f"Buying Power: ${acct['buying_power']}",
            "",
            "Positions:",
        ]
        if positions:
            for p in positions:
                lines.append(
                    f"  {p['symbol']}: {p['qty']} shares @ ${p['avg_entry_price']} "
                    f"(Current: ${p['current_price']}, P&L: ${p['unrealized_pl']})"
                )
        else:
            lines.append("  No open positions.")
        return "\n".join(lines)

    @tool
    async def alpaca_place_order(
        symbol: str,
        qty: int,
        side: str = "buy",
        order_type: str = "market",
        limit_price: str = "",
    ) -> str:
        """Place a stock order on Alpaca.

        Args:
            symbol: Stock ticker (e.g. AAPL, TSLA).
            qty: Number of shares.
            side: 'buy' or 'sell'.
            order_type: 'market' or 'limit'.
            limit_price: Required for limit orders (e.g. '150.00').
        """
        headers, base = await _get_headers()
        payload: dict = {
            "symbol": symbol.upper(),
            "qty": str(qty),
            "side": side,
            "type": order_type,
            "time_in_force": "day",
        }
        if order_type == "limit" and limit_price:
            payload["limit_price"] = limit_price

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{base}/v2/orders", headers=headers, json=payload)
            resp.raise_for_status()

        order = resp.json()
        return (
            f"Order placed: {order['side'].upper()} {order['qty']}x {order['symbol']} "
            f"({order['type']}) — Status: {order['status']}, ID: {order['id']}"
        )

    @tool
    async def alpaca_get_quote(symbol: str) -> str:
        """Get the latest bid / ask / last-trade price for a stock symbol.

        Uses Alpaca's market data API (IEX feed on free tier). Returns a concise
        one-line summary; the ask price is typically used as the entry basis.

        Args:
            symbol: Stock ticker (e.g. 'AAPL', 'NVDA').
        """
        headers, _ = await _get_headers()
        sym = symbol.upper()
        async with httpx.AsyncClient(timeout=15) as client:
            q_resp = await client.get(f"{_DATA_BASE}/v2/stocks/{sym}/quotes/latest", headers=headers)
            q_resp.raise_for_status()
            t_resp = await client.get(f"{_DATA_BASE}/v2/stocks/{sym}/trades/latest", headers=headers)
            t_resp.raise_for_status()

        quote = q_resp.json().get("quote", {}) or {}
        trade = t_resp.json().get("trade", {}) or {}
        bid = quote.get("bp")
        ask = quote.get("ap")
        last = trade.get("p")
        when = trade.get("t") or quote.get("t") or "?"
        return (
            f"{sym}: bid=${bid} ask=${ask} last=${last} at {when}"
        )

    @tool
    async def alpaca_place_bracket_order(
        symbol: str,
        qty: int,
        take_profit_price: str,
        stop_loss_price: str,
        side: str = "buy",
    ) -> str:
        """Place a bracket order with attached take-profit (limit) and stop-loss (stop) legs.

        The primary market order executes immediately; once filled, the two child
        legs become active as an OCO pair — whichever triggers first cancels the other.
        Orders are submitted with time_in_force=gtc (required for brackets).

        Args:
            symbol: Stock ticker (e.g. 'AMD').
            qty: Number of shares for the primary leg.
            take_profit_price: Target limit price as string, e.g. '279.24'.
            stop_loss_price: Stop-loss stop price as string, e.g. '241.16'.
            side: 'buy' or 'sell' for the primary leg. Default 'buy'.
        """
        headers, base = await _get_headers()
        payload = {
            "symbol": symbol.upper(),
            "qty": str(qty),
            "side": side,
            "type": "market",
            "time_in_force": "gtc",
            "order_class": "bracket",
            "take_profit": {"limit_price": str(take_profit_price)},
            "stop_loss": {"stop_price": str(stop_loss_price)},
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{base}/v2/orders", headers=headers, json=payload)
            resp.raise_for_status()
        order = resp.json()
        return (
            f"Bracket placed: {order['side'].upper()} {order['qty']}x {order['symbol']} "
            f"TP=${take_profit_price} SL=${stop_loss_price} — "
            f"Status: {order['status']}, ID: {order['id']}"
        )

    @tool
    async def alpaca_list_orders(
        symbols: str = "",
        status: str = "open",
        limit: int = 50,
    ) -> str:
        """List orders, optionally filtered by symbol(s) and status.

        Returns nested bracket legs inline so the child take-profit / stop-loss
        legs are visible for reconciliation.

        Args:
            symbols: Comma-separated list of symbols (e.g. 'AMD,NVDA'). Empty = all.
            status: 'open', 'closed', or 'all'. Default 'open'.
            limit: Max orders to return (Alpaca cap 500). Default 50.
        """
        headers, base = await _get_headers()
        params: dict = {"status": status, "limit": str(limit), "nested": "true"}
        if symbols:
            params["symbols"] = symbols.upper()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{base}/v2/orders", headers=headers, params=params)
            resp.raise_for_status()
        orders = resp.json() or []
        if not orders:
            return f"No {status} orders."

        def _fmt(o: dict, indent: str = "") -> str:
            limit_p = o.get("limit_price") or "-"
            stop_p = o.get("stop_price") or "-"
            klass = o.get("order_class") or ""
            tag = f" [{klass}]" if klass else ""
            return (
                f"{indent}{o['id']}: {o['side'].upper()} {o['qty']}x {o['symbol']} "
                f"type={o['type']}{tag} limit={limit_p} stop={stop_p} status={o['status']}"
            )

        lines = [f"{len(orders)} {status} order(s):"]
        for o in orders:
            lines.append(_fmt(o))
            for leg in o.get("legs") or []:
                lines.append(_fmt(leg, indent="    └─ "))
        return "\n".join(lines)

    @tool
    async def alpaca_cancel_order(order_id: str) -> str:
        """Cancel an open order by its Alpaca order ID.

        Cancelling a bracket parent cancels its child legs too. Returns a short
        status string. 404 means the order was already filled/cancelled.

        Args:
            order_id: The Alpaca order UUID to cancel.
        """
        headers, base = await _get_headers()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(f"{base}/v2/orders/{order_id}", headers=headers)
        if resp.status_code in (204, 207):
            return f"Order {order_id} cancelled."
        if resp.status_code == 404:
            return f"Order {order_id} not found (already filled or cancelled)."
        return f"Order {order_id}: HTTP {resp.status_code} — {resp.text[:200]}"

    return [
        alpaca_get_portfolio,
        alpaca_place_order,
        alpaca_get_quote,
        alpaca_place_bracket_order,
        alpaca_list_orders,
        alpaca_cancel_order,
    ]


async def test_connection(creds: dict, config: dict) -> dict:
    """Test Alpaca credentials by fetching account info."""
    base = (config.get("base_url") or "https://paper-api.alpaca.markets").rstrip("/")
    url = f"{base}/v2/account"
    headers = {
        "APCA-API-KEY-ID": creds.get("api_key", ""),
        "APCA-API-SECRET-KEY": creds.get("api_secret", ""),
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
        data = resp.json()
        return {
            "ok": True,
            "detail": f"Connected: Account {data.get('account_number', 'unknown')} (${data.get('portfolio_value', '?')})",
        }
    except httpx.HTTPStatusError as e:
        return {"ok": False, "detail": f"Alpaca API error — HTTP {e.response.status_code}: {e.response.text[:200]} (URL: {url})"}
    except Exception as e:
        return {"ok": False, "detail": f"Connection failed: {e} (URL: {url})"}
