"""Order-book measurement: spread, depth, walk cost, basis.

Law 1: nothing here asserts a market condition. Every value is computed from a
book that was actually observed.

Law 3: when the book cannot answer the question - it is empty, crossed, or too
thin to fill the requested size - these functions return None with a reason
rather than extrapolating past the last level. A walk cost invented beyond the
end of the book is exactly the kind of quietly wrong number that makes a guard
worse than no guard.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class BookProblem(str, Enum):
    EMPTY = "EMPTY_BOOK"
    CROSSED = "CROSSED_BOOK"
    INSUFFICIENT_DEPTH = "INSUFFICIENT_DEPTH"


@dataclass(frozen=True)
class Level:
    price: float
    qty: float

    @property
    def notional(self) -> float:
        return self.price * self.qty


@dataclass(frozen=True)
class Book:
    symbol: str
    ts: datetime
    bids: tuple[Level, ...]   # descending price
    asks: tuple[Level, ...]   # ascending price
    # Levels requested from the venue. When a side returns exactly this many,
    # the ladder was cut off by the request rather than by the end of the book,
    # and anything measured beyond its edge is a lower bound rather than a
    # measurement. Records written before this field existed were taken at 20.
    depth_limit: int = 20

    @classmethod
    def from_record(cls, rec: dict) -> "Book | None":
        """Build from a recorder token record. None if unusable (Law 3)."""
        bids = tuple(Level(float(p), float(q)) for p, q in rec.get("bids", []))
        asks = tuple(Level(float(p), float(q)) for p, q in rec.get("asks", []))
        if not bids or not asks:
            return None
        ts = datetime.fromisoformat(rec["ts"].replace("Z", "+00:00"))
        return cls(rec["symbol"], ts.astimezone(timezone.utc), bids, asks,
                   int(rec.get("depth_limit", 20)))

    @property
    def is_truncated(self) -> bool:
        """True when the venue returned as many levels as we asked for."""
        return (len(self.bids) >= self.depth_limit
                or len(self.asks) >= self.depth_limit)

    def spans(self, band_pct: float) -> bool:
        """True when both ladders reach past the band on their own."""
        lo = self.mid * (1.0 - band_pct / 100.0)
        hi = self.mid * (1.0 + band_pct / 100.0)
        return self.bids[-1].price <= lo and self.asks[-1].price >= hi

    @property
    def best_bid(self) -> float:
        return self.bids[0].price

    @property
    def best_ask(self) -> float:
        return self.asks[0].price

    @property
    def is_crossed(self) -> bool:
        return self.best_bid >= self.best_ask

    @property
    def mid(self) -> float:
        return (self.best_bid + self.best_ask) / 2.0


def half_spread_bps(book: Book) -> float | None:
    """(ask - bid) / (2 * mid) * 10_000."""
    if book.is_crossed:
        return None
    return (book.best_ask - book.best_bid) / (2.0 * book.mid) * 10_000.0


def depth_within(book: Book, band_pct: float = 1.0) -> float | None:
    """Resting notional within +/- band_pct of mid, both sides summed.

    Returns None when the ladder stops inside the band because the request was
    truncated: that figure would be a lower bound on the real depth, and a
    lower bound silently used as a measurement is how a liquidity ratio ends up
    understated by 4.8x (Law 3). A book that simply ends before the band, with
    every level the venue holds, is measured normally.
    """
    if book.is_crossed:
        return None
    if book.is_truncated and not book.spans(band_pct):
        return None
    mid = book.mid
    lo = mid * (1.0 - band_pct / 100.0)
    hi = mid * (1.0 + band_pct / 100.0)
    bid_side = sum(l.notional for l in book.bids if l.price >= lo)
    ask_side = sum(l.notional for l in book.asks if l.price <= hi)
    return bid_side + ask_side


@dataclass(frozen=True)
class WalkResult:
    notional_requested: float
    notional_filled: float
    vwap: float
    mid: float
    cost_bps: float
    levels_consumed: int
    exhausted_book: bool


def walk_cost_bps(book: Book, notional: float,
                  side: Side = Side.BUY) -> WalkResult | BookProblem:
    """Simulated cost of a marketable order against this book.

    Returns INSUFFICIENT_DEPTH when the visible book cannot fill the request.
    That is a hard BLOCK, not a large number: the true cost is unknown, and
    guessing it would be a fabricated measurement.
    """
    if not book.bids or not book.asks:
        return BookProblem.EMPTY
    if book.is_crossed:
        return BookProblem.CROSSED
    if notional <= 0:
        raise ValueError("notional must be positive")

    levels = book.asks if side is Side.BUY else book.bids
    mid = book.mid
    remaining = notional
    spent = 0.0
    qty = 0.0
    used = 0

    for lvl in levels:
        if remaining <= 0:
            break
        take_notional = min(remaining, lvl.notional)
        spent += take_notional
        qty += take_notional / lvl.price
        remaining -= take_notional
        used += 1

    if remaining > 1e-9:
        return BookProblem.INSUFFICIENT_DEPTH

    vwap = spent / qty
    # Positive means worse than mid, for either side.
    cost = (vwap - mid) / mid * 10_000.0
    if side is Side.SELL:
        cost = -cost
    return WalkResult(notional, spent, vwap, mid, cost, used, False)


def basis_bps(token_price: float, reference_price: float) -> float:
    """(token - reference) / reference * 10_000.

    Always reported alongside REFERENCE_AGE: a basis against a 61-hour-old
    close means something categorically different from one against a live
    quote (Law 8).
    """
    if reference_price <= 0:
        raise ValueError(f"non-positive reference price: {reference_price}")
    return (token_price - reference_price) / reference_price * 10_000.0
