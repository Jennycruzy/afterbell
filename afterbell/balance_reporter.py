"""Produce signed P7 snapshots from fresh Binance Agent OS account exports."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from afterbell.instruments import REGISTRY, TOKEN_SYMBOLS
from afterbell.positions import PositionSnapshot, sign_snapshot


class BalanceReporterError(ValueError):
    """Account evidence, prices, or key could not be trusted."""


def _utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise BalanceReporterError("captured_at must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise BalanceReporterError(f"captured_at is invalid: {exc}") from exc
    if parsed.tzinfo is None:
        raise BalanceReporterError("captured_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def _number(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise BalanceReporterError(f"{label} must be numeric") from exc
    if not math.isfinite(number) or number < 0:
        raise BalanceReporterError(f"{label} must be finite and non-negative")
    return number


def parse_account_export(raw: bytes, *, now: datetime | None = None,
                         max_age_s: float = 120.0) -> tuple[dict[str, float], str, str]:
    """Validate MCP evidence and return bStock quantities, time, and digest."""
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BalanceReporterError(f"account export is not valid JSON: {exc}") from exc
    if not isinstance(envelope, Mapping):
        raise BalanceReporterError("account export must be an object")
    if envelope.get("tool") != "spot.getAccount":
        raise BalanceReporterError("account export tool must be spot.getAccount")
    captured = _utc(envelope.get("captured_at"))
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age = (current - captured).total_seconds()
    if age < -5 or age > max_age_s:
        raise BalanceReporterError(
            f"account export age {age:.1f}s is outside the {max_age_s:.1f}s limit")
    account = envelope.get("result")
    if not isinstance(account, Mapping):
        raise BalanceReporterError("account export result must be an object")
    balances = account.get("balances")
    if not isinstance(balances, list):
        raise BalanceReporterError("account result balances must be a list")

    wanted = {instrument.token_asset: symbol
              for symbol, instrument in REGISTRY.items()}
    quantities = {symbol: 0.0 for symbol in TOKEN_SYMBOLS}
    seen: set[str] = set()
    for index, item in enumerate(balances):
        if not isinstance(item, Mapping):
            raise BalanceReporterError(f"balance {index} must be an object")
        asset = str(item.get("asset", "")).strip().upper()
        if not asset:
            raise BalanceReporterError(f"balance {index} has no asset")
        if asset in seen:
            raise BalanceReporterError(f"account result repeats asset {asset}")
        seen.add(asset)
        if asset in wanted:
            quantities[wanted[asset]] = (
                _number(item.get("free"), f"{asset}.free")
                + _number(item.get("locked"), f"{asset}.locked"))

    canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                           allow_nan=False).encode()
    return quantities, captured.isoformat(), hashlib.sha256(canonical).hexdigest()


def fetch_prices(symbols: list[str], *,
                 client: httpx.Client | None = None) -> dict[str, float]:
    """Fetch public Spot prices; missing or malformed quotes fail closed."""
    own_client = client is None
    client = client or httpx.Client(timeout=10.0)
    try:
        prices: dict[str, float] = {}
        for symbol in symbols:
            response = client.get("https://api.binance.com/api/v3/ticker/price",
                                  params={"symbol": symbol})
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, Mapping) or body.get("symbol") != symbol:
                raise BalanceReporterError(f"unexpected price response for {symbol}")
            price = _number(body.get("price"), f"{symbol}.price")
            if price == 0:
                raise BalanceReporterError(f"{symbol}.price must be positive")
            prices[symbol] = price
        return prices
    except (httpx.HTTPError, ValueError) as exc:
        if isinstance(exc, BalanceReporterError):
            raise
        raise BalanceReporterError(f"Binance public price request failed: {exc}") from exc
    finally:
        if own_client:
            client.close()


def build_snapshot(raw: bytes, prices: Mapping[str, Any], key: Ed25519PrivateKey,
                   *, now: datetime | None = None,
                   max_age_s: float = 120.0) -> PositionSnapshot:
    quantities, captured_at, evidence_digest = parse_account_export(
        raw, now=now, max_age_s=max_age_s)
    notionals = {
        symbol: quantities[symbol] * _number(prices.get(symbol), f"{symbol}.price")
        for symbol in TOKEN_SYMBOLS
    }
    return sign_snapshot(PositionSnapshot(
        as_of=captured_at,
        positions=notionals,
        source=f"binance-agent-os/spot.getAccount;sha256={evidence_digest}",
    ), key)


def load_private_key(path: Path) -> Ed25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (OSError, ValueError, TypeError) as exc:
        raise BalanceReporterError(f"private key could not be loaded: {exc}") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise BalanceReporterError("position reporter key is not Ed25519")
    return key


def write_snapshot(path: Path, snapshot: PositionSnapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        handle.write(snapshot.to_json() + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sign a fresh Binance Agent OS account export for P7")
    parser.add_argument("--account-export", required=True, type=Path)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-input-age", type=float, default=120.0)
    args = parser.parse_args()
    raw = args.account_export.read_bytes()
    snapshot = build_snapshot(
        raw, fetch_prices(TOKEN_SYMBOLS), load_private_key(args.private_key),
        max_age_s=args.max_input_age)
    write_snapshot(args.output, snapshot)
    print(f"wrote signed snapshot {snapshot.digest} to {args.output}")


if __name__ == "__main__":
    main()
