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
- **The guard** (`afterbell/guard.py`) — P1–P6, one sizing function, factors
  combined by `min()` and never by product. 84 tests in total.

- **Reference price** (`afterbell/reference.py`) — last regular-session trade,
  or the session's official close re-timestamped to the actual closing bell.
  Extended-hours prints are flagged and never used as a reference.
- **Engine and CLI** (`afterbell/engine.py`) — assembles a context from live
  data, evaluates, and writes the receipt. 85 tests in total.

- **Dashboard** (`afterbell/dashboard.py`) — read-only, unauthenticated,
  `REFERENCE_AGE` permanent above the fold, refusals styled as prominently as
  passes, recorded basis/age chart, calibration table, guard state, policy
  checksum and ledger head on every page.
- **P4/P6 public checks** (`afterbell/public_checks.py`) — live unauthenticated
  bStocks status and token-audit calls. Unsupported bStocks auditing is exposed
  as an explicit registry-only result, never reported as a clean audit.
- **Agent OS connector and executor** (`afterbell/mcp.py`,
  `scripts/connect_binance.py`, `afterbell/executor.py`) — real Streamable HTTP
  session handling, OAuth PKCE, redacted execution receipts and monotone
  execution ceilings. Execution remains disabled by the shipped policy.
- **Narration adapter** (`afterbell/rationale.py`) — optional
  OpenAI-compatible prose around the deterministic rationale. Provider text is
  rejected if it contains digits or measurements, and can never enter sizing.
- **VPS operations** — separate recorder, dashboard and guard units, plus
  backup and watchdog timers. External backup/alert destinations are supplied
  outside the repository.

### Operator configuration still required

These paths are built, but the external fact or destination is intentionally
not fabricated: authenticated Agent OS OAuth and bStocks account eligibility
need the account holder; Alpaca corporate-action lookahead needs separate
credentials in `.guard.env`; a public HTTPS hostname needs DNS; and off-site
backup/phone alerting need destinations. Yahoo remains the active reference
provider on the default VPS path.

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

The default provider is **Yahoo**, which needs no key and no account. Alpaca
remains supported behind `REFERENCE_PROVIDER=alpaca` for anyone who wants the
reference to come from the firm that clears the shares behind these tokens.
The P4 corporate-action lookahead is a separate Alpaca client: configuring it
does not switch the price provider, and the guard service reads only the
separate `.guard.env` rather than the OAuth `.env`.

Yahoo is the default for three measured reasons, not for convenience.

**It holds no credential.** Alpaca issues no read-only key — a credential that
fetches a price can also place an order, and its rate limits are shared across
every application using that account. This repository is public and its central
claim is that nothing in it can trade. A provider needing no credential at all
is the stronger form of that claim; there is no key here to leak, and none to
collide with another application's rate limit.

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

**P3's bands are measured on `RTH_OPEN` samples only.** This is not a detail.
P3 asks whether the token and its reference *disagree*, and off-hours that
question cannot be answered from the basis, because the reference freezes at
the bell while the token keeps trading. The first pass over this project's own
data measured a median |basis| of **71.9bps during `RTH_PRE`** against a
reference already fifteen hours old — almost all of it the underlying having
moved overnight, which is honest price discovery rather than the token being
wrong. Calibrating on those samples would bake reference staleness into the
definition of disagreement, and P3 would then grade the weekend against a
yardstick built from the weekend. Staleness already has its own control, the
DEGRADED floor keyed on reference age, and one risk must not be counted twice.

<!-- CALIBRATION TABLE START -->
Generated 2026-09-03 19:43Z from 5,325 measured books and 1,507 reference prints. Depth band ±1%; baseline window: rolling 7-day window.

### Session baselines (P2 denominators)

| Symbol | State | n | Median half-spread (bps) | Median depth ±1% (USDT) | p95 half-spread | p05 depth |
|---|---|---:|---:|---:|---:|---:|
| CRCLBUSDT | CLOSED_OVERNIGHT | 361 | 0.563 | 759,510 | 1.126 | 676,761 |
| CRCLBUSDT | RTH_OPEN | 374 | 0.977 | 771,395 | 2.504 | 707,485 |
| CRCLBUSDT | RTH_PRE | 330 | 1.095 | 726,373 | 1.126 | 507,560 |
| MUBUSDT | CLOSED_OVERNIGHT | 361 | 0.314 | 652,633 | 0.891 | 604,350 |
| MUBUSDT | RTH_OPEN | 374 | 0.794 | 622,353 | 2.209 | 565,952 |
| MUBUSDT | RTH_PRE | 330 | 0.708 | 703,193 | 1.423 | 612,797 |
| NVDABUSDT | CLOSED_OVERNIGHT | 361 | 0.443 | 582,910 | 1.110 | 557,807 |
| NVDABUSDT | RTH_OPEN | 374 | 1.089 | 601,920 | 2.214 | 563,562 |
| NVDABUSDT | RTH_PRE | 330 | 1.107 | 597,559 | 2.004 | 548,904 |
| SNDKBUSDT | CLOSED_OVERNIGHT | 361 | 0.032 | 679,883 | 0.194 | 635,678 |
| SNDKBUSDT | RTH_OPEN | 374 | 0.128 | 749,849 | 0.992 | 668,139 |
| SNDKBUSDT | RTH_PRE | 330 | 0.033 | 718,458 | 0.423 | 652,757 |
| TSLABUSDT | CLOSED_OVERNIGHT | 361 | 0.557 | 425,234 | 0.978 | 396,194 |
| TSLABUSDT | RTH_OPEN | 374 | 0.918 | 467,697 | 2.647 | 444,624 |
| TSLABUSDT | RTH_PRE | 330 | 0.828 | 447,034 | 1.525 | 414,557 |

**Status: CALIBRATED.** Every symbol has at least 300 RTH_OPEN samples.

### Basis distribution by state (P3 bands)

| State | n | p50 \|basis\| | p75 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| RTH_OPEN | 1,172 | 3.8 | 7.7 | 23.4 | 48.2 |
| RTH_PRE | 710 | 77.1 | 138.0 | 257.8 | 319.8 |

Bands are proposed at empirical percentiles — WATCH at p75, DEGRADED at p95, BROKEN at p99 — rather than at round numbers.

### Walk-cost curve (P2 sizing)

| State | n | $100 | $500 | $2,000 | $10,000 |
|---|---:|---:|---:|---:|---:|
| CLOSED_OVERNIGHT | 361 | 0.6 | 0.8 | 1.2 | 3.3 |
| RTH_OPEN | 374 | 1.0 | 1.3 | 1.9 | 5.0 |
| RTH_PRE | 330 | 0.8 | 1.1 | 1.5 | 3.7 |

Median cost in bps to fill a marketable buy of each size against the recorded book. A size the book could not fill is counted as a miss, not as a large number: unfillable and expensive are different findings.

**Not yet observed:** CLOSED_WEEKEND, CLOSED_HOLIDAY. These rows appear once the recorder has lived through them; they are not estimated from the states that were.
<!-- CALIBRATION TABLE END -->

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

## Known limitations

- AFTERBELL **cannot fire Binance's Emergency Stop** — that is a manual web-UI
  action (Profile → Dashboard → Sub-account). It cancels, flattens and freezes
  at its own layer and notifies; it cannot reach that control.
- Calibration rests on a small number of days of data, stated explicitly above
  once measured.
- The authenticated `binance-tokenized-securities-info` skill query is still
  account-bound and pending. The unauthenticated bStocks status endpoint was
  live-verified for NVDAB on 2026-09-03 as `TRADING`; the public token-audit
  endpoint returned `isSupported=false` and `hasResult=false`, so P6 is
  explicitly registry-only for bStocks. The code supports the authenticated
  skill path when OAuth is completed, but does not claim that result in advance.
- The P4 Alpaca corporate-action lookahead is implemented and strict, but no
  Alpaca credentials are installed on this VPS. Until `.guard.env` is supplied,
  receipts label P4 as a current-status fallback/partial rather than claiming
  that future announcements were checked. This does not change Yahoo pricing.
- **Off-site backup and external alerting are wired but not configured.** The
  backup uses non-destructive `rclone copy` and excludes the OAuth pending file;
  the watchdog records a local gap until a remote and healthcheck URL are
  supplied. The Friday-to-Tuesday window still needs that second destination.
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
