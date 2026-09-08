# AFTERBELL submission checklist

Updated **8 September 2026 UTC**. This checklist uses the same plain language
as the public dashboard. It separates evidence already in the repository from
actions that still need an outside destination.

## Ready in the repository

- [x] Calendar-aware timing, liquidity, price-agreement, corporate-action,
  identity, contract, and account-exposure checks are implemented and tested.
- [x] Every decision and refusal is recorded in a hash-linked receipt history.
- [x] The current order limit is stored in signed settings, and this public
  build does not place orders.
- [x] New exposure requires a recent signed account-position report.
- [x] The published data report contains 39,895 measured books, 36,045
  reference prints, 868 regular-hours observations per token, and 1,440
  holiday observations per token.
- [x] Backup verification and the 14-day retention policy are deployed; no
  production archive has reached the deletion boundary yet.
- [x] The watchdog treats missing, failed, or older-than-two-hours backup
  status as unhealthy.
- [x] The public dashboard is live, color-coded, and shows the
  measurements behind each result.

## Next evidence

- [ ] Continue the corrected counterparty sample through an evenly covered
  regular-hours and closure comparison, then regenerate its report.

## Outside submission work

- [x] Skills Hub pull request opened:
  [binance/binance-skills-hub#337](https://github.com/binance/binance-skills-hub/pull/337).
  It is open and awaiting review; it is not merged, and it is reported as
  opened rather than accepted until that destination says otherwise.
- [ ] Record the public dashboard, public MCP surface, backup
  evidence, and the existing minimum-size acceptance record for the video and
  submission portal. Follow [`submission-runbook.md`](submission-runbook.md).
- [x] Keep unattended account authentication outside this package. A supported
  client can sign a fresh position report as documented in `position-input.md`;
  anonymous calls without that evidence deliberately fail closed. Moving
  interactive OAuth into Python would violate the credential boundary.
- [x] Explain that the current venue-status check does not guarantee advance
  notice of every corporate action.

The remaining video/portal checkbox requires the external submission
destination; it is not an unfinished code path.

## Safe final step before any live order

If a separate client ever submits an order, it must confirm the signed
settings, execution switch, configuration fingerprint, current signed
account-position report, and fresh market data before acting.
