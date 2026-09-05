# AFTERBELL — build status

Updated **2026-09-05 16:56 UTC**. This file separates code that is built from
external facts that still need an account holder or destination.

The detailed continuation handoff is intentionally local-only and untracked; this file records the public status.

## Running unattended right now

| process | unit | credential boundary | state |
|---|---|---|---|
| Recorder | `afterbell-recorder.service` | none; Yahoo reference | active, enabled at boot |
| Dashboard | `afterbell-dashboard.service` | none | active through HTTPS at `afterbell.site` |
| MCP server | `afterbell-mcp.service` | none; holds no credential | active through HTTPS at `afterbell.site/mcp` |
| Guard | `afterbell-guard.service` | no credentials; public Binance corporate-action status | active, enabled at boot |
| Watchdog | `afterbell-watchdog.timer` | Healthchecks URL in separate mode-600 file | active, every 5 min |
| Backup | `afterbell-backup.timer` | Google Drive remote in separate mode-600 file | active, hourly |

The recorder, dashboard and guard never load `.env`, so an Agent OS OAuth token
cannot stop or enter the market-data process. The executor is never invoked by
a service and the shipped policy has `executor.enabled: false`.

The dashboard listens only on loopback; nginx is the sole public entrypoint.
HTTPS is live at `afterbell.site` and `www.afterbell.site`, with automatic
certificate renewal. TCP 8100 is not allowed through UFW.

## Built

- Canonical registry, checksum validation, and full instrument resolution
- 60-second recorder for five bStock pairs: full depth (`limit=5000`), trades,
  `exchangeInfo` status, Yahoo regular-session reference data, and gap markers
- Market clock and `REFERENCE_AGE` over the checked-in 2026 calendar
- Measurements: spread, ±1% depth, walk cost, basis, RTH-only baselines
- Policy loader and monotone six-check safety evaluator with signed policy SHA
- Hash-chained JSONL receipts for decisions and refusals
- Live public Binance bStocks status and token-audit adapters
- Binance-native corporate-action status checks; current status is
  never mislabeled as guaranteed corporate-action lookahead
- Credential-free D1 authorization boundary: Ed25519-signed 120-second artifacts,
  atomic nonce reservation, exact Codex MCP handoff, and child fill receipts
- Optional narration-only adapter; provider text cannot contain measurements or
  enter the decision
- Dashboard with recorded basis/age chart, calibration table, guard state,
  policy SHA and ledger head
- Operator freeze: a kill file checked ahead of all six protections, receipted
  as `OPERATOR_FREEZE` and alerted on both transitions
- A read-only MCP server surface: `evaluate_order` and `get_market_state`,
  unauthenticated, receipted, reachable from any client
- The evaluation table, generated from the adversarial corpus and the ledger
- Systemd services, backup timer, watchdog timer, and explicit alert gaps
- Synthetic self-contained adversarial corpus and reckless counterparty tests

## Live evidence from this box

- The operator freeze was engaged against the running guard on 2026-09-05 and
  produced receipt 2404, `BLOCK` / `OPERATOR_FREEZE` / 0.0 permitted, on a
  request the same guard had been reducing to 600 USDT a minute earlier.
  Removing the file restored the previous behaviour on the next cycle.
- A live authorization was issued for a real decision: 5,000 USDT requested,
  600 permitted by the guard, narrowed to 25 by the hand-chosen execution
  ceiling. The artifact signature and TTL were verified locally. No Binance credential was
  exposed and no order was sent.
- The MCP server answered `$5,000 NVDABUSDT BUY` over public HTTPS with
  `REDUCE` to 600 USDT, naming the weekend closure, in 1.1s.

- Binance REST ping and `NVDABUSDT` ticker: passed.
- Binance public bStocks status for the canonical NVDAB contract: `TRADING`.
- Public token audit: `isSupported=false`, `hasResult=false`; contract verification
  reports registry-only, not a clean audit.
- Live public integration test: passed with
  `AFTERBELL_RUN_LIVE=1`.
- Yahoo is the active reference provider. Alpaca is not configured here.
- Integrated live guard evaluation: market-closure risk reduced on the closing ramp; liquidity, price disagreement, identity, and contract checks passed; **corporate-action status warns because Binance current-status verification does not guarantee advance corporate-action notice**.

## Calibration

The latest generated table is in `docs/calibration.md` and the README. At
2026-09-05 13:50 UTC it contained 17,965 measured books, 14,135 reference prints,
**781 RTH_OPEN samples per symbol out of 300 required**, and a first full weekend
closure at **827 CLOSED_WEEKEND samples per symbol**. All five baseline medians
are measured and usable inside the declared rolling seven-day window.

Basis is now measured across five market states rather than three. Regular
trading disagreement is far tighter than the live bands assume — RTH_OPEN
p75/p95/p99 at 7.1/12.6/33.9 bps against live WATCH/DEGRADED/BROKEN bands of
100/250/500 bps — while `RTH_PRE` is the widest state at a p99 of 537.6 bps.
That spread between states is the argument for keeping the bands measured
rather than round.

The signed policy remains `status: UNCALIBRATED` because its market-closure, liquidity, and price-disagreement thresholds
are still hypotheses; no threshold was silently promoted. `CLOSED_HOLIDAY` is
the one state never yet observed; it records on Labor Day, 2026-09-07. Add that
observation, then review the proposed values manually before changing policy.

The calibration command is reproducible and never edits live policy:

```
.venv/bin/python -m afterbell.calibrate --out docs/calibration.md
```
## Account-bound validation

1. Binance Agent OS is authenticated through the supported Codex MCP client;
   `codex mcp list` shows `binance-agent-os` enabled with `Auth: OAuth`. A
   read-only `spot.getAccount` probe succeeded with `canTrade: true`, but the
   Spot `balances` array is empty.
2. `spot.exchangeInfo` reports `NVDABUSDT` `TRADING`,
   `isSpotTradingAllowed: true`, and `NOTIONAL.minNotional=5.00` USDT. This
   is not proof that the account is funded or jurisdiction-eligible for a
   real bStock trade.
3. No real order has been sent. A minimum NVDAB test requires fresh, explicit
   account-holder approval and funds in the connected Spot account.
4. HTTPS and Google Drive backup are configured outside the repository.
   Healthchecks transition delivery is not yet proven; watchdog logs include
   an earlier `ALERT GAP` for a missing URL.

## Remaining gaps

1. **D1 operational acceptance:** the credential-free authorization boundary is
   built and Codex OAuth is verified, but no real order ID or fill receipt
   exists. The connected Spot account currently has no balances.
2. **D5 aggregate exposure ceiling:** not built.
3. **D7 Skills Hub PR:** not opened.
4. **D11 video and submission mechanics:** not started.
5. **D6 advance corporate-action notice:** Binance current status is live and
   authoritative; Alpaca is optional best-effort and not wired or configured.
6. **D8 Square publishing:** awaits Creator Center API key.
7. **D9 counterparty comparison:** wait for an even post-fix RTH/closure sample.
8. **Public MCP hardening:** rate limiting and bounded receipt growth are not
   implemented.
9. **Calibration:** CLOSED_HOLIDAY remains unobserved; policy stays
   UNCALIBRATED pending data and manual review.

## Known limitations

- AFTERBELL cannot fire Binance's Emergency Stop; that remains a manual web-UI
  control.
- The authenticated tokenized-securities skill query remains account-bound and
  is not claimed here. Codex OAuth and read-only Spot checks are verified, but
  bStock funding/jurisdiction eligibility and a real order remain unproven.
- The public token audit does not support bStocks, so contract verification's live fallback is the
  canonical registry alone.
- The current box is in AWS eu-west-1 rather than the Tokyo region recommended
  by the build spec. Public REST currently passes, but that is not a guarantee
  for future Binance or Agent OS access.
- This is a technical demonstration, not investment advice, an offer, a
  solicitation, or a claim of direct ownership of underlying shares.

## Next automatic milestones

- The Friday bell and the weekend closure are recorded. Keep the recorder
  running through the Labor Day closure and the Tuesday reopen; those states
  cannot be back-filled.
- Re-run calibration after Labor Day, inspect proposed policy values manually,
  and only then decide whether the policy can be marked calibrated.
