"""D5 aggregate gross-exposure gate tests."""
import copy
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from afterbell.guard import OrderRequest, Verdict, evaluate, to_receipt
from afterbell.measure import Side
from afterbell.policy import PolicyError, load
from afterbell.positions import PositionSnapshot, sign_snapshot

from tests.test_guard import POL, ctx_at, req


def exposure_policy(tmp_path: Path, *, require: bool = True,
                    cap: float = 100.0):
    key = Ed25519PrivateKey.generate()
    public_path = tmp_path / "position.pub"
    public_path.write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo))
    raw = copy.deepcopy(POL.raw)
    raw["exposure"] = {
        "max_gross_usdt": cap,
        "snapshot_max_age_s": 120.0,
        "position_public_key": str(public_path),
        "require_snapshot": require,
    }
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(raw))
    return load(policy_path), key


def signed_positions(ctx, key, positions, age_s=30.0):
    snap = PositionSnapshot(
        as_of=(ctx.clock.ts - timedelta(seconds=age_s)).isoformat(),
        positions=positions, source="codex-supported-client")
    return sign_snapshot(snap, key)


def test_missing_snapshot_blocks_when_execution_evidence_is_required(tmp_path):
    pol, _ = exposure_policy(tmp_path)
    d = evaluate(req(10.0), ctx_at("2026-09-03T15:00:00"), pol)
    assert d.verdict is Verdict.BLOCK
    assert d.allowed_notional == 0.0
    assert d.binding_constraint == "P7"
    p7 = next(g for g in d.gates if g.name == "P7")
    assert p7.measurements["exposure_check"] == "REQUIRED_BUT_MISSING"


def test_signed_snapshot_caps_new_gross_exposure_across_symbols(tmp_path):
    pol, key = exposure_policy(tmp_path)
    ctx = ctx_at("2026-09-03T15:00:00")
    ctx.position_snapshot = signed_positions(
        ctx, key, {"NVDABUSDT": 20.0, "TSLABUSDT": 70.0})
    d = evaluate(req(20.0), ctx, pol)
    assert d.verdict is Verdict.REDUCE
    assert d.allowed_notional == pytest.approx(10.0)
    assert d.binding_constraint == "P7"
    p7 = next(g for g in d.gates if g.name == "P7")
    assert p7.measurements["exposure_check"] == "VERIFIED"
    assert p7.measurements["gross_exposure_usdt"] == pytest.approx(90.0)
    assert p7.measurements["max_order_usdt"] == pytest.approx(10.0)


def test_reducing_order_can_close_an_over_ceiling_position(tmp_path):
    pol, key = exposure_policy(tmp_path)
    ctx = ctx_at("2026-09-03T15:00:00")
    ctx.position_snapshot = signed_positions(ctx, key, {"NVDABUSDT": 120.0})
    order = OrderRequest("NVDABUSDT", Side.SELL, 20.0, query="buy Nvidia")
    d = evaluate(order, ctx, pol)
    assert d.verdict is Verdict.PASS
    assert d.allowed_notional == pytest.approx(20.0)
    assert d.binding_constraint == "none"
    assert next(g for g in d.gates if g.name == "P7").measurements[
        "max_order_usdt"] == pytest.approx(120.0)


def test_tampered_snapshot_blocks_even_when_market_checks_pass(tmp_path):
    pol, key = exposure_policy(tmp_path)
    ctx = ctx_at("2026-09-03T15:00:00")
    signed = signed_positions(ctx, key, {"NVDABUSDT": 1.0})
    ctx.position_snapshot = replace(signed, positions={"NVDABUSDT": 0.0})
    d = evaluate(req(1.0), ctx, pol)
    assert d.verdict is Verdict.BLOCK
    assert "P7" in d.binding_constraint
    assert "signature" in d.rationale.lower()


def test_stale_snapshot_blocks(tmp_path):
    pol, key = exposure_policy(tmp_path)
    ctx = ctx_at("2026-09-03T15:00:00")
    ctx.position_snapshot = signed_positions(ctx, key, {"NVDABUSDT": 1.0},
                                             age_s=121.0)
    d = evaluate(req(1.0), ctx, pol)
    assert d.verdict is Verdict.BLOCK
    assert "P7" in d.binding_constraint
    assert "freshness" in d.rationale


def test_receipt_commits_snapshot_identity_without_raw_positions(tmp_path):
    pol, key = exposure_policy(tmp_path)
    ctx = ctx_at("2026-09-03T15:00:00")
    ctx.position_snapshot = signed_positions(
        ctx, key, {"NVDABUSDT": 20.0, "TSLABUSDT": 70.0})
    order = req(20.0)
    receipt = to_receipt(evaluate(order, ctx, pol), order)
    assert receipt["measurements"]["exposure_check"] == "VERIFIED"
    assert len(receipt["measurements"]["snapshot_digest"]) == 64
    assert "positions" not in receipt["measurements"]


def test_enabled_executor_policy_must_require_position_snapshot(tmp_path):
    raw = copy.deepcopy(POL.raw)
    raw["executor"] = {
        "enabled": True, "max_order_usdt": 25.0,
        "symbols": ["NVDABUSDT"], "require_manual_invocation": True,
    }
    raw["exposure"]["require_snapshot"] = False
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(PolicyError, match="require_snapshot"):
        load(path)
