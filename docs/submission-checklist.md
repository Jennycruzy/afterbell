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
- [x] The published data report contains 39,365 measured books, 35,520
  reference prints, 781 regular-hours observations per token, and 1,440
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

- [ ] Open the Skills Hub pull request in the required destination and report it
  as opened until the destination confirms its status.
- [ ] Record the public dashboard, public MCP surface, backup
  evidence, and the existing minimum-size acceptance record for the video and
  submission portal.
- [ ] Provide a supported-client authentication path for unattended
  signed account-position reports. Never move interactive OAuth into Python or
  a daemon.
- [ ] Explain that the current venue-status check does not guarantee advance
  notice of every corporate action.

## Safe final step before any live order

If a separate client ever submits an order, it must confirm the signed
settings, execution switch, configuration fingerprint, current signed
account-position report, and fresh market data before acting.
