"""Alpaca Trading extension for Sutra OS.

Drop this file into backend/app/tools/extensions/ and configure
via the Integrations page with your Alpaca API credentials.

Provides two tools:
  - alpaca_get_portfolio: Fetch account value and open positions
  - alpaca_place_order: Place stock orders (market/limit)
"""

import httpx
from langchain_core.tools import tool

EXTENSION_MANIFEST = {
    "id": "alpaca",
    "name": "Alpaca Trading",
    "description": "Fetch portfolio positions and place trades via Alpaca Markets API",
    "icon": "bar-chart-3",
    "version": "1.0.0",
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
    "tool_ids": ["alpaca_get_portfolio", "alpaca_place_order"],
    "is_dangerous": True,
}


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

    return [alpaca_get_portfolio, alpaca_place_order]


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
