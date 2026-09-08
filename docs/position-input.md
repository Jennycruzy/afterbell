# Trusted position input and execution activation

AFTERBELL does not hold Binance credentials or fetch private account positions.
The D5/P7 gate accepts only a short-lived snapshot produced by the root-operated
balance reporter from a Binance Agent OS `spot.getAccount` export.

The safe order is:

1. Generate a dedicated Ed25519 keypair for the balance reporter. Keep its
   private key root-only at `/etc/afterbell/position-attestor.key`; do not
   commit it, reuse a Binance key, or pass a Binance OAuth token to Python.
2. Install the public key on the VPS as `/etc/afterbell/position.pub`,
   owned by `root:root` and mode `0644`. Record its fingerprint
   out of band and verify it with the account holder before trusting snapshots.
3. Call the read-only Binance Agent OS `spot.getAccount` tool and save an
   evidence envelope containing the exact result and capture time:

   ```json
   {"tool":"spot.getAccount","captured_at":"2026-09-06T00:00:00+00:00","result":{"balances":[]}}
   ```

   Invoke the reporter within 120 seconds:

   ```sh
   python -m afterbell.balance_reporter \
     --account-export data/account-export.json \
     --private-key /etc/afterbell/position-attestor.key \
     --output data/position-snapshot.json
   ```

   It rejects stale or malformed evidence, fetches public Binance prices,
   includes all five canonical bStock symbols, and emits signed JSON:

   ```json
   {
     "as_of": "2026-09-06T00:00:00+00:00",
     "positions": {"NVDABUSDT": 0.0},
     "source": "binance-agent-os/spot.getAccount;sha256=<evidence digest>",
     "signature": "ed25519:<hex>"
   }
   ```

   `positions` contains signed USDT net-position notionals: positive is net
   long and negative is net short. Every symbol counts toward the gross cap.
4. Submit a harmless read-only evaluation with the snapshot and confirm the
   receipt reports `P7` as `VERIFIED`, with the expected snapshot
   digest, source, age, and gross exposure. A stale, future, unsigned, or
   incorrectly signed snapshot must be refused.
5. Confirm `exposure.require_snapshot: true` remains set; do not disable it
   while the connected account has any exposure. Enable `executor.enabled` only
   in a deliberate, reviewed policy change;
   the loader refuses an executable policy without both the requirement and the
   configured public key.
6. Restart and verify the guard/MCP services after the policy or external key
   configuration changes. Keep the first funded test separate and manually
   approved.
7. Fund the connected Spot account only after steps 1–6 are complete. Then,
   and only with fresh account-holder approval, perform the minimum valid D1
   test through the supported client and retain its order/fill receipt.

The deployed policy keeps `executor.enabled: false` and is read-only, but now
sets `exposure.require_snapshot: true`. The dedicated attestor public key is
installed; every actionable evaluation must carry a fresh reporter snapshot.
Funding and an order test remain separate, explicitly approved operations.
