"""Continuous read-only guard evaluator for the VPS.

This service evaluates a small advisory request every minute and writes the
latest deterministic state for the dashboard. Every evaluation is written to
the hash-chained receipt ledger. It never calls the executor and never receives
an OAuth token.
"""
from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from afterbell.engine import Guard
from afterbell.guard import OrderRequest, to_receipt
from afterbell.measure import Side
from afterbell.policy import load as load_policy
from afterbell.posture import change_record, observe, transitions

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "guard_state.json"
POSTURE = ROOT / "data" / "posture.json"
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


def _state_from(req: OrderRequest, decision, *, receipt_seq: int,
                receipt_hash: str) -> dict:
    receipt = to_receipt(decision, req)
    return {
        "ts": _iso(),
        "symbol": req.symbol,
        "receipt_seq": receipt_seq,
        "receipt_hash": receipt_hash,
        "evaluation_source": req.evaluation_source,
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
        "policy_status": receipt["policy_status"],
        "rationale": receipt["rationale"],
        "note": receipt["rationale"],
        "corporate_action_note": receipt.get("corporate_action_note"),
        "corporate_action_source": receipt.get("corporate_action_source"),
        "corporate_action_lookahead": receipt.get("corporate_action_lookahead"),
    }


def _last_posture() -> dict | None:
    """The bands as they stood on the previous cycle, across restarts.

    Held on disk so a restart does not lose a transition, and so the first
    cycle after one compares against what was really seen rather than
    reporting a change that did not happen.
    """
    try:
        return json.loads(POSTURE.read_text())["after"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def notice_change(guard: Guard, state: dict, pol) -> dict | None:
    """Compare this cycle with the last and record it only if it moved.

    This is the whole of the service's initiative: nobody asked, and most
    cycles produce nothing. It writes an observation, never an authorization,
    because there is no proposal here to bind one to.
    """
    from afterbell.posture import Posture

    now = observe(state, pol)
    stored = _last_posture()
    before = Posture(**stored) if stored else None
    moved = transitions(before, now)
    if not moved:
        _write_json(POSTURE, {"ts": _iso(), "after": now.to_dict()})
        return None
    record = guard.ledger.append(change_record(
        before, now, moved, ts=_iso(),
        receipt_seq=state.get("receipt_seq"),
        receipt_hash=state.get("receipt_hash")))
    _write_json(POSTURE, {"ts": _iso(), "after": now.to_dict(),
                          "last_change_seq": record["seq"]})
    return record


def evaluate_once(guard: Guard, req: OrderRequest):
    """Evaluate, receipt, and publish one monitor cycle atomically by order.

    ``Guard.evaluate`` is the one receipt-writing surface. Keeping this
    service on it means a displayed refusal or pass always has a linked,
    hash-chained receipt; failures before that point become explicit gaps.
    """
    ctx = guard.build_context(req)
    decision = guard.evaluate(req, ctx)
    _write_json(STATE, _state_from(req, decision,
                                   receipt_seq=guard.ledger.seq,
                                   receipt_hash=guard.ledger.head))
    HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT.write_text(_iso() + "\n")
    try:
        change = notice_change(guard, _state_from(
            req, decision, receipt_seq=guard.ledger.seq,
            receipt_hash=guard.ledger.head), guard.policy)
        if change is not None:
            print(f"[{_iso()}] noticed change seq={change['seq']} "
                  f"{[c['band'] for c in change['changed']]}", flush=True)
    except Exception as exc:                 # noticing must never stop guarding
        _gap(f"posture: {type(exc).__name__}: {exc}")
    return decision


def run(interval: float = 60.0, symbol: str = "NVDABUSDT") -> None:
    policy = load_policy()
    guard = Guard(policy)
    req = OrderRequest(symbol.upper(), Side.BUY, policy.base_notional,
                       query="read-only monitor: buy Nvidia",
                       evaluation_source="continuous_read_only_monitor")
    while RUNNING:
        started = time.monotonic()
        try:
            decision = evaluate_once(guard, req)
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
