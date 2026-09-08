# Trusted account-position input

AFTERBELL does not hold exchange credentials or fetch private account positions.
Before allowing new exposure, it accepts only a short-lived, signed report
produced by the root-operated balance reporter from a supported client's
account export.

The purpose is straightforward: the evaluator must know what the account
already holds across all supported tokens before it can safely add more. If the
report is absent, stale, unsigned, or altered, new exposure is refused.

## Safe setup

1. Generate a dedicated Ed25519 keypair for the balance reporter. Keep the
   private key root-only at `/etc/afterbell/position-attestor.key`; never commit
   it, reuse an exchange key, or pass an OAuth token to Python.
2. Install the public key as `/etc/afterbell/position.pub`, owned by `root:root`
   and mode `0644`. Verify its fingerprint with the account holder out of band.
3. Call the supported client's account tool and save an evidence
   envelope with the exact result and capture time:

   ```json
   {"tool":"spot.getAccount","captured_at":"2026-09-06T00:00:00+00:00","result":{"balances":[]}}
   ```

4. Run the reporter within the configured freshness window:

   ```sh
   python -m afterbell.balance_reporter \
     --account-export data/account-export.json \
     --private-key /etc/afterbell/position-attestor.key \
     --output data/position-snapshot.json
   ```

5. The reporter rejects stale or malformed evidence, fetches public prices,
   includes all five canonical token symbols, and emits signed JSON:

   ```json
   {
     "as_of": "2026-09-06T00:00:00+00:00",
     "positions": {"NVDABUSDT": 0.0},
     "source": "binance-agent-os/spot.getAccount;sha256=<evidence digest>",
     "signature": "ed25519:<hex>"
   }
   ```

   `positions` contains signed USDT net-position notionals: positive is net
   long and negative is net short. Every supported symbol counts toward the
   gross exposure limit.

6. Submit a harmless evaluation with the report. Confirm the receipt
   says the account evidence was verified and includes its digest, source, age,
   and gross exposure. A stale, future, unsigned, or incorrectly signed report
   must be refused.
7. Restart and verify the evaluator and MCP services after key or settings
   changes. Keep any funded test separate from this evidence flow.

## Current deployment

The deployed settings require this account report for actionable evaluations,
while this build does not submit orders. The public dashboard explains a missing
report as **required account report missing** and shows why the allowed amount
is zero. Market-state calls do not need private account evidence.

A future unattended publisher still needs a supported-client authentication
path. Do not move interactive OAuth into Python, a daemon, or this
repository.
