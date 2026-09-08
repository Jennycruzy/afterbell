# AFTERBELL submission checklist

Updated **2026-09-08 UTC**. This checklist is deliberately split between
evidence that exists in the repository, human decisions still required, and
actions that need an external account or submission destination.

## Ready in the repository

- [x] Seven-check guard, hash-chained receipts, operator freeze, and
  credential-free authorization boundary are implemented and tested.
- [x] Authorization issuance is fail-closed unless `policy.status` is exactly
  `CALIBRATED`; the shipped policy remains `UNCALIBRATED` and
  `executor.enabled: false`.
- [x] The deployed policy requires `exposure.require_snapshot: true`; a
  missing or stale signed position snapshot blocks P7.
- [x] Generated calibration evidence includes 38,185 measured books, 34,345
  reference prints, 781 `RTH_OPEN` samples per symbol, and 1,440
  `CLOSED_HOLIDAY` samples per symbol.
- [x] Live backup verification passed at 2026-09-08 08:43 UTC through
  2026-09-07 using the service-writable rclone config. The job verifies stable
  data and has a 14-day retention policy; no production archive has yet
  reached the deletion boundary.
- [x] The watchdog now treats missing, failed, or older-than-two-hours backup
  status as unhealthy.

## Human review still required

- [ ] Review the generated holiday, liquidity, clock, and basis proposals
  against the policy’s current bands. Do not mark the signed policy calibrated
  from sample coverage alone.
- [ ] If the review approves changes, edit `config/policy.yaml` deliberately,
  record the new policy SHA, restart the source-backed services, and rerun the
  full tests and live read-only checks. Keep execution disabled until that
  decision is explicit.
- [ ] Continue the corrected counterparty sample through an even
  regular-hours/closure comparison, then regenerate `docs/counterparty.md`.

## External submission blockers

- [ ] D7 Skills Hub PR: open the PR in the required destination; report it as
  opened, not merged, until the destination confirms otherwise.
- [ ] D11 video and submission: record the read-only guard, P7 refusal, public
  dashboard/MCP, verified backup status, and the existing D1 acceptance record;
  submit the video and links through the required portal.
- [ ] Square publishing: obtain the Creator Center publishing credential and
  publish only sanitized blocks, digests, and public links.
- [ ] Unattended signed snapshots: obtain a supported-client authentication
  path and implement a root-operated publisher; never move the interactive
  Binance OAuth token into Python or a daemon.
- [ ] D6 corporate-action lookahead remains a documented limitation: Binance
  current processing status is checked, but advance notice is not guaranteed.

## Safe final gate

Before any future live execution decision, verify the policy status, executor
flag, current policy SHA, fresh signed position snapshot, and explicit human
approval. A generated calibration report marked `CALIBRATED` is not by itself
permission to change the signed policy.
