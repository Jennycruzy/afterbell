"""Execution: the only module in this repository that can place an order.

It is deliberately the smallest thing here, and deliberately not importable
from the package root. `from afterbell import Guard` still reaches nothing that
can trade; you have to ask for this module by name.

The design rule is one sentence: **the executor cannot originate an order.** It
takes a Decision the guard already produced and does nothing but shrink it. It
has no opinion about price, no symbol of its own, no schedule, and no way to
construct a request. If the guard did not permit something, there is no code
path here that invents it.

Four ceilings apply, in this order, and each can only reduce:

  1. the guard's permitted notional        (measured)
  2. the policy's `executor.max_order_usdt` (a number a human chose by hand)
  3. the policy's symbol allowlist          (absent means blocked)
  4. `executor.enabled`                     (false unless deliberately edited)

None of them can raise the size. That is what makes it safe to hand this a
token: the worst case is that every check passes and it places exactly what the
guard already said was acceptable, capped by a hand-chosen number.

Law 4: the execution is receipted like everything else, and the receipt carries
the hash of the guard decision that authorised it. An order with no matching
decision receipt is an order this system did not place.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from afterbell.guard import Decision, OrderRequest, Verdict
from afterbell.policy import Policy

MCP_URL = "https://agent.binance.com/mcp/agentic"
ROOT = Path(__file__).resolve().parent.parent
EXECUTION_LEDGER = ROOT / "data" / "executions.jsonl"


class ExecutionRefused(RuntimeError):
    """Raised loudly, and the reason is recorded. Never swallowed."""


@dataclass(frozen=True)
class ExecutionPlan:
    symbol: str
    side: str
    notional: float
    guard_permitted: float
    requested: float
    binding_ceiling: str
    policy_sha256: str

    @property
    def was_capped(self) -> bool:
        return self.notional < self.guard_permitted


def plan(decision: Decision, req: OrderRequest, pol: Policy) -> ExecutionPlan:
    """Turn a decision into an order, or refuse and say which ceiling bound.

    Every branch here refuses. There is no branch that increases a number.
    """
    if not pol.executor_enabled:
        raise ExecutionRefused(
            "execution is disabled in policy; enable it by editing the "
            "checksummed file, which is the only way it can be enabled")

    if decision.verdict is Verdict.BLOCK or decision.allowed_notional <= 0:
        raise ExecutionRefused(
            f"the guard returned {decision.verdict.value} with "
            f"{decision.allowed_notional:,.2f} permitted; there is no order "
            f"to place. Binding: {decision.binding_constraint}")

    if req.symbol.upper() not in pol.executor_symbols:
        raise ExecutionRefused(
            f"{req.symbol} is not in the execution allowlist "
            f"({', '.join(sorted(pol.executor_symbols)) or 'empty'}); an "
            "allowlist absence blocks even when every protection passed")

    cap = pol.executor_max_order_usdt
    notional = min(decision.allowed_notional, cap)
    binding = ("executor.max_order_usdt" if cap < decision.allowed_notional
               else "guard")

    if notional <= 0:
        raise ExecutionRefused(f"capped to {notional:,.2f}; not an order")

    # Belt and braces. If this ever fires, something above it is wrong, and
    # placing the order anyway would be the failure this project describes.
    if notional > decision.allowed_notional or notional > req.notional:
        raise ExecutionRefused(
            f"refusing to place {notional:,.2f} against a permitted "
            f"{decision.allowed_notional:,.2f} and a requested "
            f"{req.notional:,.2f}")

    return ExecutionPlan(
        symbol=req.symbol.upper(), side=req.side.value, notional=notional,
        guard_permitted=decision.allowed_notional, requested=req.notional,
        binding_ceiling=binding, policy_sha256=decision.policy_sha256)


def _mcp(token: str, method: str, params: dict | None = None) -> dict:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    r = httpx.post(MCP_URL, json=body, timeout=45, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"})
    if r.status_code != 200:
        return {"_http": r.status_code, "_body": r.text[:400]}
    txt = r.text
    if txt.startswith("event:") or "\ndata: " in txt:
        for line in txt.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
    return r.json()


def _receipt(p: ExecutionPlan, decision_hash: str | None, sent: bool,
             response: Any) -> dict:
    return {
        "kind": "execution",
        "ts": datetime.now(timezone.utc)
              .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "symbol": p.symbol, "side": p.side,
        "requested_notional": p.requested,
        "guard_permitted_notional": p.guard_permitted,
        "placed_notional": p.notional,
        "binding_ceiling": p.binding_ceiling,
        "capped_below_guard": p.was_capped,
        "policy_sha256": p.policy_sha256,
        "decision_hash": decision_hash,
        "sent": sent,
        "response": response,
    }


def execute(p: ExecutionPlan, *, decision_hash: str | None = None,
            live: bool = False, ledger_path: Path | str = EXECUTION_LEDGER
            ) -> dict:
    """Place the planned order, or rehearse it.

    `live` defaults to False and must be passed explicitly. A dry run writes
    the same receipt with `sent: false`, so a rehearsal and a real execution
    are compared by reading one field rather than by remembering which was
    which.
    """
    token = os.environ.get("BINANCE_ACCESS_TOKEN", "").strip()
    response: Any = None
    sent = False

    if live:
        if not token:
            raise ExecutionRefused(
                "no BINANCE_ACCESS_TOKEN; run scripts/connect_binance.py")
        response = _mcp(token, "tools/call", {
            "name": "place_order",
            "arguments": {"symbol": p.symbol, "side": p.side,
                          "type": "MARKET", "quoteOrderQty": p.notional}})
        sent = True

    rec = _receipt(p, decision_hash, sent, response)
    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def render(p: ExecutionPlan, rec: dict) -> str:
    lines = [
        "",
        f"  EXECUTION  {'SENT' if rec['sent'] else 'DRY RUN - nothing placed'}",
        "",
        f"    requested        {p.requested:>12,.2f} USDT",
        f"    guard permitted  {p.guard_permitted:>12,.2f} USDT",
        f"    placed           {p.notional:>12,.2f} USDT",
        f"    bound by         {p.binding_ceiling}",
        "",
    ]
    if p.was_capped:
        lines.insert(-1, "    the hand-set execution cap bound below what the "
                         "guard already permitted")
        lines.insert(-1, "")
    return "\n".join(lines)


def main() -> None:
    """Guard first, then execute what it permitted. Nothing else.

    This is the finale: a reckless counterparty proposes a size, the guard
    measures the market and cuts it, and only what survives is placed.
    """
    import argparse

    from afterbell.engine import Guard, render as render_decision
    from afterbell.measure import Side
    from afterbell.policy import load as load_policy

    ap = argparse.ArgumentParser(
        description="Place only what the guard permits. Dry run by default.")
    ap.add_argument("--symbol", default="NVDABUSDT")
    ap.add_argument("--side", default="BUY", choices=["BUY", "SELL"])
    ap.add_argument("--notional", type=float, default=4000.0,
                    help="what the proposing agent asked for")
    ap.add_argument("--query", default="buy Nvidia")
    ap.add_argument("--policy", default=None)
    ap.add_argument("--live", action="store_true",
                    help="actually place the order. Without this nothing is "
                         "sent and the receipt records sent: false")
    a = ap.parse_args()

    pol = load_policy(a.policy)
    guard = Guard(pol)
    req = OrderRequest(a.symbol, Side(a.side), a.notional, query=a.query)
    decision = guard.evaluate(req)
    print(render_decision(decision))

    try:
        p = plan(decision, req, pol)
    except ExecutionRefused as exc:
        print(f"  EXECUTION REFUSED\n\n    {exc}\n")
        raise SystemExit(1)

    rec = execute(p, decision_hash=guard.ledger.head, live=a.live)
    print(render(p, rec))
    print(f"  decision receipt {guard.ledger.head[:16]}...  "
          f"policy {pol.sha256[:16]}...\n")


if __name__ == "__main__":
    main()
