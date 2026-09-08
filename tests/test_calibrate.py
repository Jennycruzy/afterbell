"""Calibration.

The point of these tests is that the pass refuses to publish a number it does
not have the samples for. A calibration that quietly fills gaps is worse than
none, because it looks measured.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from afterbell.calibrate import (
    LADDER_USDT, MIN_STATE_SAMPLES, PAIR_TOLERANCE_S, ReferenceIndex,
    propose_bands, render_table, run,
)
from afterbell.clock import MarketState


def U(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def book_record(symbol, ts, mid=225.0, half=0.01, qty=200.0, n=40):
    return {"kind": "token", "symbol": symbol,
            "ts": ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "bids": [[f"{mid - half - i * 0.5:.4f}", f"{qty}"] for i in range(n)],
            "asks": [[f"{mid + half + i * 0.5:.4f}", f"{qty}"] for i in range(n)],
            "depth_limit": 5000}


def write_dataset(tmp_path, day, n_books, state_ts, with_reference=True,
                  ref_price=225.0):
    d = tmp_path / day
    d.mkdir(parents=True)
    with open(d / "token.jsonl", "w") as fh:
        for i in range(n_books):
            fh.write(json.dumps(
                book_record("NVDABUSDT", state_ts + timedelta(seconds=60 * i))
            ) + "\n")
    if with_reference:
        with open(d / "reference.jsonl", "w") as fh:
            for i in range(n_books):
                ts = state_ts + timedelta(seconds=60 * i)
                fh.write(json.dumps({
                    "kind": "reference", "provider": "yahoo",
                    "ts": ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                    "derived": {"NVDA": {"price": ref_price,
                                         "ts": ts.isoformat(),
                                         "source": "regular_trade"}}}) + "\n")
    return tmp_path


# Wednesday 2 Sep 2026 15:00Z - inside a regular session.
RTH = U("2026-09-02T15:00:00")


def test_thin_sample_produces_no_band_proposal(tmp_path):
    """Ten observations is not a distribution."""
    raw = write_dataset(tmp_path, "2026-09-02", 10, RTH)
    assert propose_bands(run(raw)) == {}


def test_sufficient_sample_produces_measured_bands(tmp_path):
    raw = write_dataset(tmp_path, "2026-09-02", MIN_STATE_SAMPLES + 5, RTH)
    bands = propose_bands(run(raw))
    assert set(bands) == {"NOMINAL", "WATCH", "DEGRADED", "BROKEN"}
    assert bands["BROKEN"]["max_abs_bps"] is None
    # Monotonic, or the ladder in the guard would short-circuit wrongly.
    caps = [bands[k]["max_abs_bps"] for k in ("NOMINAL", "WATCH", "DEGRADED")]
    assert caps == sorted(caps)


def test_bands_are_never_proposed_from_off_hours_samples(tmp_path):
    """The trap this pass exists to avoid.

    Off-hours the reference is frozen while the token keeps trading, so the
    basis measures overnight drift in the underlying, not disagreement. Bands
    built from it would grade the weekend against a yardstick made of weekend.
    """
    overnight = U("2026-09-03T02:00:00")
    raw = write_dataset(tmp_path, "2026-09-03", MIN_STATE_SAMPLES + 5, overnight)
    cal = run(raw)
    assert cal.basis["CLOSED_OVERNIGHT"].n >= MIN_STATE_SAMPLES
    assert propose_bands(cal) == {}


def test_reference_further_away_than_a_cycle_is_not_paired(tmp_path):
    raw = write_dataset(tmp_path, "2026-09-02", 5, RTH, with_reference=False)
    with open(raw / "2026-09-02" / "reference.jsonl", "w") as fh:
        far = RTH + timedelta(seconds=PAIR_TOLERANCE_S + 30)
        fh.write(json.dumps({
            "kind": "reference", "provider": "yahoo",
            "ts": far.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "derived": {"NVDA": {"price": 225.0}}}) + "\n")
    idx = ReferenceIndex.build(raw)
    assert idx.at("NVDA", RTH) is None


def test_walk_curve_covers_every_ladder_size(tmp_path):
    raw = write_dataset(tmp_path, "2026-09-02", MIN_STATE_SAMPLES + 5, RTH)
    walk = run(raw).walk["RTH_OPEN"]
    assert set(walk) == set(LADDER_USDT)
    costs = [walk[s] for s in LADDER_USDT]
    assert all(c is not None for c in costs)
    # Bigger orders eat further into the book, never less far.
    assert costs == sorted(costs)


def test_table_states_uncalibrated_when_samples_are_short(tmp_path):
    raw = write_dataset(tmp_path, "2026-09-02", 10, RTH)
    table = render_table(run(raw), min_rth=300)
    assert "Data coverage: incomplete" in table
    assert "300-sample minimum" in table


def test_table_names_states_never_observed(tmp_path):
    raw = write_dataset(tmp_path, "2026-09-02", 10, RTH)
    table = render_table(run(raw))
    assert "Not yet observed" in table
    assert "Weekend closure" in table


def test_table_reports_calibrated_once_samples_suffice(tmp_path):
    raw = write_dataset(tmp_path, "2026-09-02", 320, RTH)
    table = render_table(run(raw), min_rth=300)
    assert "**Data coverage: complete.**" in table


def test_report_can_state_and_apply_a_rolling_window(tmp_path):
    raw = write_dataset(tmp_path, "2026-09-02", 10, RTH)
    cal = run(raw, window_days=7, now=RTH + timedelta(days=1))
    assert cal.window_days == 7
    assert cal.n_books == 10
    assert "rolling 7-day window" in render_table(cal)
