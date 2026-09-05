#!/usr/bin/env python3
"""The transcriber: places exactly what an authorization permits, and nothing else.

This is the boring half of the design, and boring is the point. Binance rejects
a standalone PKCE client as an unsupported agent, so AFTERBELL cannot hold a
bearer token. A supported MCP client can. This script is what that client runs.

It does four things and refuses everything else:

    1. read a signed authorization
    2. verify signature, expiry, monotonicity and replay
    3. place exactly `permitted_notional` through the order tool it discovers
    4. write the fill back into the ledger as a child of the decision receipt

There is **no decision logic here**. It has no thresholds, no market data, no
opinion about size, and no branch that could produce a larger order than the
artifact carries. When a judge asks "could the agent have placed more?", the
answer is a signature check rather than an assurance.

Nothing about the placement step trusts the caller: the size comes from a
signed field, and `--notional` may only ever lower it.

Usage:
    python scripts/transcribe.py --auth auth.json                    # verify only
    python scripts/transcribe.py --auth auth.json --place --token "$TOKEN"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from afterbell.authorization import (                              # noqa: E402
    AuthorizationError, check_redeemable, load_public_key, parse,
    redemption_record,
)
from afterbell.ledger import Ledger                                # noqa: E402

DEFAULT_LEDGER = ROOT / "data" / "receipts.jsonl"
DEFAULT_PUBKEY = ROOT / "config" / "authorization.pub"


def _place(token: str, symbol: str, side: str, notional: float) -> dict:
    """Call the order tool the authenticated server actually exposes.

    Imported here rather than at module scope so that a dry run needs no
    credential and touches no network path at all.
    """
    from afterbell.executor import _mcp_place_order
    return _mcp_place_order(token, {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quoteOrderQty": f"{notional:.2f}",
    })


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--auth", required=True, help="path to the signed artifact")
    ap.add_argument("--pubkey", default=str(DEFAULT_PUBKEY))
    ap.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    ap.add_argument("--notional", type=float, default=None,
                    help="place less than permitted. It can only lower the "
                         "size; a larger value is refused, not clamped")
    ap.add_argument("--place", action="store_true",
                    help="actually place. Without it this verifies and stops")
    ap.add_argument("--token", default=None,
                    help="bearer token from the supported MCP client")
    ap.add_argument("--placed-by", default="codex-mcp")
    args = ap.parse_args(argv)

    auth = parse(Path(args.auth).read_text())
    pub = load_public_key(args.pubkey)

    try:
        check_redeemable(auth, pub, args.ledger)
    except AuthorizationError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    notional = auth.permitted_notional
    if args.notional is not None:
        if args.notional > auth.permitted_notional:
            # Refused rather than silently clamped: a caller asking for more
            # than was authorized has made an error worth surfacing.
            print(f"REFUSED: --notional {args.notional} exceeds the permitted "
                  f"{auth.permitted_notional}", file=sys.stderr)
            return 2
        notional = args.notional

    print(f"authorization {auth.nonce} verified")
    print(f"  requested  {auth.requested_notional:,.2f} USDT")
    print(f"  permitted  {auth.permitted_notional:,.2f} USDT "
          f"(bound by {auth.binding_constraint})")
    print(f"  placing    {notional:,.2f} USDT {auth.side} {auth.symbol}")
    print(f"  expires in {auth.seconds_remaining():.0f}s")

    if not args.place:
        print("dry run: nothing placed, nothing redeemed")
        return 0
    if not args.token:
        print("REFUSED: --place needs --token from the supported MCP client",
              file=sys.stderr)
        return 2

    response = _place(args.token, auth.symbol, auth.side, notional)
    order_id = str(response.get("orderId") or response.get("order_id") or "")
    record = redemption_record(auth, placed_notional=notional,
                              order_id=order_id or None,
                              venue_response=response,
                              placed_by=args.placed_by)
    written = Ledger(args.ledger).append(record)
    print(f"placed. order_id={order_id or 'unknown'} "
          f"receipt seq={written['seq']} hash={written['hash'][:16]}")
    print(json.dumps(response, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
