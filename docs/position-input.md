# Trusted position input and execution activation

AFTERBELL does not fetch account positions. The D5/P7 aggregate-exposure gate
accepts only a short-lived position snapshot signed by a trusted supported
client. This is an account-state trust boundary, not a market-data setting.

The safe order is:

1. Obtain the Ed25519 public key from the supported-client position publisher.
   Keep the matching private key only in that publisher. Do not commit it, put
   it in AFTERBELL, or pass a Binance OAuth token to Python.
2. Install the public key on the VPS as `/etc/afterbell/position.pub`,
   owned by `root:root` and mode `0644`. Record its fingerprint
   out of band and verify it with the account holder before trusting snapshots.
3. Establish the publisher that emits a fresh signed JSON snapshot at least
   every 120 seconds. Its signed fields are exactly:

   ```json
   {
     "as_of": "2026-09-06T00:00:00+00:00",
     "positions": {"NVDABUSDT": 0.0},
     "source": "supported-client",
     "signature": "ed25519:<hex>"
   }
   ```

   `positions` contains signed USDT net-position notionals: positive is net
   long and negative is net short. Every symbol counts toward the gross cap.
4. Submit a harmless read-only evaluation with the snapshot and confirm the
   receipt reports `P7` as `VERIFIED`, with the expected snapshot
   digest, source, age, and gross exposure. A stale, future, unsigned, or
   incorrectly signed snapshot must be refused.
5. Only after that evidence exists, set `exposure.require_snapshot: true`.
   Enable `executor.enabled` only in a deliberate, reviewed policy change;
   the loader refuses an executable policy without both the requirement and the
   configured public key.
6. Restart and verify the guard/MCP services after the policy or external key
   configuration changes. Keep the first funded test separate and manually
   approved.
7. Fund the connected Spot account only after steps 1–6 are complete. Then,
   and only with fresh account-holder approval, perform the minimum valid D1
   test through the supported client and retain its order/fill receipt.

The shipped policy intentionally remains `executor.enabled: false`,
`exposure.require_snapshot: false`, and read-only. On the current VPS the
trusted public key and a live snapshot publisher are not configured yet, so no
funding or order test is ready to run.
