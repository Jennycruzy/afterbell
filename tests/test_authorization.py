"""Authorization tests.

The artifact is handed to a client this package does not control, so each of
its five safety properties is asserted here rather than assumed: short-lived,
signed, single-use, monotone, chained.
"""
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from afterbell.authorization import (
    Authorization, AuthorizationError, check_redeemable, generate_keypair,
    issue, load_private_key, load_public_key, nonce_consumed, nonce_finalized,
    nonce_redeemed, nonce_reserved, parse, reserve,
    redemption_record, verify,
)
from afterbell.guard import Verdict, evaluate, to_receipt
from afterbell.ledger import Ledger

from tests.test_guard import POL, ctx_at, req

UNCALIBRATED_POL = replace(
    POL, raw=dict(POL.raw) | {"status": "UNCALIBRATED"})

RTH = "2026-09-03 15:00"
WEEKEND = "2026-09-05 22:00"


@pytest.fixture
def keys(tmp_path):
    pub = generate_keypair(tmp_path / "auth.key", tmp_path / "auth.pub")
    return load_private_key(tmp_path / "auth.key"), pub


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "receipts.jsonl")


def authorize(keys, ledger, when=RTH, notional=100.0, **kw):
    priv, pub = keys
    r = req(notional)
    d = evaluate(r, ctx_at(when), POL)
    receipt = ledger.append(to_receipt(d, r))
    return issue(d, r, receipt, priv, **kw), d, receipt


# ---------------- signed ----------------

def test_a_freshly_issued_authorization_verifies(keys, ledger):
    auth, d, _ = authorize(keys, ledger)
    verify(auth, keys[1])
    assert auth.permitted_notional == d.allowed_notional
    assert auth.signature.startswith("ed25519:")


def test_an_uncalibrated_policy_cannot_issue_authorization(keys, ledger):
    priv, _ = keys
    r = req(100.0)
    d = evaluate(r, ctx_at(RTH), UNCALIBRATED_POL)
    receipt = ledger.append(to_receipt(d, r))
    with pytest.raises(AuthorizationError, match="CALIBRATED"):
        issue(d, r, receipt, priv)


def test_tampered_permitted_notional_is_rejected(keys, ledger):
    """The acceptance test named in the continuation spec."""
    auth, _, _ = authorize(keys, ledger, notional=12.0)
    forged = Authorization(**(auth.to_dict() | {"permitted_notional": 5_000.0}))
    with pytest.raises(AuthorizationError, match="signature does not match"):
        verify(forged, keys[1])


@pytest.mark.parametrize("field,value", [
    ("symbol", "TSLABUSDT"),
    ("side", "SELL"),
    ("binding_constraint", "FABRICATED"),
    ("market_state", "CLOSED_WEEKEND"),
    ("policy_sha256", "0" * 64),
    ("receipt_seq", 999_999),
    ("receipt_hash", "f" * 64),
    ("expires_at", "2030-01-01T00:00:00+00:00"),
])
def test_no_signed_field_can_be_altered(keys, ledger, field, value):
    auth, _, _ = authorize(keys, ledger)
    forged = Authorization(**(auth.to_dict() | {field: value}))
    with pytest.raises(AuthorizationError):
        verify(forged, keys[1])


def test_another_key_cannot_sign_one(keys, ledger, tmp_path):
    """A well-formed signature from the wrong key is still refused."""
    auth, _, _ = authorize(keys, ledger)
    generate_keypair(tmp_path / "other.key", tmp_path / "other.pub")
    other = load_private_key(tmp_path / "other.key")
    resigned = Authorization(**(auth.to_dict() | {
        "signature": "ed25519:" + other.sign(auth.signing_bytes()).hex()}))
    with pytest.raises(AuthorizationError, match="signature does not match"):
        verify(resigned, keys[1])


def test_unsigned_artifact_is_rejected(keys, ledger):
    auth, _, _ = authorize(keys, ledger)
    with pytest.raises(AuthorizationError, match="not Ed25519-signed"):
        verify(Authorization(**(auth.to_dict() | {"signature": ""})), keys[1])


def test_round_trips_through_json(keys, ledger):
    """A re-serialised artifact still verifies, or the transcriber is useless."""
    auth, _, _ = authorize(keys, ledger)
    verify(parse(auth.to_json()), keys[1])


def test_an_extra_field_is_refused_rather_than_ignored(keys, ledger):
    """A field outside the signature must not be silently dropped."""
    body = authorize(keys, ledger)[0].to_dict() | {
        "max_notional_override": 1e9}
    with pytest.raises(AuthorizationError, match="unknown authorization fields"):
        parse(json.dumps(body))


def test_a_missing_field_is_refused(keys, ledger):
    body = authorize(keys, ledger)[0].to_dict()
    body.pop("policy_sha256")
    with pytest.raises(AuthorizationError, match="missing fields"):
        parse(json.dumps(body))


# ---------------- short-lived ----------------

def test_ttl_defaults_to_two_minutes(keys, ledger):
    auth, _, _ = authorize(keys, ledger)
    assert 0 < auth.seconds_remaining() <= 120


def test_an_expired_authorization_is_refused(keys, ledger):
    auth, _, _ = authorize(keys, ledger)
    later = datetime.now(timezone.utc) + timedelta(seconds=121)
    with pytest.raises(AuthorizationError, match="expired"):
        verify(auth, keys[1], now=later)


def test_expiry_is_signed_so_it_cannot_be_extended(keys, ledger):
    auth, _, _ = authorize(keys, ledger)
    stretched = Authorization(**(auth.to_dict() | {
        "expires_at": (datetime.now(timezone.utc)
                       + timedelta(days=1)).isoformat(timespec="seconds")}))
    with pytest.raises(AuthorizationError, match="signature does not match"):
        verify(stretched, keys[1])


# ---------------- monotone ----------------

def test_permitted_never_exceeds_requested(keys, ledger):
    """The guard's min() holds all the way into the artifact."""
    for notional in (1.0, 12.0, 100.0, 5_000.0):
        auth, d, _ = authorize(keys, ledger, notional=notional)
        assert auth.permitted_notional <= auth.requested_notional == notional


def test_a_reduced_weekend_request_is_authorized_for_the_reduced_size(keys, ledger):
    auth, d, _ = authorize(keys, ledger, when=WEEKEND, notional=5_000.0)
    assert d.verdict is Verdict.REDUCE
    assert auth.permitted_notional == d.allowed_notional < 5_000.0
    assert auth.binding_constraint == d.binding_constraint


def test_recording_more_than_permitted_is_refused(keys, ledger):
    auth, _, _ = authorize(keys, ledger, notional=100.0)
    with pytest.raises(AuthorizationError, match="exceeds permitted"):
        redemption_record(auth, placed_notional=auth.permitted_notional + 0.01,
                          order_id="x", venue_response=None, placed_by="test")


# ---------------- single-use ----------------

def test_replay_is_refused_after_redemption(keys, ledger, tmp_path):
    auth, _, _ = authorize(keys, ledger)
    check_redeemable(auth, keys[1], ledger.path)          # first time: fine
    ledger.append(redemption_record(
        auth, placed_notional=auth.permitted_notional, order_id="1",
        venue_response=None, placed_by="test"))
    assert nonce_redeemed(ledger.path, auth.nonce)
    with pytest.raises(AuthorizationError, match="already redeemed"):
        check_redeemable(auth, keys[1], ledger.path)


def test_nonces_are_unique(keys, ledger):
    seen = {authorize(keys, ledger)[0].nonce for _ in range(25)}
    assert len(seen) == 25


def test_an_unrelated_nonce_is_not_treated_as_redeemed(keys, ledger):
    auth, _, _ = authorize(keys, ledger)
    ledger.append({"kind": "decision", "nonce": auth.nonce})   # not a redemption
    assert not nonce_redeemed(ledger.path, auth.nonce)


def test_reservation_is_atomic_and_consumes_the_nonce(keys, ledger):
    auth, _, _ = authorize(keys, ledger)
    reserve(auth, keys[1], ledger.path)
    assert nonce_reserved(ledger.path, auth.nonce)
    assert nonce_consumed(ledger.path, auth.nonce)
    with pytest.raises(AuthorizationError, match="replay refused"):
        reserve(auth, keys[1], ledger.path)


def test_reservation_is_not_a_final_fill(keys, ledger):
    auth, _, _ = authorize(keys, ledger)
    reserve(auth, keys[1], ledger.path)
    assert not nonce_finalized(ledger.path, auth.nonce)
    ledger.append(redemption_record(
        auth, placed_notional=auth.permitted_notional, order_id="abc",
        venue_response={"orderId": "abc"}, placed_by="codex-supported-mcp"))
    assert nonce_finalized(ledger.path, auth.nonce)


# ---------------- chained ----------------

def test_it_names_the_decision_receipt_it_came_from(keys, ledger):
    auth, _, receipt = authorize(keys, ledger)
    assert auth.receipt_seq == receipt["seq"]
    assert auth.receipt_hash == receipt["hash"]
    assert auth.policy_sha256 == POL.sha256


def test_redemption_is_a_child_of_that_receipt(keys, ledger):
    auth, _, receipt = authorize(keys, ledger)
    rec = redemption_record(auth, placed_notional=1.0, order_id="abc",
                            venue_response={"status": "FILLED"},
                            placed_by="codex-mcp")
    assert rec["authorizes_receipt_seq"] == receipt["seq"]
    assert rec["authorizes_receipt_hash"] == receipt["hash"]
    assert (rec["requested_notional"], rec["permitted_notional"],
            rec["placed_notional"]) == (100.0, auth.permitted_notional, 1.0)


# ---------------- a blocked decision authorizes nothing ----------------

def test_a_block_authorizes_zero_and_cannot_be_redeemed(keys, ledger, tmp_path):
    """BLOCK is representable, and it is not redeemable."""
    priv, pub = keys
    kill = tmp_path / "FREEZE"
    kill.write_text("")
    from dataclasses import replace
    pol = replace(POL, raw=dict(POL.raw) | {
        "operator_freeze": {"kill_file": str(kill)}})
    r = req(100.0)
    d = evaluate(r, ctx_at(RTH), pol)
    receipt = ledger.append(to_receipt(d, r))
    auth = issue(d, r, receipt, priv)
    verify(auth, pub)                      # authentic
    assert auth.permitted_notional == 0.0
    assert auth.binding_constraint == "OPERATOR_FREEZE"
    with pytest.raises(AuthorizationError, match="permits nothing"):
        check_redeemable(auth, pub, ledger.path)


def test_private_key_file_is_not_world_readable(tmp_path):
    generate_keypair(tmp_path / "k", tmp_path / "k.pub")
    assert (tmp_path / "k").stat().st_mode & 0o077 == 0


# ---------------- the hand-chosen ceiling ----------------

def test_the_policy_cap_narrows_the_authorization(keys, ledger):
    """A ceiling a human chose by hand, applied where it is still signed."""
    priv, pub = keys
    r = req(5_000.0)
    d = evaluate(r, ctx_at(WEEKEND), POL)
    receipt = ledger.append(to_receipt(d, r))
    auth = issue(d, r, receipt, priv, cap=25.0)
    verify(auth, pub)
    assert d.allowed_notional > 25.0            # the guard permitted more
    assert auth.permitted_notional == 25.0
    assert auth.binding_constraint == "executor.max_order_usdt"


def test_a_cap_above_the_guard_changes_nothing(keys, ledger):
    """A ceiling can only reduce. It is never a permission to exceed."""
    priv, pub = keys
    r = req(100.0)
    d = evaluate(r, ctx_at(RTH), POL)
    receipt = ledger.append(to_receipt(d, r))
    auth = issue(d, r, receipt, priv, cap=1_000_000.0)
    verify(auth, pub)
    assert auth.permitted_notional == d.allowed_notional == 100.0
    assert auth.binding_constraint == d.binding_constraint


def test_a_zero_cap_authorizes_nothing(keys, ledger):
    priv, pub = keys
    r = req(100.0)
    d = evaluate(r, ctx_at(RTH), POL)
    receipt = ledger.append(to_receipt(d, r))
    auth = issue(d, r, receipt, priv, cap=0.0)
    with pytest.raises(AuthorizationError, match="permits nothing"):
        check_redeemable(auth, pub, ledger.path)
