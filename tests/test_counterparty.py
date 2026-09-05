"""Counterparty analysis tests.

Two measurement traps were found while building this, and both are asserted
against here so a later change cannot quietly reintroduce them: prints from one
sweeping order must not count as several arrivals, and a hole in the captured
tape must not be read as a quiet stretch.
"""
import json

import pytest

from afterbell.counterparty import (
    StateMetrics, finding,
    BURST_MS, Coverage, Trade, aggregate, arrivals, collect, diurnal_flatness,
    measure, render,
)

BASE_MS = 1_788_361_200_000      # Wed 2 Sep 2026 15:00 UTC, inside regular hours


def tr(tid, ts_ms, qty=1.0, quote=225.0, symbol="NVDABUSDT"):
    return Trade(symbol, tid, ts_ms, 225.0, qty, quote, False)


# ---------------- arrivals: one order is one arrival ----------------

def test_prints_sharing_a_timestamp_are_one_arrival():
    """A taker eating five makers prints five times and arrived once."""
    events = arrivals([tr(i, BASE_MS) for i in range(5)])
    assert len(events) == 1
    assert len(events[0]) == 5


def test_prints_at_different_instants_are_separate_arrivals():
    events = arrivals([tr(1, BASE_MS), tr(2, BASE_MS + 1)])
    assert [len(e) for e in events] == [1, 1]


def test_a_sweep_does_not_inflate_the_burst_rate():
    """The bug that made the first pass report 45-75% bursts."""
    sweep = [tr(i, BASE_MS) for i in range(20)]          # one arrival
    spaced = [tr(20 + i, BASE_MS + (i + 1) * 60_000) for i in range(40)]
    m = measure(sweep + spaced, Coverage())["RTH_OPEN"]
    assert m.trades == 60
    assert m.events == 41
    assert m.burst_rate == 0.0            # nothing arrived within 200ms
    assert m.mean_sweep == pytest.approx(60 / 41)


def test_sweep_depth_is_reported():
    m = measure([tr(1, BASE_MS), tr(2, BASE_MS),
                 tr(3, BASE_MS + 60_000)], Coverage())["RTH_OPEN"]
    assert m.events == 2
    assert m.swept_events == 1
    assert m.sweep_share == 0.5
    assert m.mean_sweep == 1.5


def test_genuinely_fast_arrivals_still_count_as_bursts():
    """Collapsing sweeps must not collapse real bursts too."""
    trades = [tr(i, BASE_MS + i * (BURST_MS // 2)) for i in range(60)]
    m = measure(trades, Coverage())["RTH_OPEN"]
    assert m.events == 60
    assert m.burst_rate == 1.0


# ---------------- holes in the tape are never timed ----------------

def test_a_gap_in_ids_is_not_timed():
    """Ids 1 and 500 are not adjacent, so the time between them means nothing."""
    m = measure([tr(1, BASE_MS), tr(500, BASE_MS + 3_600_000)],
                Coverage())["RTH_OPEN"]
    assert m.events == 2
    assert m.timed_pairs == 0
    assert m.gaps_ms == []


def test_only_consecutive_ids_are_timed():
    trades = [tr(1, BASE_MS), tr(2, BASE_MS + 1000),
              tr(90, BASE_MS + 2000), tr(91, BASE_MS + 3000)]
    m = measure(trades, Coverage())["RTH_OPEN"]
    assert m.timed_pairs == 2          # 1->2 and 90->91, never 2->90


def test_coverage_counts_what_was_missed(tmp_path):
    """Ids are consecutive, so the size of a hole is knowable exactly."""
    day = tmp_path / "2026-09-02"
    day.mkdir()
    batches = [
        {"symbol": "NVDABUSDT", "trades": [
            {"id": i, "time": BASE_MS + i, "price": "225", "qty": "1",
             "quoteQty": "225", "isBuyerMaker": False} for i in range(1, 51)]},
        # 50 trades happened in between and were never seen
        {"symbol": "NVDABUSDT", "trades": [
            {"id": i, "time": BASE_MS + i, "price": "225", "qty": "1",
             "quoteQty": "225", "isBuyerMaker": False}
            for i in range(101, 151)]},
    ]
    (day / "token.jsonl").write_text(
        "".join(json.dumps(b) + "\n" for b in batches))

    trades, coverage = collect(tmp_path)
    c = coverage["NVDABUSDT"]
    assert c.captured == 100
    assert c.span == 150                  # ids 1..150
    assert c.share == pytest.approx(2 / 3)
    assert c.complete_windows == 0        # the one window had a hole
    assert len(trades["NVDABUSDT"]) == 100


def test_overlapping_batches_are_deduplicated(tmp_path):
    day = tmp_path / "2026-09-02"
    day.mkdir()
    def batch(lo):
        return {"symbol": "NVDABUSDT", "trades": [
            {"id": i, "time": BASE_MS + i, "price": "225", "qty": "1",
             "quoteQty": "225", "isBuyerMaker": False}
            for i in range(lo, lo + 50)]}
    (day / "token.jsonl").write_text(
        json.dumps(batch(1)) + "\n" + json.dumps(batch(20)) + "\n")

    trades, coverage = collect(tmp_path)
    assert len(trades["NVDABUSDT"]) == 69          # 1..69, not 100
    assert coverage["NVDABUSDT"].complete_windows == 1


# ---------------- diurnal flatness needs a whole day ----------------

def test_diurnal_flatness_needs_every_hour():
    """A partial day cannot answer whether volume dips overnight."""
    half = [tr(i, BASE_MS + i * 3_600_000) for i in range(12)]
    assert diurnal_flatness(half) is None


def test_diurnal_flatness_of_a_flat_day_is_one():
    day = [tr(i, BASE_MS + i * 3_600_000) for i in range(24)]
    assert diurnal_flatness(day) == pytest.approx(1.0)


def test_a_quiet_hour_lowers_flatness():
    day = [tr(i, BASE_MS + i * 3_600_000, quote=225.0) for i in range(24)]
    day.append(tr(99, BASE_MS + 5 * 3_600_000, quote=225.0))   # a busy hour
    assert diurnal_flatness(day) == pytest.approx(0.5)


# ---------------- thin samples say nothing ----------------

def test_too_few_samples_report_nothing_rather_than_a_number():
    m = measure([tr(i, BASE_MS + i * 1000) for i in range(5)],
                Coverage())["RTH_OPEN"]
    assert m.interarrival_cv is None
    assert m.burst_rate is None
    assert m.round_notional_share is None


def test_the_rendered_table_shows_a_dash_for_missing_measures():
    m = {"NVDABUSDT": measure([tr(i, BASE_MS + i * 1000) for i in range(5)],
                              Coverage())}
    out = render(m, {"NVDABUSDT": Coverage()}, {"NVDABUSDT": None})
    assert "–" in out


# ---------------- aggregation ----------------

def test_aggregate_averages_across_symbols_not_prints():
    """One heavily traded symbol must not speak for the others."""
    busy = measure([tr(i, BASE_MS + i * 1000) for i in range(2000)],
                   Coverage())
    quiet = measure([tr(i, BASE_MS + i * 1000, symbol="MUBUSDT")
                     for i in range(60)], Coverage())
    agg = aggregate({"NVDABUSDT": busy, "MUBUSDT": quiet})
    assert agg["RTH_OPEN"].arrivals == 2060
    # an unweighted mean of two equal per-symbol rates is that rate
    assert agg["RTH_OPEN"].burst_rate == pytest.approx(
        busy["RTH_OPEN"].burst_rate)


# ---------------- the comparison refuses when it cannot be made ----------

def _states(rth_cov, wknd_cov, rth_burst=0.2, wknd_burst=0.5):
    """Two states with chosen coverage and burst rates."""
    def mk(state, seen, span, burst):
        m = StateMetrics(state)
        m.seen_ids, m.span_ids = seen, span
        m.events = 100
        m.gaps_ms = [10.0] * int(100 * burst) + [10_000.0] * int(100 * (1 - burst))
        m.bursts = int(100 * burst)
        m.quote_qtys = [225.0] * 100
        return m
    return {"NVDABUSDT": {
        "RTH_OPEN": mk("RTH_OPEN", int(1000 * rth_cov), 1000, rth_burst),
        "CLOSED_WEEKEND": mk("CLOSED_WEEKEND", int(1000 * wknd_cov), 1000,
                             wknd_burst)}}


def test_uneven_coverage_refuses_to_state_a_direction():
    """The real case: 24% of regular hours against 55% of the weekend."""
    by_symbol = _states(0.24, 0.55)
    out = "\n".join(finding(aggregate(by_symbol), by_symbol))
    assert "Not enough of the tape was captured" in out
    assert "24.0%" in out and "55.0%" in out
    assert "more clustered" not in out and "less clustered" not in out


def test_even_but_low_coverage_still_refuses():
    """Equal sampling is not enough; it has to be nearly complete."""
    by_symbol = _states(0.60, 0.60)
    out = "\n".join(finding(aggregate(by_symbol), by_symbol))
    assert "Not enough of the tape was captured" in out


def test_complete_coverage_permits_the_comparison():
    by_symbol = _states(1.0, 1.0, rth_burst=0.2, wknd_burst=0.5)
    out = "\n".join(finding(aggregate(by_symbol), by_symbol))
    assert "Not enough of the tape" not in out
    assert "more clustered" in out          # weekend 50% vs regular 20%


def test_the_stated_direction_follows_the_measurement():
    by_symbol = _states(1.0, 1.0, rth_burst=0.5, wknd_burst=0.2)
    out = "\n".join(finding(aggregate(by_symbol), by_symbol))
    assert "less clustered" in out


def test_per_state_coverage_is_computed_from_ids():
    """Seen over occurred, where occurred comes from the id distance."""
    trades = [tr(1, BASE_MS), tr(2, BASE_MS + 1000), tr(12, BASE_MS + 2000)]
    m = measure(trades, Coverage())["RTH_OPEN"]
    assert m.span_ids == 11               # 1->2 is 1, 2->12 is 10
    assert m.seen_ids == 2                # one print seen at each step
    assert m.state_coverage == pytest.approx(2 / 11)
