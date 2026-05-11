# Trade Run Summary

Emit as the final assistant message. Use a monospace code block.

```
Symbol  Action          Shares  Entry    Target   Stop     R:R   Est. Cost  Status
AMD     BUY               24    253.85   279.24   241.16   2.00  6092.40    FILLED
NVDA    ADD               10    132.10   145.00   122.00   1.27  1321.00    ACCEPTED
TSLA    UPDATE BRACKET    50    —        320.00   240.00   —     —          ACCEPTED
MSFT    HOLD              30    —        —        —        —     —          AT CAP
META    SKIP               0    —        —        —        —     —          PRICE MOVED
```

Then a footer:

```
Total Equity:        $103,500
Cash Before:         $42,300
Cash After:          $34,886.60
Cash Reserve (15%):  $15,525
Positions Held:      8
New Trades:          2
Updated Brackets:    1
Skipped:             2
```

Valid `Action`: BUY, ADD, UPDATE BRACKET, HOLD, SKIP
Valid `Status`: FILLED, ACCEPTED, PENDING, AT CAP, NO CAPITAL, PRICE MOVED, MALFORMED, ERROR — &lt;msg&gt;
