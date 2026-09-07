# Live acceptance record

Updated 2026-09-07 UTC. This record contains no Binance account identifier or
credential.

## D5/P7 and Alpaca

- Dedicated Ed25519 position-attestor keypair is installed outside the
  repository; the private key is root-only.
- The aggregate exposure requirement is enabled.
- A live Binance Agent OS spot.getAccount result was converted into a signed
  snapshot and verified by the installed public key.
- Alpaca credentials are stored outside Git in AFTERBELL's mode-600 guard
  environment. Read-only stock snapshot and paper-clock requests both returned
  HTTP 200.
- Yahoo remains the recorder's primary provider. Alpaca is an additional
  read-only reference path for the guard; Binance remains the source of
  current bStocks processing status.

## D1 live execution

The account holder approved one exact minimum test: a market BUY of
NVDABUSDT spending 5.00 USDT, accepting the weekend-reference warning and
fees.

- Guard decision: WARN, requested 5.00, permitted 5.00 USDT
- P1/P3: reduced for the closed and stale U.S. reference market
- P5/P6: passed
- P7: verified with zero pre-trade bStock exposure
- Binance order ID: 54422149
- Binance status: FILLED
- Filled quantity: 0.021 NVDAB
- Average fill price: 231.52 USDT
- Cumulative quote spent: 4.86192000 USDT
- Fee: 0.000021 NVDAB
- Authorization nonce: consumed and finalized
- Child receipt hash: 06b4a0e9927ddfe630aa4e28390c3e85e17e357bc4b51a04c05f80a1a83c48d5

The post-trade read-only account check reported 0.020979 NVDAB and
5.68314309 USDT free. A fresh signed post-trade snapshot verified P7 and
measured gross bStock exposure at approximately 4.85516997 USDT.

After the test, executor.enabled was returned to false. Future orders remain
manually gated and require a fresh signed snapshot and explicit approval.

## Remaining submission work

- Record the demo and submit the project.
- Open the Skills Hub PR if it is required by the submission.
- Continue the corrected counterparty sample through a complete regular
  session after the recorder fix.
- Review calibration proposals after the Labor Day holiday sample; do not
  promote thresholds automatically.
- Square publishing and unattended snapshot publishing still require their
  respective external credentials or automation authority.
