"""Signed account-position snapshots for the aggregate exposure gate.

AFTERBELL has no authenticated position feed.  A caller that has a supported
client's account view can hand the guard a short-lived, signed snapshot instead.
The snapshot contains signed USDT notionals (positive means net long and
negative means net short), not quantities or credentials.  The signature is a
separate trust boundary from the market-data checks: an unsigned or stale
account view is not an account view the guard can safely use.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

SIGNATURE_PREFIX = "ed25519:"
SIGNED_FIELDS = ("as_of", "positions", "source")


class PositionSnapshotError(ValueError):
    """Raised when an account-position snapshot cannot be trusted or used."""


def _as_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise PositionSnapshotError("position snapshot as_of must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise PositionSnapshotError(
            f"position snapshot as_of is not an ISO timestamp: {exc}") from exc
    if parsed.tzinfo is None:
        raise PositionSnapshotError("position snapshot as_of must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class PositionSnapshot:
    """A signed, point-in-time map of net position notionals.

    ``positions`` is normalized to uppercase symbols and copied at
    construction, so signing and verification never depend on a caller later
    mutating a dictionary.  Values are signed USDT notionals.  A snapshot may
    include symbols that are not in AFTERBELL's bStock registry: they still
    count toward the account-wide gross ceiling.
    """

    as_of: str
    positions: Mapping[str, float]
    source: str
    signature: str = ""

    def __post_init__(self) -> None:
        _as_utc(self.as_of)
        # Normalize symbols and reject values whose interpretation is not
        # stable.  The normalized map is copied so a signature cannot be
        # detached from the data later.
        normalized: dict[str, float] = {}
        if not isinstance(self.positions, Mapping):
            raise PositionSnapshotError("position snapshot positions must be an object")
        for raw_symbol, raw_value in self.positions.items():
            symbol = str(raw_symbol).strip().upper()
            if not symbol:
                raise PositionSnapshotError("position snapshot contains an empty symbol")
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise PositionSnapshotError(
                    f"position for {symbol} must be a number") from exc
            if not math.isfinite(value):
                raise PositionSnapshotError(
                    f"position for {symbol} must be finite")
            if symbol in normalized:
                raise PositionSnapshotError(
                    f"position snapshot repeats symbol {symbol}")
            normalized[symbol] = value
        if not isinstance(self.source, str) or not self.source.strip():
            raise PositionSnapshotError("position snapshot source is required")
        if not isinstance(self.signature, str):
            raise PositionSnapshotError(
                "position snapshot signature must be a string")
        if not math.isfinite(sum(abs(value) for value in normalized.values())):
            raise PositionSnapshotError(
                "position snapshot gross exposure must be finite")
        object.__setattr__(self, "positions", normalized)

    @property
    def as_of_dt(self) -> datetime:
        return _as_utc(self.as_of)

    @property
    def gross_exposure_usdt(self) -> float:
        """The account-wide gross exposure represented by this snapshot."""
        return sum(abs(value) for value in self.positions.values())

    def signing_bytes(self) -> bytes:
        """Canonical bytes covered by the Ed25519 signature."""
        body = {field: getattr(self, field) for field in SIGNED_FIELDS}
        return json.dumps(body, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode()

    @property
    def digest(self) -> str:
        """Stable identifier for receipts without recording raw positions."""
        return hashlib.sha256(self.signing_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "positions": dict(self.positions),
            "source": self.source,
            "signature": self.signature,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2,
                          allow_nan=False)


def sign_snapshot(snapshot: PositionSnapshot,
                  key: Ed25519PrivateKey) -> PositionSnapshot:
    """Sign a snapshot with the trusted supported-client input key."""
    unsigned = replace(snapshot, signature="")
    return replace(unsigned,
                   signature=SIGNATURE_PREFIX
                   + key.sign(unsigned.signing_bytes()).hex())


def load_public_key(path: str | Path) -> Ed25519PublicKey:
    """Load the public key trusted for supported-client position input."""
    try:
        key = serialization.load_pem_public_key(Path(path).read_bytes())
    except (OSError, ValueError, TypeError) as exc:
        raise PositionSnapshotError(
            f"position snapshot public key could not be loaded from {path}: {exc}") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise PositionSnapshotError(f"{path} is not an Ed25519 public key")
    return key


def verify_snapshot(snapshot: PositionSnapshot, public_key: Ed25519PublicKey,
                    *, now: datetime | None = None,
                    max_age_s: float | None = None) -> float:
    """Verify signature and freshness; return snapshot age in seconds."""
    if not snapshot.signature.startswith(SIGNATURE_PREFIX):
        raise PositionSnapshotError("position snapshot is not Ed25519-signed")
    try:
        raw = bytes.fromhex(snapshot.signature[len(SIGNATURE_PREFIX):])
    except ValueError as exc:
        raise PositionSnapshotError(
            f"position snapshot has a malformed signature: {exc}") from exc
    try:
        public_key.verify(raw, snapshot.signing_bytes())
    except InvalidSignature as exc:
        raise PositionSnapshotError(
            "position snapshot signature does not match its contents") from exc

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age_s = (now - snapshot.as_of_dt).total_seconds()
    if age_s < -5.0:
        raise PositionSnapshotError("position snapshot as_of is in the future")
    if max_age_s is not None:
        if not math.isfinite(max_age_s) or max_age_s <= 0:
            raise PositionSnapshotError("position snapshot max age must be positive")
        if age_s > max_age_s:
            raise PositionSnapshotError(
                f"position snapshot is {age_s:.1f}s old, beyond the "
                f"{max_age_s:.1f}s freshness limit")
    return max(0.0, age_s)


def parse(data: str | bytes | Mapping[str, Any]) -> PositionSnapshot:
    """Parse a strict snapshot artifact; unknown fields are refused."""
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise PositionSnapshotError(f"invalid position snapshot JSON: {exc}") from exc
    if not isinstance(data, Mapping):
        raise PositionSnapshotError("position snapshot must be a JSON object")
    known = set(SIGNED_FIELDS) | {"signature"}
    unknown = sorted(set(data) - known)
    if unknown:
        raise PositionSnapshotError(f"unknown position snapshot fields: {unknown}")
    missing = sorted(known - set(data))
    if missing:
        raise PositionSnapshotError(f"position snapshot missing fields: {missing}")
    return PositionSnapshot(
        as_of=data["as_of"], positions=data["positions"],
        source=data["source"], signature=data["signature"])
