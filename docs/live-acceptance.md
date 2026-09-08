# Live acceptance record

Updated **8 September 2026 UTC**. This record contains no account identifier or
credential. It documents one exact minimum-size acceptance
event; it is not a recommendation to trade.

## Account exposure and reference checks

- A dedicated Ed25519 account-report keypair is installed outside the
  repository; the private key is root-only.
- The exposure requirement is enabled for actionable evaluations.
- A supported-client account result was converted into a signed
  position report and verified by the installed public key.
- Alpaca stock snapshot and paper-clock requests returned HTTP 200.
- Yahoo remains the recorder's primary reference provider.
- The venue's public certificate-status path is the source for current
  processing status. A clear current response does not promise future notice.

## Minimum-size acceptance

The test used one exact minimum-size request: a market BUY of `NVDABUSDT`
spending 5.00 USDT, accepting the weekend-reference warning and fees.

- Decision: caution, requested 5.00, permitted 5.00 USDT
- Timing and price checks: reduced for the closed and stale reference market
- Identity and address checks: clear
- Account exposure: verified with zero pre-trade certificate exposure
- Venue order ID: `54422149`
- Venue status: `FILLED`
- Filled quantity: `0.021 NVDAB`
- Average fill price: `231.52 USDT`
- Cumulative quote spent: `4.86192000 USDT`
- Fee: `0.000021 NVDAB`
- Authorization nonce: consumed and finalized
- Child receipt hash: `06b4a0e9927ddfe630aa4e28390c3e85e17e357bc4b51a04c05f80a1a83c48d5`
- Child receipt sequence: `4480`, record kind `authorization_redeemed`
- Redeemed by: `codex-binance-agent-os` — the `placed_by` field on that record,
  naming the supported client that submitted it. AFTERBELL issued the
  authorization; it did not submit the order and holds no venue credential.
- Recorded side by side on that record: requested `5.00`, permitted `5.00`,
  placed `4.86192`. The placed figure is read back from the venue response
  rather than copied from the permitted amount, so the three can be compared.

The post-trade account check reported `0.020979 NVDAB` and
`5.68314309 USDT` free. A fresh signed post-trade report measured gross
certificate exposure at approximately `4.85516997 USDT`.

After the test, the system returned to its normal protected state. Any new
exposure requires a fresh signed account report.

## Remaining submission work

- Record and submit the demonstration.
- Open the Skills Hub pull request if required.
- Continue the corrected counterparty sample through a complete regular session
  and closure.
- Review the captured holiday data and proposed limits before changing
  the configuration.
- Provide a supported path for unattended account-report publishing.
