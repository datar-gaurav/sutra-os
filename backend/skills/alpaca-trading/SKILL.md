---
name: Alpaca Trading
slug: alpaca-trading
description: |
  Load when the user provides stock trading recommendations and wants positions
  sized and bracket orders placed on the Alpaca paper-trading account.
icon: TrendingUp
color: "#22c55e"
version: 2.1.0
category: trading
tools:
  - alpaca_get_portfolio
  - alpaca_get_quote
  - alpaca_place_bracket_order
  - alpaca_place_order
  - alpaca_list_orders
  - alpaca_cancel_order
config_schema:
  type: object
  properties:
    risk_pct:
      type: number
      default: 0.05
    concentration_cap_pct:
      type: number
      default: 0.20
    cash_reserve_pct:
      type: number
      default: 0.15
    price_deviation_cap:
      type: number
      default: 0.01
---

**Paper trading only.** Never claim real execution. You are not a financial advisor — you mechanically apply the rules below.

Risk config: risk_pct={risk_pct}, concentration_cap_pct={concentration_cap_pct}, cash_reserve_pct={cash_reserve_pct}, price_deviation_cap={price_deviation_cap}.

Input format (one rec per line):
```
Symbol | Buy | Target | Stop | Reason
AMD    | 253.85 | 279.24 | 241.16 | Long; semi momentum
```

Workflow:
1. `alpaca_get_portfolio()` once. Compute `deployable_cash`, `max_per_position`, `risk_budget`. If `deployable_cash ≤ 0`, place nothing and explain.
2. For each rec: `alpaca_get_quote(symbol)`. Skip if price has moved beyond `price_deviation_cap` or if R:R denominator ≤ 0. Sort survivors by R:R descending.
3. Size positions per `references/sizing.md`. Deduct deployed capital from running `deployable_cash` as you go.
4. `alpaca_place_bracket_order(...)` for each sized trade. On failure: `references/error-handling.md`.
5. Reconcile existing positions — if bracket legs differ from the new rec, cancel + replace with sell-side bracket. If they match, mark `HOLD`.
6. Emit the final summary using `assets/summary_template.md`.

**Safety rules (non-negotiable):**
- Never exceed `concentration_cap_pct` of equity in one symbol (including existing holdings).
- Never deploy cash below the `cash_reserve_pct` reserve.
- Never submit a bracket entry without both stop-loss and take-profit.
- Never chase price beyond `price_deviation_cap`.

## Gotchas
