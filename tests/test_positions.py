"""Signed account-position snapshot tests."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from afterbell.positions import (
    PositionSnapshot, PositionSnapshotError, parse, sign_snapshot,
    verify_snapshot,
)


def snapshot(at=None):
    at = at or datetime.now(timezone.utc)
    return PositionSnapshot(
        as_of=at.isoformat(), positions={"nvdabusdt": 20.0, "TSLABUSDT": -3.0},
        source="codex-supported-client")


def test_snapshot_is_signed_and_round_trips():
    key = Ed25519PrivateKey.generate()
    at = datetime.now(timezone.utc) - timedelta(seconds=10)
    signed = sign_snapshot(snapshot(at), key)
    parsed = parse(json.loads(signed.to_json()))
    age = verify_snapshot(parsed, key.public_key(), now=at + timedelta(seconds=10),
                          max_age_s=120)
    assert age == pytest.approx(10.0)
    assert parsed.positions == {"NVDABUSDT": 20.0, "TSLABUSDT": -3.0}
    assert parsed.gross_exposure_usdt == pytest.approx(23.0)
    assert len(parsed.digest) == 64


def test_tampering_is_refused():
    key = Ed25519PrivateKey.generate()
    signed = sign_snapshot(snapshot(datetime.now(timezone.utc) - timedelta(seconds=1)),
                           key)
    forged = PositionSnapshot(
        as_of=signed.as_of, positions={"NVDABUSDT": 9_999.0},
        source=signed.source, signature=signed.signature)
    with pytest.raises(PositionSnapshotError, match="does not match"):
        verify_snapshot(forged, key.public_key())


def test_stale_snapshot_is_refused():
    key = Ed25519PrivateKey.generate()
    at = datetime.now(timezone.utc) - timedelta(seconds=121)
    signed = sign_snapshot(snapshot(at), key)
    with pytest.raises(PositionSnapshotError, match="beyond"):
        verify_snapshot(signed, key.public_key(), now=datetime.now(timezone.utc),
                        max_age_s=120)


def test_unsigned_and_unknown_fields_are_refused():
    with pytest.raises(PositionSnapshotError, match="not Ed25519-signed"):
        verify_snapshot(snapshot(), Ed25519PrivateKey.generate().public_key())
    with pytest.raises(PositionSnapshotError, match="unknown"):
        parse(snapshot().to_dict() | {"override": 1})
