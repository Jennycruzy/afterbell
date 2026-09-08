# AFTERBELL — current status

Updated **8 September 2026 UTC**. This page is the operational companion to
the [live dashboard](https://afterbell.site). It separates what is running,
what is measured, and what still needs an explicit decision or outside access.

## The short version

The recorder, read-only dashboard, read-only MCP service, evaluator, backup
timer, and watchdog are running. The data archive is live. All five supported
tokens have enough regular-hours observations for comparison, including the
captured holiday period.

Live order permission is intentionally paused. The signed safety settings still
contain draft limits, and a current signed account-position report was not
provided to the latest decision. The system therefore shows an allowed amount
of **$0** rather than guessing.

## Running services

| Service | Public or local role | Current state |
|---|---|---|
| Recorder | Captures token books, trades, and reference prices | Active; no credential |
| Dashboard | Read-only operating view at `afterbell.site` | Active over HTTPS |
| MCP service | Read-only `evaluate_order` and `get_market_state` tools | Active over HTTPS |
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
- Read-only public dashboard and MCP surface.
- Signed short-lived authorization boundary, with live submission paused.
- Recorder, dashboard, evaluator, backup, and watchdog system services.
- Adversarial test corpus and ordinary-condition accuracy checks.

## Measured evidence

The published reports currently contain:

- 39,365 measured books and 35,520 reference prints;
- 781 regular-hours observations per supported token, with 300 required;
- 1,440 holiday observations per supported token;
- 35 hostile request patterns tested against two market conditions;
- zero hostile inputs that increased the permitted amount;
- 6/6 positive controls, showing that the test cannot pass by refusing every
  request; and
- a 1.00% refusal rate inside the specifically defined normal-book sample.

The live ledger is above 6,600 recorded decisions. The dashboard carries the
current counter and timestamps; the generated reports carry the reproducible
checkpoint used for the published measurements.

## Why live permission is paused

This is the distinction that matters:

- **Data coverage:** complete. The recorder has enough normal-hours data for
  every supported token, and the holiday period is represented.
- **Safety settings:** draft. The initial limits were written before the full
  measured distributions were available. A project owner must compare those
  proposed limits with the report and explicitly approve or revise them.

Until that decision is documented, the authorization issuer refuses to create a
live-order permission. No website action can bypass this hold.

## Why the latest decision is zero

The system must know current account exposure before adding more. The latest
request did not include a fresh signed account-position report, so the evaluator
refused to assume the account was empty. This is a data-integrity choice, not a
prediction about the token price.

## Remaining work

1. Record the owner decision on the proposed safety limits; keep live
   submission paused until then.
2. Continue the corrected trade-arrival sample through a balanced regular-hours
   and closure comparison.
3. Obtain an approved unattended authentication path for signed account
   reports; never move interactive OAuth into Python or a daemon.
4. Complete the external Skills Hub, video, and submission steps.
5. Document the limitation that current venue status does not guarantee future
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

See [`HANDOFF.md`](HANDOFF.md) and [`docs/submission-checklist.md`](docs/submission-checklist.md)
for the continuation plan.
