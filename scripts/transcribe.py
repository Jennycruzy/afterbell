#!/usr/bin/env python3
"""Credential-free governed-execution handoff for a supported MCP client.

Python never receives a Binance bearer token and never calls Binance. It
verifies and atomically reserves a signed authorization, writes exact MCP tool
arguments for Codex, then records Codex's saved raw response.

Usage:
    python scripts/transcribe.py --auth auth.json --prepare placement.json
    python scripts/transcribe.py --auth auth.json --finalize response.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from afterbell.authorization import (                              # noqa: E402
    AuthorizationError, load_public_key, nonce_finalized, nonce_reserved, parse, redemption_record, reserve, verify,
)
from afterbell.ledger import Ledger                                # noqa: E402

DEFAULT_LEDGER = ROOT / "data" / "receipts.jsonl"
DEFAULT_PUBKEY = ROOT / "config" / "authorization.pub"


def placed_notional(response: dict) -> float:
    """What the venue says was actually spent, never what we hoped it spent.

    The redemption record puts requested, permitted and placed side by side so
    the three can be compared. Copying the permitted amount into the placed
    field would make that comparison vacuous and would defeat the
    placed-exceeds-permitted check downstream, so the number is read from the
    venue response or the finalize is refused. Binance spells the field
    `cummulativeQuoteQty`; the correct spelling is accepted too.
    """
    for key in ("cummulativeQuoteQty", "cumulativeQuoteQty"):
        if key in response:
            try:
                return float(response[key])
            except (TypeError, ValueError):
                raise AuthorizationError(
                    f"venue response has an unreadable {key}: "
                    f"{response[key]!r}") from None
    raise AuthorizationError(
        "venue response carries no cummulativeQuoteQty, so the amount actually "
        "spent cannot be measured; refusing to record an assumed one")


def placement_manifest(auth):
    """Exact credential-free arguments a supported MCP client may submit."""
    return {
        "kind": "afterbell.place-order.v1",
        "nonce": auth.nonce,
        "authorization": auth.to_dict(),
        "tool_arguments": {
            "symbol": auth.symbol, "side": auth.side, "type": "MARKET",
            "quoteOrderQty": f"{auth.permitted_notional:.2f}",
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--auth", required=True, help="path to the signed artifact")
    ap.add_argument("--pubkey", default=str(DEFAULT_PUBKEY))
    ap.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    action = ap.add_mutually_exclusive_group()
    action.add_argument("--prepare", metavar="PATH",
                        help="atomically reserve once and write exact Codex MCP arguments")
    action.add_argument("--finalize", metavar="PATH",
                        help="write the child receipt from Codex saved MCP response")
    ap.add_argument("--placed-by", default="codex-mcp")
    args = ap.parse_args(argv)

    auth = parse(Path(args.auth).read_text())
    pub = load_public_key(args.pubkey)

    try:
        # Verification is always local; only preparation consumes the nonce.
        (reserve(auth, pub, args.ledger) if args.prepare
         else verify(auth, pub, check_expiry=not bool(args.finalize)))
    except AuthorizationError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    print(f"authorization {auth.nonce} verified")
    print(f"  requested  {auth.requested_notional:,.2f} USDT")
    print(f"  permitted  {auth.permitted_notional:,.2f} USDT "
          f"(bound by {auth.binding_constraint})")
    print(f"  placing    {auth.permitted_notional:,.2f} USDT {auth.side} {auth.symbol}")
    print(f"  expires in {auth.seconds_remaining():.0f}s")

    if args.finalize:
        if not nonce_reserved(args.ledger, auth.nonce):
            print("REFUSED: authorization was never reserved for Codex", file=sys.stderr)
            return 2
        if nonce_finalized(args.ledger, auth.nonce):
            print("REFUSED: authorization was already finalized", file=sys.stderr)
            return 2
        try:
            response = json.loads(Path(args.finalize).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"REFUSED: invalid saved MCP response: {exc}", file=sys.stderr)
            return 2
        if not isinstance(response, dict):
            print("REFUSED: saved MCP response must be a JSON object", file=sys.stderr)
            return 2
        order_id = str(response.get("orderId") or response.get("order_id") or "")
        try:
            spent = placed_notional(response)
        except AuthorizationError as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 2
        try:
            written = Ledger(args.ledger).append_once(
                redemption_record(auth, placed_notional=spent,
                                  order_id=order_id or None, venue_response=response,
                                  placed_by=args.placed_by),
                field="nonce", value=auth.nonce,
                kinds={"authorization_redeemed"})
        except RuntimeError:
            print("REFUSED: authorization was already finalized", file=sys.stderr)
            return 2
        print(f"finalized order_id={order_id or 'unknown'} "
              f"placed={spent:.8f} of {auth.permitted_notional:.2f} permitted "
              f"receipt seq={written['seq']} hash={written['hash'][:16]}")
        return 0

    if not args.prepare:
        print("verified: no Binance call, no nonce consumed")
        return 0

    manifest = placement_manifest(auth)
    Path(args.prepare).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"reserved. Codex may submit exactly {auth.permitted_notional:.2f} "
          f"{auth.side} {auth.symbol}; save its raw response for finalization")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
