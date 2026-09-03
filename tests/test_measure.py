"""Measurement tests.

The books here are constructed with explicit ladders so the arithmetic can be
checked against a hand-computed answer. That is unit testing, not a market
mock: no test here stands in for a live price, and nothing in the production
path ever fabricates a book (Law 2).
"""
from datetime import datetime, timezone

import pytest

from afterbell.measure import (
    Book, BookProblem, Level, Side, basis_bps, depth_within, half_spread_bps,
    walk_cost_bps,
)

TS = datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc)


def mk(bids, asks):
    return Book("TESTUSDT", TS,
                tuple(Level(p, q) for p, q in bids),
                tuple(Level(p, q) for p, q in asks))


def test_half_spread_is_half_the_spread_over_mid():
    b = mk([(99.0, 10)], [(101.0, 10)])          # mid 100, spread 2
    assert half_spread_bps(b) == pytest.approx(100.0)


def test_depth_band_excludes_levels_outside_it():
    b = mk([(99.5, 10), (98.0, 10)], [(100.5, 10), (102.0, 10)])
    # mid 100 -> band [99, 101]. Only 99.5 and 100.5 qualify.
    assert depth_within(b, 1.0) == pytest.approx(99.5 * 10 + 100.5 * 10)


def test_walk_cost_on_a_single_level_is_the_spread_to_mid():
    b = mk([(99.0, 1000)], [(101.0, 1000)])
    w = walk_cost_bps(b, 1000.0, Side.BUY)
    assert w.vwap == pytest.approx(101.0)
    assert w.cost_bps == pytest.approx(100.0)
    assert w.levels_consumed == 1


def test_walk_cost_grows_as_it_eats_levels():
    b = mk([(99.0, 100)], [(100.0, 1), (110.0, 100)])
    cheap = walk_cost_bps(b, 100.0, Side.BUY).cost_bps
    deep = walk_cost_bps(b, 5000.0, Side.BUY).cost_bps
    assert deep > cheap


def test_sell_side_cost_is_also_positive_when_worse_than_mid():
    b = mk([(99.0, 1000)], [(101.0, 1000)])
    assert walk_cost_bps(b, 1000.0, Side.SELL).cost_bps == pytest.approx(100.0)


def test_insufficient_depth_is_a_problem_not_a_number():
    """Law 3: past the end of the book the cost is unknown. Extrapolating it
    would be a fabricated measurement, and a guard that sizes on a fabricated
    cost is worse than no guard."""
    b = mk([(99.0, 1)], [(101.0, 1)])
    assert walk_cost_bps(b, 1_000_000.0, Side.BUY) is BookProblem.INSUFFICIENT_DEPTH


def test_crossed_and_empty_books_refuse_to_measure():
    crossed = mk([(102.0, 10)], [(101.0, 10)])
    assert half_spread_bps(crossed) is None
    assert depth_within(crossed) is None
    assert walk_cost_bps(crossed, 100.0) is BookProblem.CROSSED
    assert Book.from_record({"symbol": "X", "ts": "2026-09-05T03:00:00.000Z",
                             "bids": [], "asks": []}) is None


def test_basis_sign_and_magnitude():
    assert basis_bps(190.16, 182.40) == pytest.approx(425.4, abs=0.5)
    assert basis_bps(180.0, 200.0) == pytest.approx(-1000.0)
    assert basis_bps(100.0, 100.0) == 0.0


def test_basis_refuses_a_non_positive_reference():
    with pytest.raises(ValueError):
        basis_bps(100.0, 0.0)


def test_truncated_book_refuses_to_report_depth():
    """A ladder cut off by our own request is a lower bound, not a
    measurement. This is the 4.8x understatement that shipped for 16 cycles."""
    bids = [(99.99 - i * 0.01, 10) for i in range(20)]   # 99.99 -> 99.80
    asks = [(100.01 + i * 0.01, 10) for i in range(20)]  # 100.01 -> 100.20
    b = Book("T", TS, tuple(Level(p, q) for p, q in bids),
             tuple(Level(p, q) for p, q in asks), depth_limit=20)
    assert b.is_truncated
    assert not b.spans(1.0)          # ladder reaches only ~0.19% from mid
    assert depth_within(b, 1.0) is None
    # but a band the ladder does cover is measurable
    assert depth_within(b, 0.1) is not None


def test_book_that_ends_naturally_is_measured():
    """Every level the venue holds, well inside the request limit: this is the
    whole book, so the band is measurable even though the ladder is short."""
    b = Book("T", TS, (Level(99.0, 10),), (Level(101.0, 10),), depth_limit=5000)
    assert not b.is_truncated
    assert depth_within(b, 1.0) == pytest.approx(99.0 * 10 + 101.0 * 10)
