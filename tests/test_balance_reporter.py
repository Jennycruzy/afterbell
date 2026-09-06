"""Tests for the narrow Binance account-export position publisher."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from afterbell.balance_reporter import (
    BalanceReporterError, build_snapshot, parse_account_export,
)
from afterbell.instruments import TOKEN_SYMBOLS
from afterbell.positions import verify_snapshot

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


def export(*balances, captured_at=NOW):
    return json.dumps({
        "tool": "spot.getAccount", "captured_at": captured_at.isoformat(),
        "result": {"canTrade": True, "balances": list(balances)},
    }).encode()


def test_values_free_locked_and_includes_every_symbol():
    key = Ed25519PrivateKey.generate()
    raw = export({"asset": "NVDAB", "free": "2", "locked": "0.5"},
                 {"asset": "USDT", "free": "100", "locked": "0"})
    snapshot = build_snapshot(raw, {symbol: 10 for symbol in TOKEN_SYMBOLS},
                              key, now=NOW)
    assert set(snapshot.positions) == set(TOKEN_SYMBOLS)
    assert snapshot.positions["NVDABUSDT"] == 25
    assert snapshot.gross_exposure_usdt == 25
    assert snapshot.source.startswith("binance-agent-os/spot.getAccount;sha256=")
    verify_snapshot(snapshot, key.public_key(), now=NOW, max_age_s=120)


def test_rejects_stale_wrong_tool_duplicate_and_negative_data():
    with pytest.raises(BalanceReporterError, match="outside"):
        parse_account_export(export(captured_at=NOW - timedelta(seconds=121)), now=NOW)
    wrong = json.dumps({"tool": "wallet.getBalance", "captured_at": NOW.isoformat(),
                        "result": {"balances": []}}).encode()
    with pytest.raises(BalanceReporterError, match="spot.getAccount"):
        parse_account_export(wrong, now=NOW)
    duplicate = export({"asset": "NVDAB", "free": "0", "locked": "0"},
                       {"asset": "nvdab", "free": "0", "locked": "0"})
    with pytest.raises(BalanceReporterError, match="repeats"):
        parse_account_export(duplicate, now=NOW)
    negative = export({"asset": "NVDAB", "free": "-1", "locked": "0"})
    with pytest.raises(BalanceReporterError, match="non-negative"):
        parse_account_export(negative, now=NOW)


def test_evidence_change_changes_signed_source():
    key = Ed25519PrivateKey.generate()
    prices = {symbol: 1 for symbol in TOKEN_SYMBOLS}
    first = build_snapshot(export(), prices, key, now=NOW)
    second = build_snapshot(
        export({"asset": "USDT", "free": "0", "locked": "0"}),
        prices, key, now=NOW)
    assert first.source != second.source
    assert first.signature != second.signature


def test_missing_price_fails_closed():
    with pytest.raises(BalanceReporterError, match="must be numeric"):
        build_snapshot(export(), {}, Ed25519PrivateKey.generate(), now=NOW)
