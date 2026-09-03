"""Canonical instrument registry.

Source: Binance bStocks launch announcement, 11 June 2026. Issuer is BTech
Holdings Limited (Binance group affiliate); instruments are Certificates
representing Financial Instruments under para 92, Sch 1 FSMR, offered through
an Approved Prospectus in the ADGM. They are NOT direct share ownership.

The contract addresses below are the canonical BNB Smart Chain deployments and
are the sole authority for P6. The registry is hashed at load; a mismatch is a
BLOCK with no override path (Law 6, Law 7).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Instrument:
    token_symbol: str        # Binance Spot symbol, e.g. NVDABUSDT
    token_asset: str         # base asset, e.g. NVDAB
    underlying: str          # reference-market ticker, e.g. NVDA
    underlying_name: str
    issuer: str
    instrument_class: str
    network: str
    contract: str            # canonical BNB Smart Chain address
    listed_utc: str


_ISSUER = "BTech Holdings Limited (Binance group affiliate)"
_CLASS = (
    "Certificate representing a Financial Instrument "
    "(para 92, Sch 1 FSMR) - NOT direct share ownership"
)
_NETWORK = "BNB Smart Chain"

REGISTRY: dict[str, Instrument] = {
    i.token_symbol: i
    for i in (
        Instrument("MUBUSDT", "MUB", "MU", "Micron Technology Inc", _ISSUER,
                   _CLASS, _NETWORK,
                   "0xcdf2f3e0fa43C47A6662a91C9E4a7C5f69762699",
                   "2026-06-11T17:00:00Z"),
        Instrument("CRCLBUSDT", "CRCLB", "CRCL", "Circle Internet Group Inc",
                   _ISSUER, _CLASS, _NETWORK,
                   "0x80f3D493EBCe97e343c53D29a137942416B4ffC0",
                   "2026-06-11T18:00:00Z"),
        Instrument("NVDABUSDT", "NVDAB", "NVDA", "NVIDIA Corp", _ISSUER,
                   _CLASS, _NETWORK,
                   "0x02Fca66C1D1aFB4E2A7884261eB00F63598a7436",
                   "2026-06-11T18:00:00Z"),
        Instrument("SNDKBUSDT", "SNDKB", "SNDK", "SanDisk Corp", _ISSUER,
                   _CLASS, _NETWORK,
                   "0x3eE4dF61bd4F867E349BEaE8bFE07bc31b4850fb",
                   "2026-06-11T18:00:00Z"),
        Instrument("TSLABUSDT", "TSLAB", "TSLA", "Tesla Inc", _ISSUER,
                   _CLASS, _NETWORK,
                   "0x5b1910eAaD6450E50f816082Aa078C41F10C292f",
                   "2026-06-11T18:00:00Z"),
    )
}

TOKEN_SYMBOLS = sorted(REGISTRY)
UNDERLYINGS = sorted({i.underlying for i in REGISTRY.values()})


def registry_sha256() -> str:
    """Checksum of the canonical registry, recorded in every receipt."""
    blob = json.dumps(
        [asdict(REGISTRY[s]) for s in TOKEN_SYMBOLS],
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def by_underlying(ticker: str) -> Instrument | None:
    for inst in REGISTRY.values():
        if inst.underlying == ticker.upper():
            return inst
    return None
