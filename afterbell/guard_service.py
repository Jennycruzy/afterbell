"""Continuous read-only guard evaluator for the VPS.

This service evaluates a small advisory request every minute and writes the
latest deterministic state for the dashboard. It never calls the executor and
never receives an OAuth token. User/agent requests still go through
``afterbell.engine.Guard.evaluate`` when a receipt is required.
"""
from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from afterbell.engine import Guard
from afterbell.guard import OrderRequest, evaluate as guard_evaluate, to_receipt
from afterbell.measure import Side
from afterbell.policy import load as load_policy

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "guard_state.json"
HEARTBEAT = ROOT / "data" / "guard_heartbeat"
GAPS = ROOT / "data" / "guard_gaps.jsonl"
RUNNING = True


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as fh:
        json.dump(value, fh, sort_keys=True, default=str)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temp, path)


def _gap(reason: str) -> None:
    GAPS.parent.mkdir(parents=True, exist_ok=True)
    with GAPS.open("a", encoding="utf-8") as fh:
        json.dump({"kind": "gap", "ts": _iso(), "source": "guard-service",
                   "endpoint": "evaluation", "symbol": "NVDABUSDT",
                   "reason": reason[:500]}, fh, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())


def _state_from(req: OrderRequest, decision) -> dict:
    receipt = to_receipt(decision, req)
    return {
        "ts": _iso(),
        "status": decision.verdict.value,
        "allowed_notional": decision.allowed_notional,
        "requested_notional": decision.requested_notional,
        "binding_constraint": decision.binding_constraint,
        "market_state": receipt["market_state"],
        "reference_age_s": receipt["reference_age_s"],
        "reference_age": receipt["reference_age"],
        "reference_price": receipt["reference_price"],
        "reference_ts": receipt["reference_ts"],
        "token_price": receipt["token_price"],
        "gates": receipt["gates"],
        "gate_detail": receipt["gate_detail"],
        "measurements": receipt["measurements"],
        "policy_sha256": receipt["policy_sha256"],
        "rationale": receipt["rationale"],
        "note": receipt["rationale"],
        "corporate_action_note": receipt.get("corporate_action_note"),
        "corporate_action_source": receipt.get("corporate_action_source"),
        "corporate_action_lookahead": receipt.get("corporate_action_lookahead"),
    }


def run(interval: float = 60.0, symbol: str = "NVDABUSDT") -> None:
    policy = load_policy()
    guard = Guard(policy)
    req = OrderRequest(symbol.upper(), Side.BUY, policy.base_notional,
                       query="buy Nvidia")
    while RUNNING:
        started = time.monotonic()
        try:
            ctx = guard.build_context(req)
            decision = guard_evaluate(req, ctx, policy)
            _write_json(STATE, _state_from(req, decision))
            HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
            HEARTBEAT.write_text(_iso() + "\n")
            print(f"[{_iso()}] guard {decision.verdict.value} "
                  f"allowed={decision.allowed_notional}", flush=True)
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            _gap(reason)
            _write_json(STATE, {"ts": _iso(), "status": "UNKNOWN",
                                "allowed_notional": None,
                                "requested_notional": policy.base_notional,
                                "binding_constraint": "guard-service",
                                "note": reason})
            print(f"[{_iso()}] guard GAP {reason}", flush=True)
        delay = max(0.0, interval - (time.monotonic() - started))
        deadline = time.monotonic() + delay
        while RUNNING and time.monotonic() < deadline:
            time.sleep(min(1.0, deadline - time.monotonic()))


def _stop(signum, frame) -> None:
    global RUNNING
    RUNNING = False


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Run the read-only AFTERBELL guard")
    ap.add_argument("--interval", type=float, default=60.0)
    ap.add_argument("--symbol", default="NVDABUSDT")
    args = ap.parse_args()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    run(args.interval, args.symbol)


if __name__ == "__main__":
    main()
