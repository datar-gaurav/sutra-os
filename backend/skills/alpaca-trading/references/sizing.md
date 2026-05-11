# Position Sizing

For each recommendation, after the price-deviation and R:R filters:

```
# Equity-level setup (computed once from portfolio)
total_equity      = portfolio_value
deployable_cash   = cash - (total_equity * cash_reserve_pct)
max_per_position  = total_equity * concentration_cap_pct
risk_budget       = total_equity * risk_pct
basis_price       = current_ask    # from alpaca_get_quote
```

## If symbol already held
```
existing_value      = qty * current_price
remaining_alloc     = max_per_position - existing_value
```
If `remaining_alloc <= 0`: `SKIPPED — at concentration cap`.

## If new symbol
```
remaining_alloc     = max_per_position
```

## Compute share count
```
risk_per_share       = buy_price - stop_loss
shares_by_risk       = floor(risk_budget / risk_per_share)
shares_by_allocation = floor(remaining_alloc / basis_price)
shares_by_cash       = floor(deployable_cash / basis_price)
final_shares         = min(shares_by_risk, shares_by_allocation, shares_by_cash)
```
If `final_shares <= 0`: `SKIPPED — insufficient capital or allocation`.

## Update running state
After each successful sizing:
```
deployable_cash -= final_shares * basis_price
```
The next rec sees the reduced cash.
