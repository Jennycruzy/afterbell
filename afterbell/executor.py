"""Execution planning only. The supported Codex MCP client is the only component that submits an order.

It is deliberately the smallest thing here, and deliberately not importable
from the package root. `from afterbell import Guard` still reaches nothing that
can trade; you have to ask for this module by name.

The design rule is one sentence: **the executor only plans; it cannot originate or submit an order.** It
takes a Decision the guard already produced and does nothing but shrink it. It
has no opinion about price, no symbol of its own, no schedule, and no way to
construct a request. If the guard did not permit something, there is no code
path here that invents it.

Four ceilings apply, in this order, and each can only reduce:

  1. the guard's permitted notional        (measured)
  2. the policy's `executor.max_order_usdt` (a number a human chose by hand)
  3. the policy's symbol allowlist          (absent means blocked)
  4. `executor.enabled`                     (false unless deliberately edited)

None of them can raise the size. The plan is signed into the authorization;
only a supported MCP client holds the OAuth session and may submit it.

Law 4: the execution is receipted like everything else, and the receipt carries
the hash of the guard decision that authorised it. An order with no matching
decision receipt is an order this system did not place.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from afterbell.guard import Decision, OrderRequest, Verdict
from afterbell.policy import Policy

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

    if not pol.is_calibrated:
        raise ExecutionRefused(
            "execution requires policy status CALIBRATED; current status is "
            f"{pol.status}")

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


def _redact(value: Any) -> Any:
    """Keep account identifiers and credentials out of execution receipts."""
    sensitive = {"authorization", "access_token", "refresh_token", "token",
                 "secret", "api_key", "account_id", "subaccount_id",
                 "sub_account_id", "email", "uid"}
    if isinstance(value, dict):
        return {key: ("[REDACTED]" if key.lower() in sensitive
                      else _redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _append_execution(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


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
    response: Any = None
    sent = False

    if live:
        raise ExecutionRefused(
            "AFTERBELL never receives a Binance OAuth token or calls the "
            "order endpoint. Prepare a signed authorization and let the "
            "supported Codex MCP client submit its exact arguments instead.")

    rec = _receipt(p, decision_hash, sent, _redact(response))
    _append_execution(Path(ledger_path), rec)
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
