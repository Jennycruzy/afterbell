"""Posture tests.

The service notices things nobody asked about. Two properties matter: it only
speaks when a band the policy actually sizes on has moved, and what it writes
authorises nothing.
"""
from __future__ import annotations

from afterbell.posture import (
    Posture, change_record, explain, observe, transitions,
)

from tests.test_guard import POL


def state(**kw):
    base = {
        "symbol": "NVDABUSDT",
        "status": "PASS",
        "market_state": "RTH_OPEN",
        "reference_age_s": 2.0,
        "measurements": {"spread_ratio": 0.8, "liquidity_ratio": 1.1,
                         "band": "NOMINAL", "exchange_status": "trading",
                         "exposure_check": "VERIFIED"},
    }
    m = base["measurements"] | kw.pop("measurements", {})
    return base | kw | {"measurements": m}


def test_a_quiet_open_market_reads_as_every_band_healthy():
    p = observe(state(), POL)
    assert p.market_state == "RTH_OPEN"
    assert p.reference == "fresh"
    assert p.liquidity == "normal"
    assert p.account_evidence == "current"
    assert p.verdict == "PASS"


def test_the_first_observation_reports_no_change():
    """Nothing to compare against is not the same as something changing."""
    assert transitions(None, observe(state(), POL)) == []


def test_an_unchanged_market_produces_nothing():
    before = observe(state(), POL)
    after = observe(state(reference_age_s=9.0), POL)   # still fresh
    assert transitions(before, after) == []


def test_the_closing_bell_is_noticed():
    before = observe(state(), POL)
    after = observe(state(market_state="CLOSED_WEEKEND", status="REDUCE"), POL)
    moved = dict((f, (w, n)) for f, w, n in transitions(before, after))
    assert moved["market_state"] == ("RTH_OPEN", "CLOSED_WEEKEND")
    assert moved["verdict"] == ("PASS", "REDUCE")


def test_the_reference_ageing_past_a_sizing_boundary_is_noticed():
    """The bands are the backward-gap ladder, so a move is a move in size."""
    before = observe(state(reference_age_s=3_600), POL)
    after = observe(state(reference_age_s=100_000), POL)   # past 24h
    assert before.reference == "fresh"
    assert [f for f, _, _ in transitions(before, after)] == ["reference"]


def test_a_book_leaving_its_normal_tier_is_noticed():
    before = observe(state(), POL)
    after = observe(state(measurements={"spread_ratio": 2.5,
                                        "liquidity_ratio": 0.5}), POL)
    assert before.liquidity == "normal"
    assert after.liquidity == "thin"


def test_losing_account_evidence_is_noticed():
    before = observe(state(), POL)
    after = observe(state(
        measurements={"exposure_check": "required account report missing"}), POL)
    assert after.account_evidence == "missing"
    assert ("account_evidence", "current", "missing") in transitions(before, after)


def test_the_explanation_is_plain_and_says_nothing_was_authorised():
    before = observe(state(), POL)
    after = observe(state(market_state="CLOSED_WEEKEND"), POL)
    text = explain("NVDABUSDT", transitions(before, after))

    assert "Reference market: RTH_OPEN -> CLOSED_WEEKEND" in text
    assert "No order was created" in text
    assert "no authorization was issued" in text


def test_a_quiet_cycle_explains_itself_as_quiet():
    assert explain("NVDABUSDT", []) == "NVDABUSDT: nothing material changed."


def test_the_record_authorises_nothing_and_is_not_a_decision():
    """An observation must never be readable as permission or as a decision."""
    before = observe(state(), POL)
    after = observe(state(market_state="CLOSED_WEEKEND"), POL)
    rec = change_record(before, after, transitions(before, after),
                        ts="2026-09-08T20:00:00Z", receipt_seq=10,
                        receipt_hash="abc")

    assert rec["kind"] == "posture_change"
    assert rec["authorizes"] is None
    assert "decision" not in rec          # the evaluation cohort skips it
    assert "permitted_notional" not in rec
    assert "allowed_notional" not in rec
    assert "signature" not in rec


def test_a_posture_survives_a_round_trip_through_disk():
    """The service reloads the last bands after a restart."""
    p = observe(state(), POL)
    assert Posture(**p.to_dict()) == p


def test_the_symbol_is_carried_from_the_published_state():
    """A posture that cannot name its symbol is not worth recording."""
    assert observe(state(), POL).symbol == "NVDABUSDT"


def test_a_change_of_case_in_venue_status_is_not_a_change_of_state():
    before = observe(state(measurements={"exchange_status": "TRADING"}), POL)
    after = observe(state(measurements={"exchange_status": "trading"}), POL)
    assert transitions(before, after) == []
