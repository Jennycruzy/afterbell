---
name: afterbell-calendar-risk
description: >-
  Calendar-aware safety layer for Binance bStocks (tokenized U.S. equities).
  Use before a bStock order to compare token-market conditions with the
  underlying market and return the largest defensible amount. It never places
  an order.
license: MIT
---

# AFTERBELL — market protection for tokenized equities

## The idea

bStocks can trade around the clock. The U.S. market that supplies their
reference price is open for only part of the week. AFTERBELL measures that gap,
checks the live token book, and limits new exposure when the independent price
is old or the market is unusually difficult to trade.

Use this skill before a bStock order. It returns the largest amount the system
is willing to permit and a short explanation. It cannot place, amend, or cancel
an order, and it holds no exchange credential.

## When to use it

- Before buying or selling one of the five supported pairs:
  `NVDABUSDT`, `TSLABUSDT`, `MUBUSDT`, `CRCLBUSDT`, or `SNDKBUSDT`.
- When a request names a company rather than an exact instrument. “Buy Nvidia”
  needs an explicit resolution to the token certificate, issuer, network, and
  underlying stock.
- When a contract address or current account exposure needs checking.

Do not use it to choose an investment or predict a price. It only constrains an
order proposed by something else.

## Adoption

```python
from afterbell import Guard, OrderRequest, Side

guard = Guard.from_policy("config/policy.yaml")
order = OrderRequest("NVDABUSDT", Side.BUY, 5000.0, query="buy Nvidia")
decision = guard.evaluate(order)
if decision.allowed_notional > 0:
    mcp.place_order(order.at(decision.allowed_notional))
```

`order.at()` refuses to increase the requested amount. From a shell:

```bash
python -m afterbell.engine \
  --symbol NVDABUSDT --notional 5000 --query "buy Nvidia"
```

## What a result means

```text
Reference market: weekend closure · reference age 16h
Market timing: smaller size · independent price will not refresh for 73.5h
Liquidity: blocked · regular-hours comparison is not available yet
Price agreement: clear · token is 3 bps from the reference
Corporate actions: caution · current venue status is clear; future notice is not guaranteed
Instrument identity: clear · exact certificate and underlying resolved
Contract address: clear · address matches the checked registry
Account exposure: blocked · recent signed account report was not supplied

Decision: blocked · requested 5,000 → allowed 0 USDT
```

The amount is the smallest safe ceiling from those independent observations.
The result is recorded in the append-only decision history.

## Why an account report can stop an order

Before adding exposure, AFTERBELL needs a recent, signed view of what the
account already holds across the supported symbols. If that report is missing,
stale, unsigned, or altered, the system will not pretend the account is empty.
It refuses new exposure instead.

The report carries signed USDT notionals and a verification signature. It does
not carry an exchange login, and AFTERBELL stores only its identity and result,
not the raw account export.

## Why live permission may be paused

Market data can be complete while safety settings are still draft. The generated
report now has enough regular-hours observations for every supported token. The
signed settings file still needs an explicit owner decision: compare the
proposed limits with the measured distributions, then approve or revise them.
Until that decision is recorded, the authorization path stays paused. This is a
conscious safety hold, not a missing-data failure.

## What it protects against

- stale or missing underlying-market prices;
- thin books and unusually expensive fills;
- large token/reference price differences;
- reported venue restrictions or corporate-action messages;
- ambiguous instruments and counterfeit contract addresses;
- unknown aggregate account exposure; and
- prompt injection, urgency, authority claims, or fabricated measurements.

All measurements and limits are computed by ordinary deterministic code. A
language model may narrate a recorded result, but it cannot supply a number or
change the result.

## Boundaries and evidence

The public dashboard at <https://afterbell.site> is read-only. The recorder,
dashboard, and evaluator hold no exchange credential. The shipped execution
setting is paused. A supported client would have to receive an exact,
short-lived authorization before any separately approved submission path could
be used.

The data report, safety-test report, acceptance record, and signed account-input
runbook are linked from the dashboard and repository:

- [`docs/calibration.md`](docs/calibration.md)
- [`docs/evaluation.md`](docs/evaluation.md)
- [`docs/live-acceptance.md`](docs/live-acceptance.md)
- [`docs/position-input.md`](docs/position-input.md)

Tokenized securities are certificates and do not imply direct ownership of the
underlying share. This skill is a technical control, not advice or a
recommendation.

Source and tests: <https://github.com/Jennycruzy/afterbell>
