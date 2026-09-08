# AFTERBELL — current status

Updated **8 September 2026 UTC**. This page is the operational companion to
the [live dashboard](https://afterbell.site). It separates what is running, what is
measured, and the known operating boundaries.

## The short version

The recorder, dashboard, MCP service, evaluator, backup timer, and watchdog
are running. The data archive is live. All five supported tokens have enough
regular-hours observations for comparison, including the captured holiday
period.

The current order limit is read from the signed settings. The latest decision
shows an allowed amount of **$0** because a current signed account-position
report was not supplied, so the system does not guess that the account is empty.

## Running services

| Service | Public or local role | Current state |
|---|---|---|
| Recorder | Captures token books, trades, and reference prices | Active; no credential |
| Dashboard | Public operating view at `afterbell.site` | Active over HTTPS |
| MCP service | Public `evaluate_order`, `get_market_state` and `get_safety_posture` tools | Active over HTTPS |
| Evaluator | Applies the measured data and safety settings | Active; no order submission |
| Watchdog | Watches service and backup health | Active every five minutes |
| Backup | Copies stable data to the configured remote | Active hourly |

The dashboard listens on loopback and nginx is the public entry point. TCP 8100
is not open through the firewall.

## Built and verified

- Five-token canonical registry with issuer, network, underlying, and checked
  contract addresses.
- 60-second full-depth book recorder, trade recorder, exchange status, and
  regular-session reference prices with explicit gap markers.
- Calendar-aware timing, reference-price age, spread, depth, fill-cost, price
  difference, and regular-hours comparisons.
- Seven independent safety questions combined into one smallest safe amount.
- Append-only, hash-linked decision history with a configuration fingerprint.
- Public dashboard and MCP surface.
- Unattended detection of material safety-state changes, recorded and
  explained without a request, authorising nothing.
- Signed decision records with the current order limit attached.
- Recorder, dashboard, evaluator, backup, and watchdog system services.
- Adversarial test corpus and ordinary-condition accuracy checks.

## Measured evidence

The published reports currently contain:

- 39,895 measured books and 36,045 reference prints;
- 868 regular-hours observations per supported token, with 300 required;
- 1,440 holiday observations per supported token;
- 35 hostile request patterns tested against two market conditions;
- zero hostile inputs that increased the permitted amount;
- 6/6 positive controls, showing that the test cannot pass by refusing every
  request;
- a 1.00% refusal rate inside the specifically defined normal-book sample; and
- 10 refusals for a missing signed account report, counted separately because
  they refuse on an absent input rather than on a measurement.

The live ledger is above 6,790 recorded decisions. The dashboard carries the
current counter and timestamps; the generated reports carry the reproducible
checkpoint used for the published measurements.

## Configure the order limit

The base amount for one request is stored in the signed `config/policy.yaml`
file. The dashboard displays that amount and the measured conditions that may
reduce it. The public dashboard is a monitoring and sizing surface; it does
not place orders.

## Why the latest decision is zero

The system must know current account exposure before adding more. The latest
request did not include a fresh signed account-position report, so the evaluator
refused to assume the account was empty. This is a data-integrity choice, not a
prediction about the token price.

## Remaining work

1. Continue the corrected trade-arrival sample through a balanced regular-hours
   and closure comparison.
2. Provide a supported unattended authentication path for signed account
   reports; never move interactive OAuth into Python or a daemon.
3. Upload the recorded walkthrough and the write-up to the submission
   portal. The Skills Hub pull request is open at
   binance/binance-skills-hub#337 and awaiting review.
4. Document the limitation that current venue status does not guarantee future
   corporate-action notice.

## Known limitations

- The system cannot invoke the venue's manual emergency-stop web control or
  cancel/flatten positions; it only controls its own authorization boundary.
- The counterparty-composition analysis is not directional yet because the
  historical trade sample was uneven before the recorder fix.
- Backup verification covers stable files at a checked point; it is not an
  atomic snapshot of hot files. Credentials remain outside Git.
- The public token-audit service does not support these certificates, so address
  verification relies on the checked canonical registry.
- This is a technical demonstration, not investment advice, an offer, a
  solicitation, or a claim of direct ownership of an underlying share.

See [`docs/submission-checklist.md`](docs/submission-checklist.md) for what remains.
