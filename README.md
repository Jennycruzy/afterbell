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
the open under `tests/corpus/`, and read only by agents in this repository**.
No payload is ever published anywhere a third party's agent could encounter it
— not on-chain, not in a token description, not in a social post.

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

### Not yet built

Market clock, measurement engine, resolver, guard, ledger, rationale layer,
executor, dashboard.

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

## Known limitations

- AFTERBELL **cannot fire Binance's Emergency Stop** — that is a manual web-UI
  action (Profile → Dashboard → Sub-account). It cancels, flattens and freezes
  at its own layer and notifies; it cannot reach that control.
- Calibration rests on a small number of days of data, stated explicitly above
  once measured.
- Whether the `binance-tokenized-securities-info` skill resolves bStocks (it
  self-describes as covering Ondo tokenized stocks) is **untested**. If it does
  not, P4 degrades to `exchangeInfo` status plus Alpaca announcements, and that
  will be stated here rather than quietly patched.

## Licence and disclaimer

Technical demonstration only. Not an offer, solicitation, or recommendation to
trade any instrument. Tokenized securities carry risks distinct from the
securities they reference.
