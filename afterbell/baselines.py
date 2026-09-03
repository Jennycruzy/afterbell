"""Session baselines: the denominators for every liquidity claim.

Part VIII: the rolling medians below are computed over RTH_OPEN samples ONLY.
A Saturday spread is meaningless on its own; it is meaningful as a multiple of
what that same book looked like while the reference market was open. Those
denominators cannot be back-filled after the fact, which is why the recorder
runs before anything else exists.

Law 1: a symbol with fewer than the policy's min_rth_samples observations is
reported UNCALIBRATED and receives the most restrictive treatment available.
It is never quietly compared against a baseline built from four samples.
"""
from __future__ import annotations

import glob
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from afterbell.clock import MarketState, evaluate
from afterbell.measure import Book, depth_within, half_spread_bps

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"


@dataclass
class Sample:
    symbol: str
    ts: datetime
    state: MarketState
    half_spread_bps: float
    depth_1pct: float


@dataclass
class Baseline:
    """Per-symbol RTH reference statistics."""
    symbol: str
    n_rth: int
    median_half_spread_bps: float | None
    median_depth_1pct: float | None
    n_by_state: dict[str, int] = field(default_factory=dict)
    min_samples: int = 300

    @property
    def status(self) -> str:
        ok = (self.n_rth >= self.min_samples
              and self.median_half_spread_bps is not None
              and self.median_depth_1pct is not None
              and self.median_half_spread_bps > 0
              and self.median_depth_1pct > 0)
        return "CALIBRATED" if ok else "UNCALIBRATED"

    @property
    def is_calibrated(self) -> bool:
        return self.status == "CALIBRATED"

    def spread_ratio(self, half_spread_now: float) -> float | None:
        """How much wider the book is now than its own RTH median."""
        if not self.is_calibrated:
            return None
        return half_spread_now / self.median_half_spread_bps

    def liquidity_ratio(self, depth_now: float) -> float | None:
        """What fraction of its own RTH depth the book is showing now."""
        if not self.is_calibrated:
            return None
        return depth_now / self.median_depth_1pct


def iter_records(raw_dir: Path | None = None) -> Iterator[dict]:
    base = raw_dir or RAW
    for path in sorted(glob.glob(str(base / "*" / "token.jsonl"))):
        with open(path) as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)


def to_sample(rec: dict, band_pct: float = 1.0) -> Sample | None:
    """Measure one recorded book. None when it cannot be measured (Law 3)."""
    book = Book.from_record(rec)
    if book is None:
        return None
    hs = half_spread_bps(book)
    dp = depth_within(book, band_pct)
    if hs is None or dp is None:
        return None
    return Sample(rec["symbol"], book.ts, evaluate(book.ts).state, hs, dp)


def build(records: Iterable[dict] | None = None, *, min_samples: int = 300,
          band_pct: float = 1.0) -> dict[str, Baseline]:
    """Build per-symbol baselines from recorded books."""
    recs = records if records is not None else iter_records()
    rth_spread: dict[str, list[float]] = defaultdict(list)
    rth_depth: dict[str, list[float]] = defaultdict(list)
    by_state: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for rec in recs:
        s = to_sample(rec, band_pct)
        if s is None:
            continue
        by_state[s.symbol][s.state.value] += 1
        if s.state is MarketState.RTH_OPEN:
            rth_spread[s.symbol].append(s.half_spread_bps)
            rth_depth[s.symbol].append(s.depth_1pct)

    out: dict[str, Baseline] = {}
    for symbol in sorted(by_state):
        spreads, depths = rth_spread[symbol], rth_depth[symbol]
        out[symbol] = Baseline(
            symbol=symbol,
            n_rth=len(spreads),
            median_half_spread_bps=statistics.median(spreads) if spreads else None,
            median_depth_1pct=statistics.median(depths) if depths else None,
            n_by_state=dict(by_state[symbol]),
            min_samples=min_samples,
        )
    return out


def state_distribution(records: Iterable[dict] | None = None,
                       band_pct: float = 1.0) -> dict[str, dict[str, dict]]:
    """Median spread and depth per (symbol, market state).

    This is what turns the P2 tiers and P3 bands from round numbers into
    measured percentiles, and what the published calibration table is built on.
    """
    acc: dict[tuple[str, str], list[Sample]] = defaultdict(list)
    recs = records if records is not None else iter_records()
    for rec in recs:
        s = to_sample(rec, band_pct)
        if s is not None:
            acc[(s.symbol, s.state.value)].append(s)

    out: dict[str, dict[str, dict]] = defaultdict(dict)
    for (symbol, state), samples in sorted(acc.items()):
        spreads = [x.half_spread_bps for x in samples]
        depths = [x.depth_1pct for x in samples]
        out[symbol][state] = {
            "n": len(samples),
            "median_half_spread_bps": statistics.median(spreads),
            "median_depth_1pct": statistics.median(depths),
            "p95_half_spread_bps": _pct(spreads, 95),
            "p05_depth_1pct": _pct(depths, 5),
        }
    return dict(out)


def _pct(values: list[float], p: float) -> float:
    """Nearest-rank percentile. Explicit, so the calibration table is
    reproducible from the raw data by anyone who wants to check it."""
    if not values:
        raise ValueError("percentile of an empty sample")
    s = sorted(values)
    k = max(1, min(len(s), round(p / 100.0 * len(s))))
    return s[k - 1]
