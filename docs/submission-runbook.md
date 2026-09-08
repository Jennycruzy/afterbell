# AFTERBELL judge runbook

Use this order for the submission video and live review. It explains the
product before showing the operations console.

## The two-minute story

1. **Problem — 15 seconds.** A Binance bStock token remains tradable while its
   U.S. reference market sleeps. An AI agent can otherwise size against an old
   reference without noticing.
2. **Autonomy — 20 seconds.** Show “Noticed without being asked.” AFTERBELL
   records material band changes on its own and authorizes nothing merely by
   observing them.
3. **Decision — 25 seconds.** Show the seven deterministic checks, requested
   amount, permitted amount, binding check, policy hash, and receipt hash.
4. **Expected public block — 15 seconds.** Explain that an anonymous visitor
   has no signed account-position evidence. Zero is the safe expected result,
   not a broken demo.
5. **Enforcement boundary — 25 seconds.** Say exactly: “Any agent can use the
   public advisory ceiling. In the governed path, a supported client redeems a
   short-lived, single-use authorization and cannot increase its amount.
   AFTERBELL does not control unrelated tools held by third parties.”
6. **Proof — 20 seconds.** Show order `54422149`: 5.00 USDT requested, 5.00
   permitted, 4.86192 actually spent, with the venue credential remaining in
   Binance Agent OS.

## Live checks before recording

```bash
curl -fsS https://afterbell.site/healthz
curl -fsS https://afterbell.site/api/status
curl -fsS https://afterbell.site/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
./scripts/qualitycheck.sh
```

Confirm that the quality status, recorder heartbeat, guard decision, backup,
and MCP endpoint are current. Do not place another live order for the video;
the existing minimum-size fill is the acceptance evidence.

## Claims to avoid

- Do not call all three MCP tools read-only: `evaluate_order` writes a receipt.
- Do not claim the public advisory path can constrain an unrelated credential.
- Do not claim guaranteed advance corporate-action notice.
- Do not describe a public missing-position refusal as a market prediction.
- Do not describe the historical fill as an open position.

## Recorded walkthrough

A two-and-a-half minute narrated walkthrough is recorded. It films the live
public dashboard as an anonymous visitor would see it, so every panel on
screen is the running system rather than a mock-up.

It states the test count, the coverage figure and the acceptance order on
screen. Re-record it if any of those change.
