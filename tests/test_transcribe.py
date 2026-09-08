"""Transcriber tests.

The transcriber is the seam between a decision this package signed and an
order a client it does not control actually placed. What it writes back is
the only record of what the venue really did, so the number it records has to
come from the venue rather than from the authorization.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from afterbell.authorization import AuthorizationError, redemption_record

from tests.test_authorization import authorize, keys, ledger  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent


def _module():
    spec = importlib.util.spec_from_file_location(
        "transcribe", ROOT / "scripts" / "transcribe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tr = _module()

FILL = {"orderId": 54422149, "status": "FILLED", "executedQty": "0.02100000",
        "origQuoteOrderQty": "5.00000000", "cummulativeQuoteQty": "4.86192000"}


def test_the_amount_recorded_is_the_amount_the_venue_says_it_spent():
    assert tr.placed_notional(FILL) == pytest.approx(4.86192)


def test_the_correct_spelling_is_accepted_too():
    assert tr.placed_notional({"cumulativeQuoteQty": "12.5"}) == 12.5


def test_a_response_without_a_spent_amount_is_refused():
    """Law 3: a missing measurement halts rather than becoming a default.

    Recording the permitted amount here would make the requested/permitted/
    placed comparison vacuous and would stop the placed-exceeds-permitted
    check from ever firing.
    """
    with pytest.raises(AuthorizationError, match="cannot be measured"):
        tr.placed_notional({"orderId": 1, "executedQty": "0.021"})


def test_an_unreadable_spent_amount_is_refused():
    with pytest.raises(AuthorizationError, match="unreadable"):
        tr.placed_notional({"cummulativeQuoteQty": "not-a-number"})


def test_a_partial_fill_is_recorded_below_the_permitted_amount(keys, ledger):
    """The real acceptance spent 4.86192 of a 5.00 permitted amount."""
    auth, _, _ = authorize(keys, ledger, notional=5.0)
    record = redemption_record(auth, placed_notional=tr.placed_notional(FILL),
                               order_id="54422149", venue_response=FILL,
                               placed_by="codex-binance-agent-os")

    assert record["permitted_notional"] == 5.0
    assert record["placed_notional"] == pytest.approx(4.86192)
    assert record["placed_notional"] < record["permitted_notional"]


def test_a_venue_that_spent_more_than_permitted_is_never_recorded(keys, ledger):
    """The guard that copying the permitted amount would have made unreachable."""
    auth, _, _ = authorize(keys, ledger, notional=5.0)
    overspent = dict(FILL, cummulativeQuoteQty="7.50000000")

    with pytest.raises(AuthorizationError, match="exceeds permitted"):
        redemption_record(auth, placed_notional=tr.placed_notional(overspent),
                          order_id="1", venue_response=overspent,
                          placed_by="codex-binance-agent-os")
