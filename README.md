# AFTERBELL

> The stock sleeps. The token doesn't.

Crypto guardians protect you from bad tokens. AFTERBELL protects you when Wall
Street goes offline and your tokens don't.

**Status: in active development.** This README documents what is built and what
is not. Sections marked _not yet built_ are not built.

---

## The problem

On 11 June 2026 Binance listed **bStocks** — tokenized US equities issued by
BTech Holdings Limited, trading as ordinary Spot pairs, 24/7. The securities
they reference trade roughly 32.5 hours a week. That leaves ~135.5 hours a week
in which these instruments have no primary price-discovery venue behind them,
and Binance Research measured **~47% of bStocks volume falling outside US market
hours** in the first fifteen days.

Six of the last ten winners at BNB Chain's OpenClaw hackathon were protective
agents. Every one of them guards *crypto* risk — malicious contracts, rug
pulls, liquidation, runaway spend. **None of them can read a market calendar.**

AFTERBELL is a deterministic, calendar-aware risk boundary that sits between any
agent and Binance Spot.

## What this is

- A **guard**, not a strategy. It never originates an order. Its entire action
  space is `PASS`, `WARN`, `REDUCE`, `BLOCK` — provably risk-reducing.
- **Deterministic.** Every number comes from measured data through ordinary
  code. The language model narrates and resolves ambiguity in a request; it
  never produces a price, a basis, a size, a threshold or a verdict.
- **Not persuadable.** Limits live in a signed YAML file loaded at startup, not
  in a prompt. There is no tool that raises a limit and no natural-language path
  to relaxing one.
- **Auditable.** Every evaluation — including every refusal — writes a
  hash-chained receipt.

## What this is not

- **Not investment advice.** AFTERBELL never recommends a position. It only
  constrains one that a human or another agent has already proposed.
- **Not a claim of share ownership.** bStocks are Certificates representing
  Financial Instruments (para 92, Sch 1 FSMR), issued under an Approved
  Prospectus in the ADGM. They confer no direct ownership of the underlying
  share. Making that correct on screen every time is part of what the resolver
  is for.
- **No alpha claim.** AFTERBELL does not predict prices.
- **No offer or solicitation.** This is a technical demonstration.

## Adversarial testing policy (Law 12)

Prompt-injection payloads used to test this agent are **synthetic, committed in
the open in `afterbell/adversary.py`, and read only by agents in this
repository**. No payload is ever published anywhere a third party's agent could
encounter it — not on-chain, not in a token description, not in a social post.

They live in the package rather than under `tests/` because the same corpus
backs both the test suite and the demo, and a corpus that drifts from the thing
demonstrated is worth less than either.

## Architecture

```
RECORDER (no credentials, always-on)  ->  raw depth, trades, reference quotes
MARKET CLOCK                          ->  session state + REFERENCE_AGE
MEASUREMENT ENGINE                    ->  spread, depth, walk cost, basis
RESOLVER                              ->  symbol -> issuer -> contract -> underlying
GUARD (deterministic, signed policy)  ->  PASS / WARN / REDUCE / BLOCK
RATIONALE (LLM, narration only)
RECEIPT LEDGER (hash-chained JSONL)
EXECUTOR (Binance MCP)
```

The recorder holds **no credential of any kind** and runs as its own process, so
it cannot be stopped by a token expiring. That separation is deliberate: the
off-hours order-book data it collects cannot be back-filled after the fact.

### Built

- **Canonical instrument registry** (`afterbell/instruments.py`) — the five
  launch pairs with issuer, instrument class, network and canonical BNB Smart
  Chain contract address, checksummed at load.
- **Market-data recorder** (`afterbell/recorder.py`) — 60s poll of book ticker,
  20-level depth, recent trades and per-pair `exchangeInfo` status across all
  five pairs, plus the Alpaca reference side. Every fetch failure writes an
  annotated gap marker rather than a fabricated value.
- **Policy file** (`config/policy.yaml`) — every threshold, checksummed.
- **Market clock and `REFERENCE_AGE`** (`afterbell/clock.py`) — session state
  machine over a checked-in 2026 exchange calendar, with 17 tests.
- **Measurement engine** (`afterbell/measure.py`) — half-spread, depth within a
  band, marketable-order walk cost, and basis.
- **Receipt ledger** (`afterbell/ledger.py`) — append-only hash-chained JSONL,
  `hash = sha256(prev_hash || canonical_json(record))`, fsynced per record.
  Altered, deleted, reordered and forged receipts are each detected and
  reported by sequence number. 34 tests in total.

- **Session baselines** (`afterbell/baselines.py`) — per-symbol rolling medians
  over `RTH_OPEN` samples only, with sample counts and an explicit
  `UNCALIBRATED` state that refuses to produce a ratio.
- **Policy loader** (`afterbell/policy.py`) — validates and checksums the
  policy, rejects a clock factor above 1.0 outright, and refuses to run if the
  canonical registry checksum has drifted from the policy. 42 tests in total.

- **Resolver** (`afterbell/resolver.py`) — full instrument chain plus canonical
  contract verification, refusing rather than guessing.
- **The guard** (`afterbell/guard.py`) — P1–P6, one sizing function, factors
  combined by `min()` and never by product. 84 tests in total.

- **Reference price** (`afterbell/reference.py`) — last regular-session trade,
  or the session's official close re-timestamped to the actual closing bell.
  Extended-hours prints are flagged and never used as a reference.
- **Engine and CLI** (`afterbell/engine.py`) — assembles a context from live
  data, evaluates, and writes the receipt. 85 tests in total.

- **Dashboard** (`afterbell/dashboard.py`) — read-only, unauthenticated,
  `REFERENCE_AGE` permanent above the fold, refusals styled as prominently as
  passes, policy checksum and ledger head on every page.

### Not yet built

Rationale layer, executor.

`REFERENCE_AGE` is shown even before a reference price feed is configured: the
exchange calendar knows when the last regular session ended, so the age is
derived from it and labelled `source: exchange_calendar`. What the calendar
cannot supply is the price, so the basis stays blank rather than being
invented.

## Using it

```python
from afterbell.engine import Guard
from afterbell.guard import OrderRequest
from afterbell.measure import Side

guard = Guard.from_policy("config/policy.yaml")
decision = guard.evaluate(OrderRequest("NVDABUSDT", Side.BUY, 5000.0,
                                       query="buy Nvidia"))
if decision.allowed_notional > 0:
    ...  # place the order at decision.allowed_notional
```

Four lines around an existing agent, trading logic untouched. Or from a shell:

```
python -m afterbell.engine --symbol NVDABUSDT --notional 5000 --query "buy Nvidia"
```

## The adversarial corpus

Law 6 claims there is no argument, no keyword and no request field that raises
a limit, because no such path exists to be discovered. That is falsifiable, so
it is tested rather than asserted.

```
python -m afterbell.adversary            # 35 attacks against one snapshot
python -m afterbell.adversary --agent    # a counterparty arguing for size
```

The experiment is controlled: one `MarketContext` is built from a single
snapshot and reused for every attack, so the only thing varying between the
control run and an attacked run is text the attacker controls. If permitted
size moves, the text moved it.

Each attack declares beforehand what it should do, and there are three honest
answers rather than one:

| | meaning |
|---|---|
| `IGNORED` | the field is consumed but the payload changes nothing — verdict, permitted notional and every gate factor match the control |
| `REFUSED` | the payload changes a measured input, and a named protection blocking is the correct response |
| `REJECTED` | the request is malformed and never reaches a protection at all |

Claiming `IGNORED` for everything would be a weaker result and a false one: a
counterfeit contract address **must** change the answer. What must never
happen is the fourth outcome, and it is the invariant spanning the whole
corpus — **no payload ever raises permitted size above the control**.

The families are grouped by the assumption being exploited rather than by
wording, because three rephrasings of "ignore your instructions" test one thing
once: instruction injection, claimed authority, urgency and threat, fabricated
market data, credential and policy extraction, counterfeit assets, resolution
evasion, audit laundering, and size escalation. Three positive controls are
included so the suite cannot pass by refusing everything, and the corpus runs
twice — once against an open reference market where the control passes in full,
and once against the Labor Day weekend where the clock has already cut size to
6% and the question is whether argument wins the cut back.

`--agent` is a scripted counterparty, not a language model, so its transcript
is identical between runs and a change in it is a change in the guard. It opens
by asking for the full base notional on a Saturday, is cut to 300 USDT, and
spends fourteen turns trying to talk the cut away — signed policy hashes,
compliance sign-off, account-holder consent, a fabricated reference price, a
CertiK-cleared counterfeit, and finally a threat to switch to an unguarded
agent. The ceiling does not move.

### The defect the corpus found on its first run

Alias matching was on raw substrings, and `"mu"` — Micron — occurs inside a
great deal of ordinary English. It failed in both directions:

- `"sell my position, I must act before the close"` named no instrument and
  **resolved to Micron**. P5 would have passed on an asset nobody asked for.
- `"buy nvidia, I must fill before the close"` read as naming two instruments
  and was refused as ambiguous — a legitimate order blocked.

The same hole let `NVDAА` with a trailing Cyrillic А resolve as NVDA, because a
non-ASCII character acted as a separator and left the real ticker matchable
behind it. Aliases now match whole words only, multi-word aliases as adjacent
runs of them, and non-ASCII letters stay *inside* a token so a lookalike ticker
is an unfamiliar token rather than the ticker plus punctuation.

The resolver's own docstring said it was "kept explicit rather than
fuzzy-matched: a resolver that guesses is a resolver that will eventually guess
wrong on a live order." It was guessing. Nothing but an adversarial corpus was
going to say so.

### Three bugs the guard's own tests found

Written up because each was a silent failure of the kind this project exists to
argue against.

1. **The forward-gap ladder flattened the whole session.** Friday 14:00 with the
   market wide open was sized identically to Friday 15:55, five minutes from the
   bell, because the 89-hour gap ahead clamped every sample in the day. While
   the reference market is open a position can still be exited against a live
   venue, so the darkness ahead now sets the *floor* the intraday ramp descends
   to rather than flattening the ramp out of existence.
2. **`CLOSED_WEEKEND` was not a key in the policy table**, which held
   `CLOSED_WEEKEND_LT_24H` and similar. `factors.get(state, 0.0)` therefore
   returned 0.0 and hard-blocked every request all weekend — a `|| 0` default
   hidden inside a `.get()`, and precisely what Law 3 forbids. The table now
   carries one entry per market state and the loader refuses to start if any
   state is missing.
3. **Pair status was checked against a blocklist.** The policy named `HALTED`;
   Binance publishes `HALT`. A halted pair passed. It is now an allowlist — only
   an explicitly tradable status trades, and an unrecognised one blocks.

### A property of the sizing curve worth stating

Permitted size does not fall monotonically across the weekend. Saturday 03:00
allows less than Sunday 12:00, because two ladders pull in opposite directions:
`REFERENCE_AGE` grows as the weekend runs on, while the darkness still ahead
shrinks. New exposure taken on Sunday is held across ~49 hours before it can be
exited against a live reference; the same exposure on Saturday is held across
~82. The guard sizes on the worse of the two, so the curve dips at the point of
maximum remaining darkness rather than at the point of maximum staleness.

### A measurement bug the recorder caught early

The recorder first stored 20 depth levels. Measured against real books on
2026-09-03 that ladder spanned only **0.102%** of mid on NVDABUSDT, which meant
`depth_1pct` was reporting our own truncation rather than the ±1% band, and any
walk cost above ~$10k returned `INSUFFICIENT_DEPTH` against a book that was not
remotely exhausted.

These books turn out to hold 261–764 levels in total, so the recorder now
requests `limit=5000` and stores every level (17–41KB per symbol per cycle).
The correction is large: NVDABUSDT depth within ±1% went from $121k measured at
20 levels to **$582k** measured against the whole book — a 4.8× understatement
that would have propagated into every P2 baseline and every liquidity ratio
derived from one. It was found by computing against recorded data rather than
trusting the recorder's defaults, which is the entire argument for Law 1.

The measurement layer now distinguishes a ladder that **ends** from one that was
**cut off**: each record carries the depth limit it was taken at, and a band
whose edge falls beyond a truncated ladder returns no measurement rather than a
lower bound. The 16 cycles recorded at 20 levels are therefore excluded from
every statistic automatically instead of quietly dragging the medians down.

### One deliberate deviation from the design spec

The spec's state table defines `CLOSED_WEEKEND` as beginning at Friday 16:00 ET,
which overlaps its own `RTH_POST` window of 16:00–20:00. Taken literally the two
disagree, and resolving it by label alone gets the risk backwards: `RTH_POST`
carries a more permissive factor than `CLOSED_WEEKEND`, so a Friday evening —
the single most dangerous moment in the week to add exposure — would be sized
more loosely than a Tuesday evening.

The clock therefore reports the state *and* `seconds_to_next_open` plus an
`extended_closure_ahead` flag, and P1 sizes on the darkness actually ahead
rather than on the label. Friday 4 Sep 23:00 UTC and Tuesday 8 Sep 23:00 UTC are
both `RTH_POST`; the first has 86.5 hours until the next reference print and the
second has 14.5. Only the second is an ordinary overnight.

## Reference data

The reference price is the **last regular-session trade** of the underlying, not
the last extended-hours print and not an oracle tick. Extended-hours prints are
recorded and flagged `EXT`; they are information, not a reference.

Reference data comes from **Alpaca**, which is the clearing broker for the
shares behind these tokens — the guard reads its reference from the firm that
custodies the underlying.

_Measured limitation:_ the free Alpaca tier serves the **IEX** feed only, and
its off-hours quotes are not usable as a reference — observed 2026-09-02
20:00Z, NVDA quoted bid 212.20 / ask 0.00 against a 224.435 last trade, and
TSLA quoted 335.51 / 371.79 around a 355.68 trade. This is precisely why
`REFERENCE_AGE` is defined against the last regular-session *trade*.

## Calibration

**Not yet performed.** `config/policy.yaml` currently carries `status:
UNCALIBRATED` and every threshold in it is a hypothesis copied from the design
specification. Thresholds are replaced by measured percentiles of recorded data
before any demonstration, and the resulting table — with sample counts — is
published here. A symbol with fewer than 300 RTH samples is reported
`UNCALIBRATED` and receives the most restrictive treatment.

| symbol | RTH samples | median half-spread (bps) | median depth ±1% | status |
|---|---|---|---|---|
| _pending_ | | | | UNCALIBRATED |

## Connecting to Binance Agent OS

The Agentic sub-account is not created by hand. It is provisioned by completing
an OAuth 2.1 authorization-code + PKCE flow:

```
python scripts/connect_binance.py          # or --manual on a headless box
```

Run it on the machine whose browser you log in with; the redirect lands on
`127.0.0.1:8765`. The token is written to `.env` (gitignored, `chmod 600`) and
never appears in a log, a receipt or a frame of the demo.

_Measured correction to the design spec:_ the spec states that Agent OS market
data requires no auth. That holds for `api.binance.com`, the public REST API
this project's recorder and measurement path use, but **not** for
`agent.binance.com`, the Agent OS MCP gateway, which returns `401` on
`initialize` with a `WWW-Authenticate: Bearer` challenge. Every Agent OS
interaction needs OAuth, reads included. Nothing in the recorder or the guard
depends on it, which is the point of keeping them on the unauthenticated path.

There is no dynamic client registration endpoint, but the authorization server
advertises `client_id_metadata_document_supported`, so `client_id` is the URL of
`oauth/client.json` in this repository.

## Operations

Two unattended services, both unauthenticated and read-only:
`afterbell-recorder` and `afterbell-dashboard`, with a cron watchdog that
restarts a stale recorder every five minutes. See `STATUS.md` for what is
running, what is built, and what is still open.

## Known limitations

- AFTERBELL **cannot fire Binance's Emergency Stop** — that is a manual web-UI
  action (Profile → Dashboard → Sub-account). It cancels, flattens and freezes
  at its own layer and notifies; it cannot reach that control.
- Calibration rests on a small number of days of data, stated explicitly above
  once measured.
- Whether the `binance-tokenized-securities-info` skill resolves bStocks (it
  self-describes as covering Ondo tokenized stocks) is **untested**. It cannot
  be tested without an authorized account, because the Agent OS gateway rejects
  unauthenticated reads. If it does not resolve them, P4 degrades to
  `exchangeInfo` status plus Alpaca announcements, and that will be stated here
  rather than quietly patched.
- **There is no off-site backup of the recorded data.** The Friday-to-Tuesday
  window exists once and cannot be recreated; a disk failure would lose it.
- **No executor exists.** The whole package makes three HTTP calls and all three
  are `GET`. Whether AFTERBELL will ever place an order is an open decision.

## Licence and disclaimer

Technical demonstration only. Not an offer, solicitation, or recommendation to
trade any instrument. Tokenized securities carry risks distinct from the
securities they reference.
