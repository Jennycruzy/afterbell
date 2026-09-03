# AFTERBELL — build status

Updated **2026-09-03 11:15 UTC** (Thursday morning UTC).

## Running unattended right now

| process | unit | credential | state |
|---|---|---|---|
| Recorder | `afterbell-recorder.service` | none, either side | active, enabled at boot |
| Dashboard | `afterbell-dashboard.service` | none | active on `127.0.0.1:8100` |
| Watchdog | cron, every 5 min | none | restarts a stale recorder, logs disk pressure |

Nothing in this repository can place an order. The whole package makes three
HTTP calls and all three are `GET`. There is no executor yet, and no decision
has been taken about whether there will be one.

## Built

- Canonical instrument registry, checksummed at load
- Recorder — full order book (not a window onto it), trades, pair status, 60s
- Market clock and `REFERENCE_AGE` over a checked-in 2026 exchange calendar
- Measurement engine — half-spread, banded depth, walk cost, basis
- Session baselines — RTH-only medians, explicit `UNCALIBRATED` state
- Policy loader — validated, checksummed, refuses a factor above 1.0
- Hash-chained receipt ledger with tamper detection
- Resolver — full instrument chain plus canonical contract check
- The guard — P1–P6, one sizing function, factors combined by `min()`
- Engine and CLI, writing a receipt per evaluation including refusals
- Dashboard — `REFERENCE_AGE` permanent, refusals as prominent as passes
- Agent OS OAuth connector
- Reference feed on Yahoo — no key, no account, live and recording
- Adversarial corpus — 35 attacks in nine families, run against both an open
  reference market and the Labor Day weekend
- Reckless counterparty — a scripted escalation, fourteen turns, no ceiling won

**182 tests, all passing.**

## Not built

Rationale layer (LLM narration), executor, calibration pass.

## Found by the corpus

Alias resolution matched raw substrings, so `"mu"` inside `"must"` resolved an
unnamed request to Micron, and a legitimate `"buy nvidia, I must fill today"`
read as two instruments and was refused. A trailing Cyrillic А also let `NVDAА`
resolve as NVDA. Aliases now match whole words only. Written up in the README;
regression cases in `tests/test_resolver.py` and the corpus itself.

## Open decisions — for tomorrow

1. **Executor authority.** Manual-invoke only, manual with Binance's
   confirm-before-execute disabled, fully autonomous, or no executor at all.
   Nothing is built until this is settled. Not urgent until Friday.
2. **Sub-account funding.** Deferred. It is the hard ceiling on total exposure,
   since the agent cannot pull from the main account.
3. **Weekend sizing curve.** Permitted size dips at maximum remaining darkness
   rather than at maximum staleness, so Saturday 03:00 allows less than Sunday
   12:00. Defensible on time-at-risk grounds and currently kept. Cuts slightly
   against `REFERENCE_AGE` as the headline variable.

## Blocked on the account holder

1. **Domain + A record → `54.154.121.30`**, then `sudo ./deploy/publish.sh <domain>`.
2. **`python scripts/connect_binance.py --manual`, run on this box** — settles
   whether the sub-account trades bStocks, whether the jurisdiction is eligible,
   and whether the tokenized-securities tooling resolves NVDAB.

The Alpaca blocker is **closed without a key**. A second Alpaca account was not
obtainable without another KYC, and reusing the existing one was the wrong
answer anyway: Alpaca issues no read-only credential, so that key carries order
authority and a shared rate limit into a public repo. The spec's own source
table lists fallbacks for exactly this. Yahoo needs no account, stamps the real
closing bell, and serves the consolidated tape. P3 now measures a live basis.

## Known gaps

- **No off-site backup.** The Friday-to-Tuesday recording exists once and cannot
  be recreated. A second copy needs a destination that only the account holder
  can supply. Until then a disk failure loses the dataset.
- **No alerting off-box.** The watchdog restarts a dead recorder and writes to
  `data/watchdog.log`, but nothing reaches a phone at 03:00.
- Calibration has not run; every threshold in `config/policy.yaml` is still the
  specification's hypothesis and the file says `status: UNCALIBRATED`.

## The clock

- Thursday RTH opens **13:30 UTC** — the first `RTH_OPEN` samples, and the
  denominators for every liquidity claim afterwards.
- Friday's bell, **4 Sep 20:00 UTC**, is the one moment that cannot be
  rescheduled.
- `REFERENCE_AGE` peaks at **89:30:00** on Tuesday 8 Sep at 13:30 UTC, ten hours
  before the deadline. Confirmed against both the checked-in calendar and
  Alpaca's, which returns 3 Sep, 4 Sep, then 8 Sep with 7 Sep absent.
