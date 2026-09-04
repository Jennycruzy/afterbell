---
name: afterbell-calendar-risk
description: >-
  Calendar-aware risk boundary for Binance bStocks (tokenized US equities).
  Use before placing any bStock order to size it against how long the
  reference market has been shut. Returns PASS, WARN, REDUCE or BLOCK with a
  permitted notional and a signed receipt. It never places an order.
license: MIT
---

# AFTERBELL — a calendar-aware risk boundary for bStocks

## What this is for

bStocks trade 24/7. The market that prices them is open about 32.5 hours a
week. Between Friday's closing bell and Tuesday's open over a holiday weekend
there are roughly **89 hours** during which a tokenized share keeps trading
against a reference price that stopped updating.

Most agent risk checks ask *how big is this order*. This one asks *how long has
it been since anyone independently priced this thing*, and sizes accordingly.

Use this skill before any bStock order. It reads the order, measures the
market, and returns the largest notional it is willing to permit. It cannot
place, amend or cancel an order, and it holds no exchange credential.

## When to use it

- Before submitting any buy or sell of a bStock pair (`NVDABUSDT`, `TSLABUSDT`,
  `MUBUSDT`, `CRCLBUSDT`, `SNDKBUSDT`).
- When a user request names a company rather than an instrument — "buy Nvidia"
  is a category error this skill resolves explicitly, because what is
  purchasable is a certificate issued by a Binance affiliate, not the share.
- When a token is delivered on-chain and a contract address needs checking
  against the canonical registry.

Do **not** use it to decide *whether* to trade or *what* to trade. It expresses
no view on price and produces no signal. It only constrains an order that
something else already proposed.

## Adoption

Four lines around an existing agent, with the trading logic untouched:

```python
from afterbell import Guard, OrderRequest, Side

guard = Guard.from_policy("config/policy.yaml")
order = OrderRequest("NVDABUSDT", Side.BUY, 5000.0, query="buy Nvidia")
decision = guard.evaluate(order)
if decision.allowed_notional > 0:
    mcp.place_order(order.at(decision.allowed_notional))
```

`order.at()` refuses to resize upward. The guard never permits more than was
requested, and that path is not allowed to become the exception.

From a shell:

```
python -m afterbell.engine --symbol NVDABUSDT --notional 5000 --query "buy Nvidia"
```

## What it returns

```
  TOKEN MARKET  OPEN            REFERENCE MARKET  CLOSED_WEEKEND
                                REFERENCE_AGE     16:00:00

    Market closure  REDUCE  f=0.060  reference market CLOSED_WEEKEND; 73.5h until the next regular print (extended closure)
    Liquidity       BLOCK   f=0.000  no calibrated RTH baseline for this symbol (0 samples, 300 required)
    Price agreement PASS    f=1.000  token -3bps against a reference 16:00:00 old [NOMINAL]
    Corporate action WARN    f=1.000  Binance processing status TRADING verified; advance notice is not guaranteed
    Instrument ID    PASS    f=1.000  NVDAB resolved to NVDA via BTech Holdings Limited
    Contract check   PASS    f=1.000  venue-internal spot pair; canonical registry applies

  DECISION  BLOCK     requested 5,000 -> allowed 0 USDT
  BINDING   market closure, liquidity
```

This is the output shape for a Saturday evaluation before the RTH baseline has
reached its required sample count. The liquidity check blocks until that denominator is measured.
Note that the two clock numbers are
different measurements and are not interchangeable: `REFERENCE_AGE` 16:00:00 is
how stale the last print already is, while 73.5h is how long until the next
one. The market-closure check takes the worse of them. Here the darkness *ahead* binds, because Labor
Day falls on the Monday.

`decision.allowed_notional` is the number to act on. `decision.rationale` is the
text of record. Every evaluation — including every refusal — appends a
hash-chained receipt carrying the policy checksum that produced it.

## The six protections

| | Asks |
|---|---|
| **Market closure** | How long has the reference market been shut, and how long until it reopens? |
| **Liquidity** | How does this book compare to its *own* regular-hours median spread and depth? |
| **Price agreement** | Do the token and its reference disagree, and how old is the reference? |
| **Corporate-action status** | Does Binance report a processing restriction or corporate-action message? |
| **Instrument identity** | What is this, exactly — issuer, instrument class, network, underlying? |
| **Contract verification** | Is this contract address the canonical one? |

Factors combine by `min()`, never by product. Multiplying them would invent a
precision the measurements do not have, and would let three merely-cautious
signals compound into a block no single measurement supports.

## What it cannot do

- **The guard cannot place, amend or cancel an order.** Its result space
  is PASS, WARN, REDUCE, BLOCK plus a permitted notional never larger than the
  request. The action space is provably risk-reducing, which is what makes it
  safe to grant autonomy to. A separate module, `afterbell.executor`, can place
  an order and ships disabled; it cannot originate one, only shrink one the
  guard already permitted, under a hand-set cap and a symbol allowlist.
- **It cannot be talked out of a limit.** Thresholds live in a checksummed file
  on disk, loaded at startup. There is no argument, no keyword and no request
  field that raises one. This is tested, not asserted: `python -m
  afterbell.adversary` runs 35 attacks — instruction injection, claimed
  authority, urgency, fabricated market data, credential extraction, counterfeit
  contracts, resolution evasion — against a single market snapshot, and the
  invariant is that none of them ever raises permitted size above the control.
- **It cannot invent a missing input.** A reference price that will not fetch, a
  book that will not measure, an unrecognised pair status — each halts the
  affected path and blocks. A missing reference is never treated as agreement.
- **It cannot fire Binance's Emergency Stop**, which is a manual web-UI action.
  It refuses, sizes down and notifies at its own layer only.
- **It does no arithmetic with a language model.** Every number is computed from
  measured inputs. A model may narrate a receipt; it cannot change one.

## Configuration

`config/policy.yaml` holds every threshold and is checksummed at load; its
SHA-256 travels into every receipt so a reader can tell which rules produced a
given decision. The loader refuses to start on a missing market state or a
sizing factor above 1.0.

Thresholds are measured, not invented — `python -m afterbell.calibrate`
publishes the table with a sample count beside every number, and reports
`UNCALIBRATED` rather than printing a statistic it lacks the samples for.

Yahoo is the default reference-price provider and needs no credential. Alpaca
can be selected for reference prices with `REFERENCE_PROVIDER=alpaca`, but it
does **not** power corporate-action protection. **Corporate-action protection is
Binance-native:** it checks public bStocks processing status and reason messages,
blocks a reported restriction, and marks a clear current status as partial
because Binance does not guarantee advance notice. Alpaca is never silently
substituted for Yahoo, and the recorder and safety evaluator hold no Binance or
Alpaca credential.

## Status and honesty

- Contract addresses come from a checked-in registry hashed at load.
- The instrument registry covers the five launch bStocks only.
- Binance's public bStocks status path is live-checked; an unsupported public
  token audit is recorded as registry-only rather than as a clean audit.
- **Corporate-action protection is a Binance-native current-status check, not an Alpaca lookahead.** A reported processing restriction blocks a new entry. Because Binance does not guarantee advance notice, a clear status remains explicit partial protection rather than a future-event clearance.
- Adversarial payloads used to test this skill are synthetic, self-contained,
  and never published anywhere a third party's agent could encounter them.
- bStocks are **Certificates representing Financial Instruments** (para 92,
  Sch 1 FSMR) and confer no direct ownership of the underlying share. This
  skill never implies otherwise, and never offers advice, a recommendation or a
  solicitation.

Source, tests and the full write-up: <https://github.com/Jennycruzy/afterbell>
