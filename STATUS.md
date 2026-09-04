# AFTERBELL — build status

Updated **2026-09-04 11:36 UTC**. This file separates code that is built from
external facts that still need an account holder or destination.

For the exact continuation point after the latest audit, read `HANDOFF.md`.

## Running unattended right now

| process | unit | credential boundary | state |
|---|---|---|---|
| Recorder | `afterbell-recorder.service` | none; Yahoo reference | active, enabled at boot |
| Dashboard | `afterbell-dashboard.service` | none | active on `0.0.0.0:8100` |
| Guard | `afterbell-guard.service` | no Binance OAuth; optional separate Alpaca P4 file | active, enabled at boot |
| Watchdog | `afterbell-watchdog.timer` | optional healthcheck URL | active, every 5 min |
| Backup | `afterbell-backup.timer` | optional rclone remote | active, hourly; records a gap until configured |

The recorder, dashboard and guard never load `.env`, so an Agent OS OAuth token
cannot stop or enter the market-data process. The executor is never invoked by
a service and the shipped policy has `executor.enabled: false`.

The dashboard is bound to the public interface and TCP 8100 is allowed in UFW.
A same-box request to the public IP timed out, so an external-browser reachability
check is still required; no domain or TLS certificate is claimed yet. Existing
nginx sites were not changed.

## Built

- Canonical registry, checksum validation, and full instrument resolution
- 60-second recorder for five bStock pairs: full depth (`limit=5000`), trades,
  `exchangeInfo` status, Yahoo regular-session reference data, and gap markers
- Market clock and `REFERENCE_AGE` over the checked-in 2026 calendar
- Measurements: spread, ±1% depth, walk cost, basis, RTH-only baselines
- Policy loader and monotone P1–P6 guard with signed policy SHA
- Hash-chained JSONL receipts for decisions and refusals
- Live public Binance bStocks status and token-audit adapters
- Optional Alpaca corporate-action lookahead, isolated from Yahoo pricing and
  strict on malformed/failed responses
- Streamable HTTP MCP session client, Codex-managed OAuth connection boundary,
  dynamic order-tool discovery, and redacted execution receipts
- Optional narration-only adapter; provider text cannot contain measurements or
  enter the decision
- Dashboard with recorded basis/age chart, calibration table, guard state,
  policy SHA and ledger head
- Systemd services, backup timer, watchdog timer, and explicit alert gaps
- Synthetic self-contained adversarial corpus and reckless counterparty tests

## Live evidence from this box

- Binance REST ping and `NVDABUSDT` ticker: passed.
- Binance public bStocks status for the canonical NVDAB contract: `TRADING`.
- Public token audit: `isSupported=false`, `hasResult=false`; P6 therefore
  reports registry-only, not a clean audit.
- Live public integration test: passed with
  `AFTERBELL_RUN_LIVE=1`.
- Yahoo is the active reference provider. Alpaca is not configured here.
- Integrated live guard evaluation: P1 reduced on the closing ramp, P2/P3/P5/P6
  pass, and P4 warns as a current-status fallback because Alpaca lookahead is
  not configured.

## Calibration

The latest generated table is in `docs/calibration.md` and the README. At
2026-09-03 19:43 UTC it contained 5,325 measured books, 1,507 reference prints,
and **374 RTH_OPEN samples per symbol out of 300 required**. All five baseline
medians are measured and usable inside the declared rolling seven-day window.
The signed policy remains `status: UNCALIBRATED` because its P1/P2/P3 thresholds
are still hypotheses; no threshold was silently promoted. Add the weekend and
holiday observations, then review the proposed values manually before changing
policy.

The calibration command is reproducible and never edits live policy:

```
.venv/bin/python -m afterbell.calibrate --out docs/calibration.md
```
## Account-bound validation still pending

1. Binance Agent OS is authenticated through the supported Codex MCP client;
   `python scripts/connect_binance.py` confirms configuration without reading
   Codex credentials. Run account/product checks through that MCP client.
2. A successful OAuth/read probe is not proof of bStocks trading eligibility.
   No real order has been sent. A $5 NVDAB test requires explicit account-holder
   approval and must be performed separately.
3. If Alpaca P4 lookahead is wanted, copy `.guard.env.example` to a mode-600
   `.guard.env` and supply the separate read-only corporate-action credentials.
   This does not switch Yahoo pricing.
4. Supply a domain for `deploy/publish.sh` to install the existing nginx/TLS
   route, and supply external rclone/healthcheck destinations to close the
   backup/alert gaps.

## Known limitations

- AFTERBELL cannot fire Binance's Emergency Stop; that remains a manual web-UI
  control.
- The authenticated tokenized-securities skill query and bStocks account or
  jurisdiction eligibility are not claimed until OAuth/account testing occurs.
- The public token audit does not support bStocks, so P6's live fallback is the
  canonical registry alone.
- The current box is in AWS eu-west-1 rather than the Tokyo region recommended
  by the build spec. Public REST currently passes, but that is not a guarantee
  for future Binance or Agent OS access.
- External backup, phone alerting, domain DNS and TLS need operator-supplied
  destinations.
- This is a technical demonstration, not investment advice, an offer, a
  solicitation, or a claim of direct ownership of underlying shares.

## Next automatic milestones

- Keep the recorder running through the Friday bell, Labor Day closure, and the
  Tuesday reopen; those states cannot be back-filled.
- Re-run calibration after the weekend, inspect proposed policy values manually,
  and only then decide whether the policy can be marked calibrated.
