"""Opt-in integration checks against Binance's unauthenticated endpoints.

They are skipped in ordinary unit runs so a laptop without Binance network
access does not get a false green or a false red. CI/VPS verification enables
them explicitly with AFTERBELL_RUN_LIVE=1.
"""
import os

import httpx
import pytest

from afterbell.instruments import REGISTRY
from afterbell.public_checks import PublicChecks


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("AFTERBELL_RUN_LIVE") != "1",
                       reason="set AFTERBELL_RUN_LIVE=1 for live public checks"),
]


def test_binance_public_market_and_status_endpoints_are_live():
    with httpx.Client(timeout=20.0) as client:
        ping = client.get("https://api.binance.com/api/v3/ping")
        assert ping.status_code == 200, ping.text[:300]
        ticker = client.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": "NVDABUSDT"})
        assert ticker.status_code == 200, ticker.text[:300]
        price = ticker.json().get("price")
        assert isinstance(price, str) and float(price) > 0

        status = PublicChecks(client).rwa_status(REGISTRY["NVDABUSDT"])
        assert isinstance(status.reason_code, str) and status.reason_code
