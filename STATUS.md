# AFTERBELL — build status

Updated **2026-09-08 UTC**. This file separates code that is built from
external facts that still need an account holder or destination.

The detailed continuation handoff is tracked with the repository and records the public status and external blockers.

## Running unattended right now

| process | unit | credential boundary | state |
|---|---|---|---|
| Recorder | `afterbell-recorder.service` | none; Yahoo reference | active, enabled at boot |
| Dashboard | `afterbell-dashboard.service` | none | active through HTTPS at `afterbell.site` |
| MCP server | `afterbell-mcp.service` | none; holds no credential | active through HTTPS at `afterbell.site/mcp` |
| Guard | `afterbell-guard.service` | read-only Alpaca reference plus public Binance corporate-action status | active, enabled at boot |
| Watchdog | `afterbell-watchdog.timer` | Healthchecks URL in separate mode-600 file | active, every 5 min |
| Backup | `afterbell-backup.timer` | Google Drive remote in separate mode-600 file | active, hourly |

The recorder, dashboard and guard never load the Convex `.env`, so an Agent OS
OAuth token cannot stop or enter the market-data process. The guard's separate
mode-600 environment contains only the read-only Alpaca reference credentials.
The executor is never invoked by a service and the shipped policy has
`executor.enabled: false`. The policy also remains `status: UNCALIBRATED`; the
CLI and authorization issuer reject authorization issuance on that status, even
if a deliberate demo policy enables the executor.

The dashboard listens only on loopback; nginx is the sole public entrypoint.
HTTPS is live at `afterbell.site` and `www.afterbell.site`, with automatic
certificate renewal. TCP 8100 is not allowed through UFW.

## Built

- Canonical registry, checksum validation, and full instrument resolution
- 60-second recorder for five bStock pairs: full depth (`limit=5000`), trades,
  `exchangeInfo` status, Yahoo regular-session reference data, and gap markers
- Market clock and `REFERENCE_AGE` over the checked-in 2026 calendar
- Measurements: spread, ±1% depth, walk cost, basis, RTH-only baselines
- Policy loader and monotone seven-check safety evaluator with signed policy SHA;
  every authorization path also requires an explicit `CALIBRATED` policy status
- D5/P7 aggregate exposure ceiling: signed, fresh position snapshots cap
  gross net-position exposure across symbols; executable policies require this
  input
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
- Operator freeze: a kill file checked ahead of all seven protections, receipted
  as `OPERATOR_FREEZE` and alerted on both transitions
- A read-only MCP server surface: `evaluate_order` and `get_market_state`,
  unauthenticated, receipted, reachable from any client
- The evaluation table, generated from the adversarial corpus and the ledger
- MCP hardening is deployed: batches are capped at 20 messages, request work is
  rate-bounded, evaluate_order receipt growth has a persisted daily quota, and
  nginx applies a source-address limiter before the application.
- Systemd services, backup timer, watchdog timer, and external alert transition proof
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

- Public MCP hardening proof on 2026-09-06: a harmless 60-request `GET /mcp`
  burst produced 49 HTTP 429 responses and 11 HTTP 405 responses; a JSON-RPC
  ping still returned HTTP 200. No tool call, order, or fill was made.
- The public dashboard now returns a truthful warm `WARMING` state in about
  0.16s and a cached `READY` state in about 0.06s after its background build;
  the ready state contained five symbols, 781 RTH samples per symbol, and 40
  receipts during this check.
- A benign watchdog fail/recovery transition delivered through the configured
  Healthchecks URL with `alert_transition=delivered`; the older `ALERT GAP`
  log entry records the prior missing-URL condition.
- Binance REST ping and `NVDABUSDT` ticker: passed.
- Binance public bStocks status for the canonical NVDAB contract: `TRADING`.
- Public token audit: `isSupported=false`, `hasResult=false`; contract verification
  reports registry-only, not a clean audit.
- Live public integration test: passed with
  `AFTERBELL_RUN_LIVE=1`.
- Alpaca read-only stock snapshot and paper-clock validation: HTTP 200.
- A live signed Binance balance snapshot verified P7 before and after the
  minimum order.
- Live D1 acceptance: order `54422149` filled `0.021 NVDAB` for
  `4.86192000 USDT`; post-trade account check found `0.020979 NVDAB` and
  `5.68314309 USDT` free. See [docs/live-acceptance.md](docs/live-acceptance.md).
- Integrated live guard evaluation: market-closure risk reduced on the closing ramp; liquidity, price disagreement, identity, and contract checks passed; **corporate-action status warns because Binance current-status verification does not guarantee advance corporate-action notice**.

## Calibration

The latest generated table is in `docs/calibration.md` and the README. At
2026-09-08 09:11 UTC it contained 38,185 measured books and 34,345 reference
prints, **781 RTH_OPEN samples per symbol out of 300 required**, and **1,440
CLOSED_HOLIDAY samples per symbol**. All five baseline medians are measured and
usable inside the declared rolling seven-day window.

Basis is measured across six observed market states. The `RTH_OPEN`
p75/p95/p99 remains 7.1/12.6/33.9 bps against live WATCH/DEGRADED/BROKEN bands
of 100/250/500 bps; the holiday rows are now measured rather than inferred.

The generated report is `CALIBRATED` in the sample-coverage sense: every
symbol has the required RTH baseline. The signed policy remains
`status: UNCALIBRATED` because manual review has not yet promoted its
market-closure, liquidity, or price-disagreement thresholds. This is an intentional safety hold, not a data-completeness claim.

The calibration command is reproducible and never edits live policy:

```
.venv/bin/python -m afterbell.calibrate --out docs/calibration.md
```
## Account-bound validation

1. Binance Agent OS is authenticated through the supported Codex MCP client;
   `codex mcp list` shows `binance-agent-os` enabled with `Auth: OAuth`. A
   read-only account probe succeeded with `canTrade: true`; the account was
   funded, tested, and post-trade verification completed.
2. `spot.exchangeInfo` reports `NVDABUSDT` `TRADING`,
   `isSpotTradingAllowed: true`, and `NOTIONAL.minNotional=5.00` USDT. This
   is not proof that the account is funded or jurisdiction-eligible for a
   real bStock trade.
3. The minimum NVDAB test filled as order `54422149` after fresh
   account-holder approval. The executor was disabled again after the test.
4. HTTPS and Google Drive backup are configured outside the repository.
   Healthchecks transition delivery was proven with a benign fail/recovery test;
   watchdog logs also retain an earlier `ALERT GAP` for the prior missing URL.

## Remaining gaps

Track the submission handoff in [`docs/submission-checklist.md`](docs/submission-checklist.md).

1. **Calibration review:** `CLOSED_HOLIDAY` is now measured (1,440 samples per symbol); a human must review the proposed thresholds before the signed policy can leave `UNCALIBRATED`.
2. **Backup/storage:** live Google Drive copy and stable-data verification passed at 2026-09-08 08:43 UTC, covering through 2026-09-07. The 14-day retention policy is implemented and isolated-test-covered; no production archive is old enough to have been pruned yet.
3. **Unattended signed snapshots:** a supported-client authentication path is still needed for safe, unattended position-snapshot publishing.
4. **D7 Skills Hub PR:** not opened.
5. **D11 video and submission mechanics:** not started.
6. **D8 Square publishing:** awaits Creator Center API key.
7. **D9 counterparty comparison:** continue the corrected post-fix sample through an even regular-hours/closure comparison.
8. **D6 corporate-action lookahead:** Binance current processing status is authoritative but does not guarantee advance notice; Alpaca reference validation is configured, not an independent corporate-action source.

## Known limitations

- AFTERBELL cannot fire Binance's Emergency Stop; that remains a manual web-UI
  control.
- The authenticated tokenized-securities skill query remains account-bound and
  is not claimed here. Codex OAuth and read-only Spot checks are verified, but
  bStock funding/jurisdiction eligibility and a real order remain unproven.
- The public token audit does not support bStocks, so contract verification's live fallback is the
  canonical registry alone.
- Backup/storage is live-verified but not transactional. The recorder is producing roughly 3.9 GB of raw data at this audit point. The 2026-09-08 08:43 UTC run used the service-writable rclone config, copied stable data, and passed `rclone check` through 2026-09-07. The job skips hot files and only prunes raw archives after an exact remote check at the 14-day boundary; no production archive has reached that boundary yet. This verifies a stable remote set, not an atomic point-in-time snapshot. The watchdog now treats missing, failed, or older-than-two-hours backup status as unhealthy. External alerting still needs its own transition proof. Credentials remain outside Git.
- The current box is in AWS eu-west-1 rather than the Tokyo region recommended
  by the build spec. Public REST currently passes, but that is not a guarantee
  for future Binance or Agent OS access.
- This is a technical demonstration, not investment advice, an offer, a
  solicitation, or a claim of direct ownership of underlying shares.

## Next automatic milestones

- Review the proposed threshold values against the captured holiday sample; do
  not promote them automatically, and keep execution disabled while the signed
  policy is `UNCALIBRATED`.
- Keep the hourly backup and watchdog timers active; inspect the next status
  record and exercise production retention only when an archive reaches 14 days.
- Complete the corrected counterparty sample and the external submission work.
