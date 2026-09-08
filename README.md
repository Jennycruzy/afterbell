# AFTERBELL

> **The stock sleeps. The token doesn't.**

AFTERBELL is a practical safety layer for tokenized U.S. equities. It watches the
always-open token market, compares it with the hours and condition of the
underlying stock market, and gives an agent a defensible maximum order size.

It does not predict prices. It does not choose trades. It does not hold an
exchange credential. It makes the dangerous moments visible and makes unsafe
size impossible to approve by accident.

## See the product

**Live dashboard:** <https://afterbell.site>

The public dashboard is deliberately operational rather than decorative. In
one screen it shows the live reference age, price difference, liquidity,
account-exposure evidence, the reason an amount was allowed or refused, the
recorded decision history, backup health, and the data behind the limits.

The dashboard monitors conditions and sizes requests; it does not place an order.

## The problem

A tokenized share can trade 24 hours a day. The U.S. stock it references cannot:
it trades during regular weekday sessions and then stops updating. A token can
therefore keep moving for a weekend or holiday while the most recent independent
stock price becomes older and older.

A normal order-size check misses that time gap. AFTERBELL treats it as a first-
class risk input:

> **The longer the reference market has been quiet, the less new exposure the
> system is willing to approve.**

The same idea also applies when the token book becomes thin, the token and
reference price disagree, the instrument cannot be identified exactly, or the
current account position is unknown.

## What happens when a request arrives

1. The request is resolved to one of the five supported token pairs.
2. AFTERBELL reads the recorded token book, the last regular-hours reference
   price, the market calendar, and the instrument registry.
3. It checks timing, liquidity, price agreement, corporate-action status,
   instrument identity, contract address, and current account exposure.
4. It returns a clear result and an amount no larger than the request: clear,
   caution, smaller size, or blocked.
5. It writes a tamper-evident receipt containing the measurements and the exact
   safety-settings fingerprint used for that decision.

Every number comes from ordinary deterministic code. A language model can
explain a result, but it cannot choose a price, threshold, amount, or outcome.

## Current live checkpoint

This is the state observed on **8 September 2026 UTC**; the dashboard is the
live source for changing counters and timestamps.

| What a reviewer can verify | Current state |
|---|---|
| Supported instruments | 5 token pairs with checked registry entries |
| Measured books / reference prints | 39,365 / 35,520 in the published data report |
| Normal-hours data coverage | 781 observations per token; 300 required |
| Holiday data coverage | 1,440 observations per token |
| Recorded decisions | 6,600+ live receipts |
| Order limit | $5,000 base request; market checks can reduce it |
| Current decision | $0 allowed because a recent signed account-position report was not supplied |
| Data archive | Live and updating |
| Python-side exchange credentials | None |

The zero amount is not a market prediction. It means AFTERBELL cannot safely
measure existing account exposure, so it refuses to assume the account is empty.

## Configure the order limit

The dashboard shows the current maximum for one request. Set
`base_notional_usdt` in [`config/policy.yaml`](config/policy.yaml) when you
want a different maximum. The market checks can always choose a smaller amount
when timing, liquidity, price agreement, instrument identity, or account
exposure calls for caution.

This keeps the important choice visible: the configured amount is the starting
point, and the measured market decides whether the request can use all of it.

## The seven plain-language checks

| Check | Question it answers |
|---|---|
| Market timing | How old is the reference, and how long until the underlying market can print again? |
| Liquidity | Can the requested amount be filled without an unusually expensive or thin book? |
| Price agreement | How far apart are the token and the latest independent reference price? |
| Corporate-action status | Does the venue report a current restriction or processing message? |
| Instrument identity | Is this the exact certificate, issuer, network, and underlying the request names? |
| Contract address | Does the address match the checked canonical registry? |
| Account exposure | Do we have a recent, trusted view of current holdings before adding more? |

The checks produce independent ceilings. The permitted amount is the smallest
of them, never a product of several uncertain estimates. A single unknown that
could make the request unsafe can reduce the amount to zero.

## Why the account report matters

The account-exposure check is simple to explain: before adding a new position,
the system must know what the account already holds across the supported
symbols. A recent signed position report supplies that fact without giving
AFTERBELL an exchange login.

If the report is missing, stale, unsigned, or altered, the safe answer is not
“the account is empty.” The safe answer is “I cannot measure this request,” and
new exposure is refused. The public dashboard calls this **required account
report missing** and explains the consequence directly.

The report contains signed USDT notionals, not credentials. The raw positions
are not written into public receipts; only the report identity and verification
result are retained.

## Why the design is trustworthy

- **Deterministic:** measurements and decisions are produced by ordinary code,
  not generated by a model.
- **Conservative:** missing reference data, missing liquidity data, an
  unknown instrument, an unsafe status, or missing account evidence cannot
  silently become a clear result.
- **Traceable:** every decision and refusal enters an append-only, hash-linked
  receipt ledger.
- **Credential-separated:** the recorder, dashboard, and evaluator hold no
  exchange credential. The dashboard only measures and explains requests.
- **Hard to persuade:** the signed settings file is loaded independently of the
  request text. Urgency, authority claims, fabricated prices, and prompt
  injection cannot raise an amount.
- **Observable:** the public dashboard shows both normal outcomes and refusals,
  plus the data age and integrity identifiers needed to interpret them.

## Evidence, not marketing

The current generated safety report records:

- 35 hostile request patterns tested against two market states;
- zero hostile inputs that raised the permitted amount above its control;
- 6/6 positive controls, demonstrating that the suite cannot “succeed” by
  refusing every request;
- 99 of 100 normal-book requests permitted at full requested size;
- a measured 1.00% refusal rate inside that specifically defined normal-book
  cohort; and
- six recorder and measurement issues found by the project's own tooling
  and then fixed.

The 1.00% figure is not a claim about all order flow. The monitor repeatedly
probed the same 5,000 USDT request once a minute. The definition and exclusions
are published in [`docs/evaluation.md`](docs/evaluation.md).

The counterparty-composition question is intentionally not given a direction:
historical trade capture was uneven before the recorder fix, so the honest
result is “not enough balanced evidence yet.” The limitation is documented in
[`docs/counterparty.md`](docs/counterparty.md).

## Architecture in one glance

```text
recorded token books + reference prices + exchange calendar
                              │
                              ▼
             deterministic measurements and instrument checks
                              │
                              ▼
             smallest safe amount + plain-language explanation
                              │
                              ▼
                 recorded decision + order limit
                              │
                              ▼
                   hash-linked receipt ledger
```

The recorder runs separately from the dashboard and has no credential. The
public MCP surface exposes evaluation and market-state tools. The dashboard
shows the current order limit and cannot place an order.

## Run it locally

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m afterbell.engine \
  --symbol NVDABUSDT --notional 5000 --query "buy Nvidia"
```

Use the package as a small boundary around an existing agent:

```python
from afterbell.engine import Guard
from afterbell.guard import OrderRequest
from afterbell.measure import Side

guard = Guard.from_policy("config/policy.yaml")
decision = guard.evaluate(
    OrderRequest("NVDABUSDT", Side.BUY, 5000.0, query="buy Nvidia")
)
print(decision.allowed_notional, decision.rationale)
```

The public MCP endpoint provides `evaluate_order` and `get_market_state`.
The public dashboard and MCP server do not place an order.

## Read next

- [Live dashboard](https://afterbell.site) — the fastest way to see the system.
- [`docs/calibration.md`](docs/calibration.md) — measured market baselines and
  price-difference distributions.
- [`docs/evaluation.md`](docs/evaluation.md) — safety-test definitions and
  generated results.
- [`docs/live-acceptance.md`](docs/live-acceptance.md) — the one recorded,
  recorded minimum-size acceptance event.
- [`docs/position-input.md`](docs/position-input.md) — how a supported client
  supplies a signed account-position report without sharing credentials.
- [`docs/submission-checklist.md`](docs/submission-checklist.md) — evidence that
  is ready and work that still needs an external destination.
- [`STATUS.md`](STATUS.md) — current operations and known limitations.

## Important boundaries

AFTERBELL is a technical demonstration, not investment advice, an offer, a
solicitation, or a claim of direct ownership of an underlying share. Tokenized
securities are certificates with risks distinct from the securities they
reference.

The corporate-action signal is a live current-status check. It does not claim
guaranteed advance notice of every future event. Backup verification confirms
stable files at a checked point; it is not an atomic remote snapshot of hot
files. The underlying U.S. market calendar and the public token venue can both
change, so the timestamps and source links on the dashboard matter.

## License

MIT. Technical demonstration only.
