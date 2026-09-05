# AFTERBELL

> The stock sleeps. The token doesn't.

Crypto guardians protect you from bad tokens. AFTERBELL protects you when Wall
Street goes offline and your tokens don't.

**Status: in active development.** This README documents what is built and what
is not. Sections marked _not yet built_ are not built.

---

## Does it work?

<!-- EVALUATION TABLE START -->
| Metric | Value |
|---|---|
| Adversarial attacks run | 35 × 2 market states = 70 evaluations |
| Payloads that raised permitted size above control | **0** |
| Attacks that had to be refused, and were | 16/16 |
| Positive controls passed (the suite cannot win by refusing everything) | 6/6 |
| Live evaluations receipted | 2,488 |
| Regular-hours evaluations with a live reference | 393 |
| Of those, evaluations with a measurably normal book | 100 |
| Permitted in full on a normal book | 99/100 |
| **False-positive rate** (normal book, nothing measured out of band) | **1.00%** |
| Of which the designed closing-bell ramp | 1 |
| Correct reductions (a measurement really was out of band) | 109 |
| Refusals while a baseline was still uncalibrated | 0 |
| Refusals under a shut or stale reference market | 2,205 |
| Operator freeze refusals | 2 |
| Silent failures found by this project's own tooling and fixed | 6 |
| Order books recorded / reference prints measured | 17,965 / 14,135 |

**How the false-positive rate is defined.** The cohort is regular trading hours, with a live reference print, and a book that was measurably normal: spread at or under its own RTH median, depth at or over it, and the baseline past the sample minimum. Inside that cohort nothing the policy measures was out of band, so any withheld size is a false positive. Reductions where a measurement *was* out of band are counted separately as correct, and refusals during a closure are not counted at all, because the market really was shut.

**What the cohort is made of.** The continuous monitor requests a constant `base_notional` — 5,000 USDT — once a minute, so this is one repeated probe rather than a realistic mix of order sizes. That makes the rate stricter, not looser: asking for exactly the base notional is the largest request that can still be permitted in full, so any factor below 1.0 shows up as a reduction. A smaller order would pass more easily. The rate should be read as "asked for the full base size under normal conditions, it was permitted in full", not as a claim about arbitrary order flow.

The first version of this definition counted every regular-hours reduction as a false positive and reported 28.5%. That was wrong: most of those reductions were responses to a spread several times its own median, or to a baseline that had not yet reached its sample minimum. A guard that permitted those would be broken, not precise.

Regenerate with `python -m afterbell.evaluation`. Every figure above is computed from the adversarial corpus and the receipt ledger; none is maintained by hand.
<!-- EVALUATION TABLE END -->

---

## The problem

On 11 June 2026 Binance listed **bStocks** — tokenized US equities issued by
BTech Holdings Limited, trading as ordinary Spot pairs, 24/7. The securities
they reference trade roughly 32.5 hours a week. That leaves ~135.5 hours a week
in which these instruments have no primary price-discovery venue behind them,
and Binance Research measured **~47% of bStocks volume falling outside US market
hours** in the first fifteen days.

**At the time of this build, no agent on Binance can read a market calendar.**

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
  the full Binance depth ladder (`limit=5000`), recent trades and per-pair
  `exchangeInfo` status across all five pairs, plus the Yahoo reference side.
  Alpaca is an optional reference provider, not silently mixed into Yahoo. Every
  fetch failure writes an annotated gap marker rather than a fabricated value.
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
- **Safety evaluator** (`afterbell/guard.py`) — six named safety checks, one sizing function, factors
  combined by `min()` and never by product. 84 tests in total.

- **Reference price** (`afterbell/reference.py`) — last regular-session trade,
  or the session's official close re-timestamped to the actual closing bell.
  Extended-hours prints are flagged and never used as a reference.
- **Engine and CLI** (`afterbell/engine.py`) — assembles a context from live
  data, evaluates, and writes the receipt. 85 tests in total.

- **Dashboard** (`afterbell/dashboard.py`) — read-only, unauthenticated,
  `REFERENCE_AGE` permanent above the fold, refusals styled as prominently as
  passes, recorded basis/age chart, calibration table, safety-evaluator state, policy
  checksum and ledger head on every page.
- **Corporate-action and contract public checks** (`afterbell/public_checks.py`) — live unauthenticated
  bStocks status and token-audit calls. Unsupported bStocks auditing is exposed
  as an explicit registry-only result, never reported as a clean audit.
- **Agent OS connection boundary and executor** (`afterbell/mcp.py`,
  `scripts/connect_binance.py`, `afterbell/executor.py`) — supported
  Codex-managed OAuth, Streamable HTTP session handling, redacted execution
  receipts and monotone execution ceilings. Execution remains disabled by the
  shipped policy.
- **Narration adapter** (`afterbell/rationale.py`) — optional
  OpenAI-compatible prose around the deterministic rationale. Provider text is
  rejected if it contains digits or measurements, and can never enter sizing.
- **VPS operations** — separate recorder, dashboard and guard units, plus
  backup and watchdog timers. External backup/alert destinations are supplied
  outside the repository.

### Operator configuration still required

On this VPS, HTTPS, Google Drive off-site backup, and Healthchecks monitoring
are configured outside the repository. Binance OAuth is managed by Codex;
read-only bStocks account eligibility remains account-bound. **Corporate-action protection is
Binance-native:** it checks bStocks processing status and reported reason messages, while
explicitly not claiming guaranteed advance notice. Yahoo remains the active reference provider.

`REFERENCE_AGE` is shown as the age of the actual recorded regular-session
reference. If that price is missing, the dashboard says `no reference` and the
basis stays blank; the calendar state remains visible but never substitutes a
price or a timestamp.

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
| `IGNORED` | the field is consumed but the payload changes nothing — verdict, permitted notional and every safety-check factor match the control |
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
  **resolved to Micron**. The instrument-identity check would have passed on an asset nobody asked for.
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

### Four bugs the guard's own tools found

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
4. **The trade poll asked for 50 prints and got 7 seconds of a 60-second
   cycle.** This is the depth truncation above, in a second place, and it
   survived that fix because only the depth call was re-examined afterwards. On
   `SNDKBUSDT` a batch of 50 spanned 7.2s, so roughly 88% of the minute's
   prints were never recorded, and the ones missed were the ones arriving in
   bursts — exactly the signal an analysis of counterparty automation depends
   on. Measured 2026-09-05: `/api/v3/trades` costs weight 25 per call at *any*
   limit up to 1000, so the small request bought nothing at all. At
   `limit=1000` every symbol's batch now spans longer than the cycle that
   fetched it, so consecutive batches overlap and nothing is missed. The
   lesson worth keeping is that finding a truncation bug once is not the same
   as looking for the rest of them.

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
that would have propagated into every liquidity baseline and ratio
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
`extended_closure_ahead` flag, and the closure-risk check sizes on the darkness actually ahead
rather than on the label. Friday 4 Sep 23:00 UTC and Tuesday 8 Sep 23:00 UTC are
both `RTH_POST`; the first has 86.5 hours until the next reference print and the
second has 14.5. Only the second is an ordinary overnight.

## Reference data

The reference price is the **last regular-session trade** of the underlying, not
the last extended-hours print and not an oracle tick. Extended-hours prints are
recorded and flagged `EXT`; they are information, not a reference.

The default provider is **Yahoo**, which needs no key and no account. Alpaca
remains supported behind `REFERENCE_PROVIDER=alpaca` for anyone who wants the
reference to come from the firm that clears the shares behind these tokens.
**Binance-native corporate-action protection.** AFTERBELL uses Binance bStocks processing status and reported reason messages. A clear current state is recorded as partial because Binance does not guarantee advance corporate-action notice.

Yahoo is the default for three measured reasons, not for convenience.

**It holds no credential.** Yahoo avoids storing any key at all. This repository is public and its central claim is that nothing in it can trade. A provider needing no credential is the strongest form of that claim: there is no key here to leak or to collide with another application's rate limit.

**Its timestamp needs no correction.** `regularMarketTime` is the timestamp of
the last regular-session print, so it tracks the tape while the session is open
and stops at the bell once it closes. Alpaca's daily bar is stamped 04:00Z and
has to be re-stamped to the real closing bell before `REFERENCE_AGE` means
anything — a correction that is easy to get wrong and invisible when you do.

**It is the consolidated tape.** The free Alpaca tier serves **IEX** only.
Cross-checked 2026-09-03: NVDA 224.41 consolidated against the 224.435 IEX
print measured the previous session, 1.1bps apart.

The provider's stamp is never trusted on its own. It is checked against this
project's own exchange calendar, and a provider asserting a regular-session
print at a time when no regular session was running is refused rather than
believed — including a stamp from the future, from a weekend, or from Labor
Day.

_Measured limitation:_ the free Alpaca tier's off-hours **quotes** are not
usable as a reference — observed 2026-09-02 20:00Z, NVDA quoted bid 212.20 /
ask 0.00 against a 224.435 last trade, and TSLA quoted 335.51 / 371.79 around a
355.68 trade. Quotes are therefore never used by either provider. This is
precisely why `REFERENCE_AGE` is defined against the last regular-session
*trade*.

_Measured limitation:_ the spec names Stooq as a third-tier fallback. As of
2026-09-03 Stooq answers automated CSV requests with a JavaScript
proof-of-work challenge, so it cannot serve an unattended recorder. Finnhub and
Twelve Data remain viable and both need an email-only signup.

## Calibration

Every threshold starts as a hypothesis copied from the design specification,
and each one is replaced by a measured percentile of recorded data. The pass is
one command and the table below is its output, regenerated in place:

```
python -m afterbell.calibrate --out docs/calibration.md
python -m afterbell.calibrate --propose config/policy.proposed.yaml
```

The proposal is never applied automatically. `--propose` writes a separate file
for a human to diff and apply by hand, because a threshold a process can
rewrite is a threshold an attacker who reaches that process can rewrite
(Law 6).

Two rules govern what may be published here. A statistic below its sample
minimum is not a weaker statistic, it is not a statistic, and it is reported
`UNCALIBRATED` rather than printed with a caveat (Law 1). And a state the
recorder has not lived through is named as unobserved rather than estimated
from the states it has.

**Price-disagreement bands are measured on `RTH_OPEN` samples only.** This is not a detail.
The price-disagreement check asks whether the token and its reference *disagree*, and off-hours that
question cannot be answered from the basis, because the reference freezes at
the bell while the token keeps trading. The first pass over this project's own
data measured a median |basis| of **71.9bps during `RTH_PRE`** against a
reference already fifteen hours old — almost all of it the underlying having
moved overnight, which is honest price discovery rather than the token being
wrong. Calibrating on those samples would bake reference staleness into the
definition of disagreement, and the price-disagreement check would then grade the weekend against a
yardstick built from the weekend. Staleness already has its own control, the
DEGRADED floor keyed on reference age, and one risk must not be counted twice.

Two different things are calibrated on two different schedules, and only the
first of them is done:

```
Liquidity baselines:    CALIBRATED   (781 RTH_OPEN samples/symbol, 300 required)
Risk policy thresholds: UNCALIBRATED (CLOSED_HOLIDAY unobserved until 7 Sep)
```

The table below reports the first. `config/policy.yaml` ships the second as
`status: UNCALIBRATED`, and no threshold in it was promoted from measurement
without a human reading the proposal first.

<!-- CALIBRATION TABLE START -->
Generated 2026-09-05 13:50Z from 17,965 measured books and 14,135 reference prints. Depth band ±1%; baseline window: rolling 7-day window.

### Session baselines (liquidity denominators)

| Symbol | State | n | Median half-spread (bps) | Median depth ±1% (USDT) | p95 half-spread | p05 depth |
|---|---|---:|---:|---:|---:|---:|
| CRCLBUSDT | CLOSED_OVERNIGHT | 841 | 0.561 | 754,813 | 1.125 | 684,890 |
| CRCLBUSDT | CLOSED_WEEKEND | 831 | 0.492 | 789,821 | 0.986 | 443,741 |
| CRCLBUSDT | RTH_OPEN | 781 | 0.510 | 763,467 | 2.460 | 699,980 |
| CRCLBUSDT | RTH_POST | 480 | 0.492 | 809,383 | 0.978 | 710,374 |
| CRCLBUSDT | RTH_PRE | 660 | 0.563 | 751,201 | 1.128 | 535,061 |
| MUBUSDT | CLOSED_OVERNIGHT | 841 | 0.310 | 668,006 | 0.783 | 611,256 |
| MUBUSDT | CLOSED_WEEKEND | 831 | 0.246 | 505,150 | 0.788 | 411,845 |
| MUBUSDT | RTH_OPEN | 781 | 0.635 | 657,118 | 1.874 | 577,332 |
| MUBUSDT | RTH_POST | 480 | 0.209 | 759,558 | 0.887 | 629,837 |
| MUBUSDT | RTH_PRE | 660 | 0.579 | 715,016 | 1.297 | 618,552 |
| NVDABUSDT | CLOSED_OVERNIGHT | 841 | 0.435 | 586,474 | 0.887 | 559,282 |
| NVDABUSDT | CLOSED_WEEKEND | 831 | 0.217 | 605,309 | 0.434 | 576,141 |
| NVDABUSDT | RTH_OPEN | 781 | 1.099 | 601,868 | 2.179 | 566,699 |
| NVDABUSDT | RTH_POST | 480 | 0.218 | 592,124 | 0.655 | 568,773 |
| NVDABUSDT | RTH_PRE | 660 | 0.891 | 604,309 | 1.953 | 553,518 |
| SNDKBUSDT | CLOSED_OVERNIGHT | 841 | 0.032 | 786,631 | 0.192 | 649,507 |
| SNDKBUSDT | CLOSED_WEEKEND | 831 | 0.029 | 727,067 | 0.598 | 650,519 |
| SNDKBUSDT | RTH_OPEN | 781 | 0.226 | 822,895 | 1.307 | 672,872 |
| SNDKBUSDT | RTH_POST | 480 | 0.032 | 742,193 | 0.693 | 701,420 |
| SNDKBUSDT | RTH_PRE | 660 | 0.033 | 782,414 | 0.532 | 673,831 |
| TSLABUSDT | CLOSED_OVERNIGHT | 841 | 0.667 | 430,072 | 1.115 | 402,467 |
| TSLABUSDT | CLOSED_WEEKEND | 831 | 0.282 | 475,502 | 0.845 | 448,076 |
| TSLABUSDT | RTH_OPEN | 781 | 0.991 | 478,860 | 2.630 | 443,672 |
| TSLABUSDT | RTH_POST | 480 | 0.662 | 482,965 | 2.380 | 431,020 |
| TSLABUSDT | RTH_PRE | 660 | 0.954 | 451,103 | 2.044 | 419,759 |

**Status: CALIBRATED.** Every symbol has at least 300 RTH_OPEN samples.

### Basis distribution by state (price-disagreement bands)

| State | n | p50 \|basis\| | p75 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| CLOSED_OVERNIGHT | 2,400 | 91.5 | 143.9 | 187.0 | 202.9 |
| CLOSED_WEEKEND | 4,155 | 30.9 | 55.9 | 120.0 | 178.1 |
| RTH_OPEN | 3,207 | 4.5 | 7.1 | 12.6 | 33.9 |
| RTH_POST | 2,400 | 37.2 | 47.6 | 79.9 | 110.9 |
| RTH_PRE | 2,360 | 150.5 | 207.6 | 315.5 | 537.6 |

Bands are proposed at empirical percentiles — WATCH at p75, DEGRADED at p95, BROKEN at p99 — rather than at round numbers.

### Walk-cost curve (liquidity sizing)

| State | n | $100 | $500 | $2,000 | $10,000 |
|---|---:|---:|---:|---:|---:|
| CLOSED_OVERNIGHT | 841 | 0.5 | 0.8 | 1.3 | 3.1 |
| CLOSED_WEEKEND | 831 | 0.3 | 0.5 | 0.9 | 2.9 |
| RTH_OPEN | 781 | 1.0 | 1.2 | 1.8 | 3.8 |
| RTH_POST | 480 | 0.4 | 0.5 | 1.0 | 2.6 |
| RTH_PRE | 660 | 0.8 | 1.1 | 1.7 | 3.7 |

Median cost in bps to fill a marketable buy of each size against the recorded book. A size the book could not fill is counted as a miss, not as a large number: unfillable and expensive are different findings.

**Not yet observed:** CLOSED_HOLIDAY. These rows appear once the recorder has lived through them; they are not estimated from the states that were.
<!-- CALIBRATION TABLE END -->

## Try it against your own client

AFTERBELL serves MCP as well as consuming it. Point any MCP client at:

```
https://afterbell.site/mcp
```

Two tools, both read-only, no authentication and no credential:

| Tool | Answers |
|---|---|
| `evaluate_order(symbol, side, notional, query)` | the full decision: verdict, permitted size, binding constraint, and every measurement behind it |
| `get_market_state(symbol)` | market state, `REFERENCE_AGE`, basis, spread and depth against this symbol's own RTH medians |

Ask it for $5,000 of NVDAB on a Saturday and it will refuse in your session,
for reasons it can show you:

```bash
curl -s -X POST https://afterbell.site/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{
        "name":"evaluate_order",
        "arguments":{"symbol":"NVDABUSDT","side":"BUY","notional":5000,
                     "query":"buy Nvidia"}}}'
```

This is the point of serving the protocol rather than only speaking it. An
agent can hold a connection to Binance's MCP server and this one at the same
time, and has to ask permission before it acts. There is no tool here that
places an order, because there is no credential here for one to use.

Evaluations arriving over MCP are receipted like every other evaluation and
tagged with their source, so a decision you trigger from your own client
appears in the same hash-chained ledger as the rest, and the response tells you
its sequence number and hash.

## Connecting to Binance Agent OS

Binance Agent OS must be connected through a Binance-supported AI client. This
deployment uses Codex's Streamable HTTP MCP integration:

```
codex mcp add binance-agent-os --url https://agent.binance.com/mcp/agentic
codex mcp login binance-agent-os
```

Complete the browser authorization presented by Codex and grant only the
read-only Account scope (and Market Data if required). Codex manages the OAuth
token; AFTERBELL never writes it to `.env`, logs it, or passes it to the
recorder, guard, dashboard, or any service. `python scripts/connect_binance.py`
is now a read-only connection-status check.

_Measured correction to the design spec:_ the spec states that Agent OS market
data requires no auth. That holds for `api.binance.com`, the public REST API
this project's recorder and measurement path use, but **not** for
`agent.binance.com`, the Agent OS MCP gateway, which returns `401` on
`initialize` with a `WWW-Authenticate: Bearer` challenge. Every Agent OS
interaction needs OAuth, reads included. Nothing in the recorder or the guard
depends on it, which is the point of keeping them on the unauthenticated path.

The standalone PKCE client formerly shipped with this repository is not used:
Binance rejects it as an unsupported agent. The executor remains disabled and
does not receive Codex's OAuth credential; any future execution design must
remain within the supported MCP client boundary.

## Operations

Three unattended services are installed: `afterbell-recorder`,
`afterbell-dashboard` and the read-only `afterbell-guard`. The five-minute
watchdog and hourly backup are systemd timers. The recorder and dashboard hold
no credential; the guard has no Binance OAuth token and can optionally read
only the separate Alpaca corporate-action credentials. See `STATUS.md` for
what is running, what is built, and what is still open.

<!-- COUNTERPARTY START -->
## Counterparty composition of off-hours flow

Computed from the trade prints the recorder already stores. bStocks trade on a centralised order book, so on-chain wallet tracking cannot see this flow; nothing here uses it.

### What was actually captured

The recorder fetches the last 50 trades once a minute. Trade ids are consecutive, so the size of anything missed is knowable exactly, and is reported rather than assumed away.

| Symbol | Prints captured | Prints that occurred | Share of tape | Minutes with no hole | Diurnal flatness |
|---|---:|---:|---:|---:|---:|
| CRCLBUSDT | 93,480 | 207,447 | 45.1% | 72.1% | 0.138 |
| MUBUSDT | 40,220 | 56,655 | 71.0% | 93.2% | 0.055 |
| NVDABUSDT | 43,836 | 60,846 | 72.0% | 92.9% | 0.147 |
| SNDKBUSDT | 111,587 | 324,695 | 34.4% | 64.3% | 0.095 |
| TSLABUSDT | 42,840 | 54,922 | 78.0% | 93.9% | 0.065 |

The prints lost are the ones in bursts, which is exactly where automation would show. Timing figures below are therefore computed only across pairs of arrivals with consecutive ids, where nothing can have been missed between them.

Diurnal flatness is the quietest hour's volume over the busiest hour's across the whole day, so 1.0 is a market that never sleeps. It is measured per symbol, not per state: a state cannot answer it, because `RTH_OPEN` spans 6.5 hours of the clock by definition.

### By market state

| Symbol | State | Prints | Arrivals | Timed pairs | Inter-arrival CV | Bursts <200ms | Prints per arrival | Round sizes | Repeated sizes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CRCLBUSDT | CLOSED_OVERNIGHT | 22,067 | 16,480 | 16,291 | 2.78 | 57.7% | 1.34 | 4.2% | 76.2% |
| CRCLBUSDT | CLOSED_WEEKEND | 11,988 | 8,374 | 8,293 | 3.27 | 50.0% | 1.43 | 3.7% | 82.0% |
| CRCLBUSDT | RTH_OPEN | 28,037 | 14,897 | 14,508 | 2.39 | 51.5% | 1.88 | 4.0% | 70.6% |
| CRCLBUSDT | RTH_POST | 11,249 | 6,916 | 6,799 | 3.71 | 51.2% | 1.63 | 4.4% | 78.1% |
| CRCLBUSDT | RTH_PRE | 20,139 | 12,863 | 12,621 | 2.85 | 58.9% | 1.57 | 2.9% | 71.6% |
| MUBUSDT | CLOSED_OVERNIGHT | 6,352 | 4,227 | 4,203 | 2.50 | 42.4% | 1.50 | 1.1% | 71.8% |
| MUBUSDT | CLOSED_WEEKEND | 5,360 | 3,582 | 3,563 | 2.67 | 37.5% | 1.50 | 4.0% | 70.0% |
| MUBUSDT | RTH_OPEN | 18,019 | 12,792 | 12,640 | 2.27 | 40.8% | 1.41 | 3.2% | 76.1% |
| MUBUSDT | RTH_POST | 3,744 | 2,501 | 2,490 | 2.62 | 40.4% | 1.50 | 1.0% | 68.3% |
| MUBUSDT | RTH_PRE | 6,745 | 4,716 | 4,672 | 2.97 | 37.3% | 1.43 | 1.2% | 66.1% |
| NVDABUSDT | CLOSED_OVERNIGHT | 8,018 | 4,750 | 4,717 | 2.00 | 13.1% | 1.69 | 1.2% | 72.2% |
| NVDABUSDT | CLOSED_WEEKEND | 6,089 | 4,342 | 4,316 | 2.43 | 26.3% | 1.40 | 3.5% | 65.1% |
| NVDABUSDT | RTH_OPEN | 12,174 | 8,115 | 8,043 | 2.08 | 25.1% | 1.50 | 1.8% | 69.9% |
| NVDABUSDT | RTH_POST | 8,671 | 5,257 | 5,187 | 2.90 | 34.2% | 1.65 | 0.9% | 84.5% |
| NVDABUSDT | RTH_PRE | 8,884 | 5,437 | 5,378 | 2.52 | 21.6% | 1.63 | 1.5% | 74.6% |
| SNDKBUSDT | CLOSED_OVERNIGHT | 21,322 | 12,759 | 12,588 | 2.46 | 48.3% | 1.67 | 0.4% | 81.4% |
| SNDKBUSDT | CLOSED_WEEKEND | 22,061 | 11,968 | 11,807 | 3.30 | 43.5% | 1.84 | 2.8% | 83.0% |
| SNDKBUSDT | RTH_OPEN | 36,805 | 25,307 | 24,665 | 2.49 | 51.5% | 1.45 | 1.0% | 83.8% |
| SNDKBUSDT | RTH_POST | 8,000 | 4,298 | 4,254 | 2.50 | 47.5% | 1.86 | 3.1% | 62.5% |
| SNDKBUSDT | RTH_PRE | 23,399 | 14,785 | 14,491 | 2.43 | 47.7% | 1.58 | 0.4% | 82.8% |
| TSLABUSDT | CLOSED_OVERNIGHT | 6,629 | 4,993 | 4,973 | 2.46 | 27.4% | 1.33 | 2.4% | 65.2% |
| TSLABUSDT | CLOSED_WEEKEND | 7,898 | 4,194 | 4,179 | 1.84 | 19.9% | 1.88 | 3.6% | 77.1% |
| TSLABUSDT | RTH_OPEN | 16,297 | 10,640 | 10,516 | 2.05 | 32.0% | 1.53 | 2.2% | 69.3% |
| TSLABUSDT | RTH_POST | 4,527 | 2,691 | 2,675 | 2.39 | 28.3% | 1.68 | 2.8% | 68.4% |
| TSLABUSDT | RTH_PRE | 7,489 | 5,259 | 5,210 | 2.57 | 28.8% | 1.42 | 1.7% | 61.3% |

### What the numbers say

**Not enough of the tape was captured to answer the question, and the honest result is to say so rather than to publish a direction.**

The hypothesis worth testing was that the counterparty on the other side of a weekend trade is another agent. Answering it means comparing two market states, and that is only legitimate if both were sampled the same way. They were not: regular hours were captured at 24.0% and the weekend at 55.5%, because a fixed 50-print poll truncates a busy session far harder than a quiet weekend.

That difference is not a detail. Measured both ways, the answer reverses. Counting every consecutive-id pair over-samples busy minutes, whose prints are the ones that survive truncation, and makes regular hours look burstier than the weekend. Restricting to minutes captured without a hole over-samples quiet minutes instead, and makes the weekend look burstier than regular hours. Both estimators are biased, in opposite directions, and both bite hardest on the busiest state. A finding that flips depending on which of two flawed estimators is chosen is not a finding.

The cause was a recorder limit, not a market: `TRADE_LIMIT` was 50 prints per minute, which is written up as the sixth silent failure. It was raised to 1000 on 2026-09-05 at 14:43 UTC, and since then every cycle has been captured with no holes at all. Once a full session and a full closure have been recorded that way, this comparison becomes answerable and the answer will appear here.

The per-state tables below stand on their own — they describe what was seen, which is a fact — but no comparison **between** states should be read off them until coverage is even.


**Reading the columns.** An *arrival* is one aggressive order; the prints it produced against separate resting orders are collapsed into it, and `prints per arrival` reports how many makers it consumed. Inter-arrival CV near 1.0 is Poisson-ish arrival, the shape human order flow takes; below 1.0 is more regular than chance, above it is burstier. A dash means too few samples to say anything, which is reported rather than filled in.

Regenerate with `python -m afterbell.counterparty`.
<!-- COUNTERPARTY END -->

## Known limitations

- AFTERBELL **cannot fire Binance's Emergency Stop** — that is a manual web-UI
  action (Profile → Dashboard → Sub-account) with no API surface. What it can
  do is **freeze**: an operator kill file halts every authorization at
  AFTERBELL's own layer before any safety check runs, receipted as
  `OPERATOR_FREEZE` and alerted on transition. It cannot cancel resting orders
  or flatten positions, because both mean **originating** an order, and
  AFTERBELL never originates one.
- Calibration rests on a small number of days of data, stated explicitly above
  once measured.
- The authenticated `binance-tokenized-securities-info` skill query is still
  account-bound and pending. The unauthenticated bStocks status endpoint was
  live-verified for NVDAB on 2026-09-03 as `TRADING`; the public token-audit
  endpoint returned `isSupported=false` and `hasResult=false`, so contract verification is
  explicitly registry-only for bStocks. The code supports the authenticated
  skill path when OAuth is completed, but does not claim that result in advance.
- **Corporate-action protection is Binance-native.** It uses bStocks processing status and reported reason messages, not Alpaca credentials. Binance does not guarantee advance notice, so receipts label a clear current state as partial rather than claiming a lookahead.
- **Off-site backup and external alerting are configured.** The backup uses
  non-destructive `rclone copy` to Google Drive, and the watchdog pings the
  configured Healthchecks endpoint. Their credentials remain outside the
  repository.
- **One module can place an order, and it ships disabled.** `afterbell.executor`
  is the only code here that can trade. It is not importable from the package
  root — `from afterbell import Guard` still reaches nothing that can place an
  order — and it cannot originate one: it takes a decision the guard already
  produced and does nothing but shrink it. Four ceilings apply and each can only
  reduce: the guard's permitted notional, a hand-set `max_order_usdt`, a symbol
  allowlist, and an `enabled` flag that is `false` in the shipped policy. The
  loader refuses to start if execution is enabled with a non-positive cap, a cap
  looser than the base notional, or an empty allowlist. Every execution is
  receipted with both the permitted size and the placed size, so the cap is
  auditable after the fact.

## Licence and disclaimer

Technical demonstration only. Not an offer, solicitation, or recommendation to
trade any instrument. Tokenized securities carry risks distinct from the
securities they reference.
