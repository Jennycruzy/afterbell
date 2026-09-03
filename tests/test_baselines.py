"""Baseline tests. The refusals matter more than the medians here: a ratio
computed against four samples is worse than no ratio at all."""
from datetime import datetime, timezone

import pytest

from afterbell.baselines import Baseline, build


def rec(symbol, ts, bid, ask, qty=100.0, limit=5000, step=0.5, n=40):
    """One recorded book. Default ladder spans well past +/-1% of mid."""
    bids = [[f"{bid - i * step:.4f}", f"{qty}"] for i in range(n)]
    asks = [[f"{ask + i * step:.4f}", f"{qty}"] for i in range(n)]
    return {"symbol": symbol, "ts": ts, "bids": bids, "asks": asks,
            "depth_limit": limit}


RTH = "2026-09-03T14:00:00.000Z"       # Thursday 10:00 ET, regular session
NIGHT = "2026-09-03T02:00:00.000Z"     # Wednesday 22:00 ET, closed


def test_only_rth_samples_feed_the_baseline():
    records = ([rec("NVDABUSDT", RTH, 99.0, 101.0) for _ in range(5)]
               + [rec("NVDABUSDT", NIGHT, 90.0, 110.0) for _ in range(50)])
    b = build(records, min_samples=3)["NVDABUSDT"]
    assert b.n_rth == 5
    assert b.n_by_state["CLOSED_OVERNIGHT"] == 50
    # the wide overnight books must not move the RTH median
    assert b.median_half_spread_bps == pytest.approx(100.0, rel=0.01)


def test_thin_sample_is_uncalibrated_and_refuses_ratios():
    records = [rec("NVDABUSDT", RTH, 99.0, 101.0) for _ in range(10)]
    b = build(records, min_samples=300)["NVDABUSDT"]
    assert b.status == "UNCALIBRATED"
    assert b.spread_ratio(5.0) is None
    assert b.liquidity_ratio(1000.0) is None


def test_calibrated_baseline_produces_ratios():
    records = [rec("NVDABUSDT", RTH, 99.0, 101.0) for _ in range(300)]
    b = build(records, min_samples=300)["NVDABUSDT"]
    assert b.is_calibrated
    assert b.spread_ratio(b.median_half_spread_bps * 6) == pytest.approx(6.0)
    assert b.liquidity_ratio(b.median_depth_1pct * 0.19) == pytest.approx(0.19)


def test_records_truncated_inside_the_band_are_excluded_entirely():
    """A ladder cut off by our own request before it reaches the band cannot
    measure that band, so it must not count as a sample at all. This is the
    shape of the 20-level records the recorder wrote for its first 16 cycles:
    40 levels at a 0.001 step reach only ~0.04% from mid."""
    records = [rec("NVDABUSDT", RTH, 99.999, 100.001, limit=40, step=0.001)
               for _ in range(10)]
    assert build(records, min_samples=1) == {}


def test_truncation_past_the_band_is_still_measurable():
    """Truncation only matters when the ladder stops inside the band. A book
    cut off well outside it has already answered the question."""
    records = [rec("NVDABUSDT", RTH, 99.0, 101.0, limit=40) for _ in range(5)]
    b = build(records, min_samples=1)["NVDABUSDT"]
    assert b.n_rth == 5


def test_zero_median_never_becomes_a_divisor():
    b = Baseline("X", n_rth=500, median_half_spread_bps=0.0,
                 median_depth_1pct=0.0, min_samples=300)
    assert b.status == "UNCALIBRATED"
    assert b.spread_ratio(1.0) is None


def test_rolling_window_excludes_old_rth_samples():
    old = [rec("NVDABUSDT", "2026-09-01T15:00:00.000Z", 99.0, 101.0)
           for _ in range(20)]
    recent = [rec("NVDABUSDT", "2026-09-09T15:00:00.000Z", 99.0, 101.0)
              for _ in range(5)]
    b = build(old + recent, min_samples=1, window_days=7,
              now=datetime(2026, 9, 10, 12, tzinfo=timezone.utc))["NVDABUSDT"]
    assert b.n_rth == 5
