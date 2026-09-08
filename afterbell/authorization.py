"""Authorizations: what the guard emits instead of an order.

Binance rejects a standalone PKCE client as an unsupported agent, so there is
no path where this package holds a bearer token. That constraint produced the
better architecture rather than a workaround:

    The guard does not place orders. It issues authorizations. A supported MCP
    client places exactly what it was authorized to place, and nothing else.

An authorization is a short-lived signed statement of a decision the guard has
already made and already receipted. It carries no instruction, no strategy and
no discretion. Five properties make it safe to hand to a client this package
does not control, and each one is a test:

  short-lived  a 120s TTL, because market state changes and an authorization
               must not outlive the conditions that produced it
  signed       Ed25519, private key held only by the guard process. The
               transcriber verifies with a public key and therefore cannot
               forge one, which an HMAC would not give us
  single-use   the nonce is atomically reserved in the ledger before the
               supported client is handed order arguments; a replay is refused
  monotone     the transcriber may place less than `permitted_notional` and
               never more. The check is in code, not in a prompt
  chained      it names the receipt sequence and hash of the decision it came
               from, so an authorization with no matching decision is an
               authorization this system did not issue

Law 7 still holds here. An authorization for zero is the representation of
BLOCK; there is no value of any field that turns it into a larger order than
the guard permitted.
"""
from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TTL_S = 120
SIGNATURE_PREFIX = "ed25519:"

# The signed body. `signature` is not part of it, and neither is anything a
# caller could add later: an unknown field makes verification fail rather than
# being ignored, so a field cannot be smuggled past the signature.
SIGNED_FIELDS = (
    "nonce", "issued_at", "expires_at", "symbol", "side",
    "requested_notional", "permitted_notional", "binding_constraint",
    "market_state", "reference_age_s", "policy_sha256", "receipt_seq",
    "receipt_hash",
)


class AuthorizationError(RuntimeError):
    """Raised loudly. A refused authorization is never downgraded to a warning."""


@dataclass(frozen=True)
class Authorization:
    nonce: str
    issued_at: str
    expires_at: str
    symbol: str
    side: str
    requested_notional: float
    permitted_notional: float
    binding_constraint: str
    market_state: str
    reference_age_s: float | None
    policy_sha256: str
    receipt_seq: int
    receipt_hash: str
    signature: str = ""

    def signing_bytes(self) -> bytes:
        """Canonical bytes over which the signature is computed.

        Sorted keys and no whitespace, so two encoders of the same
        authorization produce the same bytes and a re-serialised artifact still
        verifies.
        """
        body = {k: getattr(self, k) for k in SIGNED_FIELDS}
        return json.dumps(body, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)

    @property
    def expires_at_dt(self) -> datetime:
        return datetime.fromisoformat(self.expires_at)

    def seconds_remaining(self, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        return (self.expires_at_dt - now).total_seconds()

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.seconds_remaining(now) <= 0.0


# --------------------------------------------------------------------------
# Keys. The private key never leaves the guard process; the public key is
# published, because a verifier that needs a secret is a verifier that can
# forge.
# --------------------------------------------------------------------------

def generate_keypair(private_path: str | Path,
                     public_path: str | Path) -> Ed25519PublicKey:
    """Write a new keypair. The private file is created mode 600."""
    private_path, public_path = Path(private_path), Path(public_path)
    key = Ed25519PrivateKey.generate()
    private_path.parent.mkdir(parents=True, exist_ok=True)
    raw = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption())
    # Create with the right mode rather than widening then narrowing it.
    fd = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(raw)
    pub = key.public_key()
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_bytes(pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo))
    return pub


def load_private_key(path: str | Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(Path(path).read_bytes(),
                                             password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise AuthorizationError(f"{path} is not an Ed25519 private key")
    return key


def load_public_key(path: str | Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(Path(path).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise AuthorizationError(f"{path} is not an Ed25519 public key")
    return key


# --------------------------------------------------------------------------
# Issue and verify
# --------------------------------------------------------------------------

def issue(decision: Any, request: Any, receipt: dict[str, Any],
          key: Ed25519PrivateKey, *, ttl_s: int = DEFAULT_TTL_S,
          cap: float | None = None, cap_name: str = "executor.max_order_usdt",
          now: datetime | None = None) -> Authorization:
    """Sign an authorization for a decision the guard has already receipted.

    `receipt` must be the ledger record for exactly this decision. Nothing here
    recomputes a size: `permitted_notional` is the guard's own number, narrowed
    by `cap` if one is given. There is no arithmetic here that can disagree
    with the guard, and none that can exceed it.

    `cap` is the policy's hand-chosen execution ceiling. It belongs at issuance
    rather than in the transcriber, so that the transcriber keeps no thresholds
    at all and the signed artifact is the whole of the permission.
    """
    now = now or datetime.now(timezone.utc)
    if ttl_s <= 0:
        raise AuthorizationError("ttl must be positive")
    policy_status = getattr(decision, "policy_status", None)
    if policy_status != "CALIBRATED":
        raise AuthorizationError(
            f"policy status is {policy_status}; authorization issuance requires "
            "a CALIBRATED policy")
    if decision.allowed_notional > decision.requested_notional:
        # Unreachable through guard.evaluate, which takes a min() against the
        # request. Asserted anyway: this is the last place it could be caught.
        raise AuthorizationError(
            "permitted notional exceeds requested; refusing to sign")

    permitted = float(decision.allowed_notional)
    binding = decision.binding_constraint
    if cap is not None:
        if cap < 0:
            raise AuthorizationError("cap must not be negative")
        if cap < permitted:
            permitted, binding = float(cap), cap_name

    auth = Authorization(
        nonce=secrets.token_hex(16),
        issued_at=now.isoformat(timespec="seconds"),
        expires_at=(now + timedelta(seconds=ttl_s)).isoformat(timespec="seconds"),
        symbol=request.symbol,
        side=request.side.value if hasattr(request.side, "value") else str(request.side),
        requested_notional=float(decision.requested_notional),
        permitted_notional=permitted,
        binding_constraint=binding,
        market_state=decision.context.clock.state.value,
        reference_age_s=decision.context.reference_age_s,
        policy_sha256=decision.policy_sha256,
        receipt_seq=int(receipt["seq"]),
        receipt_hash=str(receipt["hash"]),
    )
    sig = key.sign(auth.signing_bytes())
    return Authorization(**(auth.to_dict() | {
        "signature": SIGNATURE_PREFIX + sig.hex()}))


def parse(data: str | bytes | dict[str, Any]) -> Authorization:
    """Parse without verifying. Every caller must then call `verify`."""
    if isinstance(data, (str, bytes)):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise AuthorizationError("authorization must be a JSON object")
    known = set(SIGNED_FIELDS) | {"signature"}
    unknown = sorted(set(data) - known)
    if unknown:
        # An ignored field is a field outside the signature. Refuse instead.
        raise AuthorizationError(f"unknown authorization fields: {unknown}")
    missing = sorted(known - set(data))
    if missing:
        raise AuthorizationError(f"authorization missing fields: {missing}")
    return Authorization(**data)


def verify(auth: Authorization, pub: Ed25519PublicKey, *,
           now: datetime | None = None, check_expiry: bool = True) -> None:
    """Raise unless the artifact is authentic, unexpired and well formed.

    Order matters only for the error message; every condition is checked.
    """
    if not auth.signature.startswith(SIGNATURE_PREFIX):
        raise AuthorizationError("authorization is not Ed25519-signed")
    try:
        raw = bytes.fromhex(auth.signature[len(SIGNATURE_PREFIX):])
    except ValueError as exc:
        raise AuthorizationError(f"malformed signature: {exc}") from exc
    try:
        pub.verify(raw, auth.signing_bytes())
    except InvalidSignature as exc:
        raise AuthorizationError(
            "signature does not match the authorization body; it was altered "
            "or signed by another key") from exc
    if auth.permitted_notional < 0:
        raise AuthorizationError("permitted notional is negative")
    if auth.permitted_notional > auth.requested_notional:
        raise AuthorizationError(
            "permitted notional exceeds requested notional")
    if check_expiry and auth.is_expired(now):
        raise AuthorizationError(
            f"authorization expired at {auth.expires_at}; market state may "
            "have changed since it was issued")


# --------------------------------------------------------------------------
# Redemption. Single-use is enforced against the ledger, because the ledger is
# the only record here that survives a restart and cannot be rewritten.
# --------------------------------------------------------------------------

RESERVATION_KIND = "authorization_reserved"
REDEMPTION_KIND = "authorization_redeemed"
NONCE_CONSUMING_KINDS = {RESERVATION_KIND, REDEMPTION_KIND}


def nonce_consumed(ledger_path: str | Path, nonce: str) -> bool:
    """True when a nonce was reserved or redeemed in the durable ledger."""
    path = Path(ledger_path)
    if not path.exists():
        return False
    needle = f'"{nonce}"'
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            # Cheap prefilter, then an exact check: the nonce must be this
            # record's redeemed nonce, not an arbitrary string match.
            if needle not in line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (rec.get("kind") in NONCE_CONSUMING_KINDS
                    and rec.get("nonce") == nonce):
                return True
    return False


def nonce_reserved(ledger_path: str | Path, nonce: str) -> bool:
    """True only after the one-time supported-client handoff was recorded."""
    path = Path(ledger_path)
    if not path.exists():
        return False
    from afterbell.ledger import Ledger
    for rec in Ledger(path):
        if rec.get("kind") == RESERVATION_KIND and rec.get("nonce") == nonce:
            return True
    return False


def nonce_finalized(ledger_path: str | Path, nonce: str) -> bool:
    """True when a reserved authorization already has its child receipt."""
    path = Path(ledger_path)
    if not path.exists():
        return False
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("kind") == REDEMPTION_KIND and rec.get("nonce") == nonce:
                return True
    return False


# Compatibility name for callers that only need the conservative answer. A
# reservation has the same replay effect as a completed redemption.
nonce_redeemed = nonce_consumed


def reservation_record(auth: Authorization) -> dict[str, Any]:
    """The durable, one-time handoff from guard to supported MCP client."""
    return {
        "kind": RESERVATION_KIND, "nonce": auth.nonce,
        "authorizes_receipt_seq": auth.receipt_seq,
        "authorizes_receipt_hash": auth.receipt_hash,
        "symbol": auth.symbol, "side": auth.side,
        "requested_notional": auth.requested_notional,
        "permitted_notional": auth.permitted_notional,
        "binding_constraint": auth.binding_constraint,
        "market_state": auth.market_state,
        "policy_sha256": auth.policy_sha256,
    }


def reserve(auth: Authorization, pub: Ed25519PublicKey,
            ledger_path: str | Path, *, now: datetime | None = None) -> dict[str, Any]:
    """Verify and consume an authorization before a client can place it.

    A failed venue call consumes this nonce too. Retrying requires a fresh
    authorization; that is preferable to two clients placing one artifact.
    """
    verify(auth, pub, now=now)
    if auth.permitted_notional <= 0:
        raise AuthorizationError(
            f"authorization permits nothing ({auth.binding_constraint}); "
            "there is no order to place")
    from afterbell.ledger import Ledger
    try:
        return Ledger(ledger_path).append_once(
            reservation_record(auth), field="nonce", value=auth.nonce,
            kinds=NONCE_CONSUMING_KINDS)
    except RuntimeError as exc:
        raise AuthorizationError(
            f"authorization {auth.nonce} was already reserved or redeemed; "
            "replay refused") from exc


def redemption_record(auth: Authorization, *, placed_notional: float,
                      order_id: str | None, venue_response: dict[str, Any] | None,
                      placed_by: str) -> dict[str, Any]:
    """The child record written back into the ledger after placement.

    It carries requested, permitted and placed side by side. A judge asking
    "could the agent have placed more" reads three numbers and a signature
    check, not an assurance.
    """
    if placed_notional > auth.permitted_notional:
        raise AuthorizationError(
            f"placed {placed_notional} exceeds permitted "
            f"{auth.permitted_notional}; refusing to record")
    return {
        "kind": REDEMPTION_KIND,
        "nonce": auth.nonce,
        "authorizes_receipt_seq": auth.receipt_seq,
        "authorizes_receipt_hash": auth.receipt_hash,
        "symbol": auth.symbol,
        "side": auth.side,
        "requested_notional": auth.requested_notional,
        "permitted_notional": auth.permitted_notional,
        "placed_notional": placed_notional,
        "binding_constraint": auth.binding_constraint,
        "market_state": auth.market_state,
        "policy_sha256": auth.policy_sha256,
        "order_id": order_id,
        "placed_by": placed_by,
        "venue_response": venue_response,
    }


def check_redeemable(auth: Authorization, pub: Ed25519PublicKey,
                     ledger_path: str | Path, *,
                     now: datetime | None = None) -> None:
    """Every condition that must hold before an order is placed.

    Signature, TTL, monotonicity and replay, in one call, so a caller cannot
    accidentally check three of the four.
    """
    verify(auth, pub, now=now)
    if nonce_consumed(ledger_path, auth.nonce):
        raise AuthorizationError(
            f"authorization {auth.nonce} was already redeemed; replay refused")
    if auth.permitted_notional <= 0:
        raise AuthorizationError(
            f"authorization permits nothing ({auth.binding_constraint}); "
            "there is no order to place")
