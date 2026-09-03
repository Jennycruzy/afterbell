"""Unauthenticated Binance checks used by P4 and P6.

The published Binance skills are wrappers around public endpoints. Keeping the
HTTP calls here makes the live path auditable and lets the guard record the
actual distinction between a supported audit, an unsafe audit and an audit
service that does not cover bStocks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx

from afterbell.instruments import Instrument

RWA_STATUS = (
    "https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/"
    "market/token/rwa/asset/market/status/ai"
)
TOKEN_AUDIT = (
    "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/security/"
    "token/audit"
)


class PublicCheckUnavailable(RuntimeError):
    """A public check could not be completed; callers must not assume pass."""


@dataclass(frozen=True)
class RWAStatus:
    open_state: bool
    reason_code: str
    reason_message: str | None
    market_status: str | None


@dataclass(frozen=True)
class TokenAudit:
    status: str
    supported: bool
    has_result: bool
    risk_level: str | int | None
    risk_items: tuple[Any, ...]

    @property
    def safe(self) -> bool | None:
        """Return a verdict only when Binance returned a usable audit result."""
        if not self.supported or not self.has_result:
            return None
        if isinstance(self.risk_level, int):
            return self.risk_level < 4
        if isinstance(self.risk_level, str):
            return self.risk_level.upper() not in {
                "HIGH", "DANGER", "CRITICAL", "SEVERE",
            }
        return None


class PublicChecks:
    """Small, credential-free client for the two Binance skill endpoints."""

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    @staticmethod
    def _payload(response: httpx.Response) -> dict[str, Any]:
        if "restricted location" in response.text.lower():
            raise PublicCheckUnavailable("Binance public endpoint reported a restricted location")
        if response.status_code != 200:
            raise PublicCheckUnavailable(
                f"HTTP {response.status_code}: {response.text[:300]}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise PublicCheckUnavailable(f"invalid JSON: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise PublicCheckUnavailable(
                f"Binance endpoint did not return success: {str(payload)[:300]}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise PublicCheckUnavailable("Binance endpoint returned no data object")
        return data

    def rwa_status(self, instrument: Instrument) -> RWAStatus:
        try:
            response = self.client.get(
                RWA_STATUS,
                params={"chainId": "56", "contractAddress": instrument.contract},
            )
        except Exception as exc:
            raise PublicCheckUnavailable(
                f"status request failed: {type(exc).__name__}: {exc}") from exc
        data = self._payload(response)

        open_state = data.get("openState")
        reason_code = data.get("reasonCode")
        if not isinstance(open_state, bool) or not isinstance(reason_code, str):
            raise PublicCheckUnavailable(
                "status response omitted required openState/reasonCode fields")
        reason_message = data.get("reasonMsg")
        if reason_message is not None and not isinstance(reason_message, str):
            raise PublicCheckUnavailable("status response reasonMsg is not text")
        market_status = data.get("marketStatus")
        if market_status is not None and not isinstance(market_status, str):
            raise PublicCheckUnavailable("status response marketStatus is not text")
        return RWAStatus(open_state, reason_code, reason_message, market_status)

    def token_audit(self, contract: str) -> TokenAudit:
        try:
            response = self.client.post(
                TOKEN_AUDIT,
                json={
                    "binanceChainId": "56",
                    "contractAddress": contract,
                    "requestId": str(uuid4()),
                },
            )
        except Exception as exc:
            raise PublicCheckUnavailable(
                f"audit request failed: {type(exc).__name__}: {exc}") from exc
        data = self._payload(response)

        supported = data.get("isSupported")
        has_result = data.get("hasResult")
        if not isinstance(supported, bool) or not isinstance(has_result, bool):
            raise PublicCheckUnavailable(
                "audit response omitted required isSupported/hasResult fields")
        risk_level = data.get("riskLevelEnum")
        if risk_level is None:
            risk_level = data.get("riskLevel")
        if risk_level is not None and not isinstance(risk_level, (str, int)):
            raise PublicCheckUnavailable("audit response risk level is malformed")
        items = data.get("riskItems")
        if not isinstance(items, list):
            raise PublicCheckUnavailable("audit response riskItems is malformed")
        if not supported or not has_result:
            status = "UNSUPPORTED" if not supported else "PENDING"
        elif self._risk_is_high(risk_level):
            status = "UNSAFE"
        else:
            status = "SAFE"
        return TokenAudit(status, supported, has_result, risk_level,
                          tuple(items))

    @staticmethod
    def _risk_is_high(level: str | int | None) -> bool:
        if isinstance(level, int):
            return level >= 4
        return isinstance(level, str) and level.upper() in {
            "HIGH", "DANGER", "CRITICAL", "SEVERE",
        }
