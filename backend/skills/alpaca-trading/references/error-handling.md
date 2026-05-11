# Error Handling

## alpaca_get_quote fails
Retry up to twice. On third failure, skip the symbol with `ERROR — quote unavailable`. Do not invent a price from the recommendation's buy_price; the rec might be stale.

## alpaca_place_bracket_order rejected — insufficient buying power
Reduce `final_shares` by 10% and retry once. If it still fails, skip with `ERROR — buying power`.

## alpaca_place_bracket_order rejected — other reason
Skip with `ERROR — <message from API>`. Do not retry on validation errors (bad price format, market closed, etc.).

## alpaca_cancel_order fails during reconciliation
Log the order ID and the new desired bracket but do not place the replacement — leaving stale + new brackets simultaneously is worse than doing nothing. Report `RECONCILE ERROR — cancel failed`.

## Time-in-force
All bracket orders are submitted with `time_in_force=gtc` so they survive across sessions. Don't change this.
