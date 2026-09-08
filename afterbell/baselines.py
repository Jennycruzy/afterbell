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
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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


# ---------------------------------------------------------------------------
# Measured-sample cache.
#
# Rebuilding a baseline used to re-read and re-parse the whole raw archive.
# That cost is not a constant: full-depth books made the archive grow about
# 1.2 GB a day, the scan went from 33s to over 13 minutes on this two-core
# box, and a server that made a caller wait for it answered 504 instead. The
# work was also entirely redundant, because a day's records never change once
# that day is over.
#
# So each day's file is measured once. The archive is append-only JSONL, so a
# cache can record how many bytes it has already consumed and, on the next
# pass, measure only what was appended since. A partial trailing line is left
# unconsumed and picked up next time, which is what makes this safe to run
# against the file the recorder is still writing to.
#
# The cache holds measurements, never decisions, and is keyed by depth band
# because the band changes what depth means. Deleting it costs time, not
# correctness.
# ---------------------------------------------------------------------------
CACHE = ROOT / "data" / "cache" / "samples"


def _cache_path(day_file: Path, band_pct: float) -> Path:
    return CACHE / f"band-{band_pct:g}" / f"{day_file.parent.name}.json"


def _load_cache(path: Path) -> tuple[int, list]:
    try:
        blob = json.loads(path.read_text())
        return int(blob["offset"]), list(blob["samples"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0, []


def _store_cache(path: Path, offset: int, rows: list) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"offset": offset, "samples": rows}))
        tmp.replace(path)                  # atomic: never a half-written cache
    except OSError:
        pass                               # a cache that cannot be written is
                                           # a slow build, not a wrong one


def _measure_from(day_file: Path, offset: int, band_pct: float) -> tuple[list, int]:
    """Measure the records appended after `offset`. Returns rows and the new
    offset, which only ever advances past complete lines."""
    rows: list = []
    consumed = offset
    with day_file.open("rb") as fh:
        fh.seek(offset)
        for raw in fh:
            if not raw.endswith(b"\n"):
                break                      # the recorder is mid-write; leave it
            consumed += len(raw)
            line = raw.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            s = to_sample(rec, band_pct)
            if s is not None:
                rows.append([s.ts.isoformat(), s.symbol, s.state.value,
                             s.half_spread_bps, s.depth_1pct])
    return rows, consumed


def _day_samples(day_file: Path, band_pct: float, use_cache: bool) -> list[Sample]:
    if not use_cache:
        rows, _ = _measure_from(day_file, 0, band_pct)
    else:
        cache = _cache_path(day_file, band_pct)
        offset, rows = _load_cache(cache)
        try:
            size = day_file.stat().st_size
        except OSError:
            size = 0
        if offset > size:                  # truncated or rotated: start over
            offset, rows = 0, []
        fresh, new_offset = _measure_from(day_file, offset, band_pct)
        if fresh or new_offset != offset:
            rows = rows + fresh
            _store_cache(cache, new_offset, rows)
    return [Sample(symbol=r[1],
                   ts=datetime.fromisoformat(r[0]),
                   state=MarketState(r[2]),
                   half_spread_bps=r[3],
                   depth_1pct=r[4])
            for r in rows]


def iter_samples(band_pct: float = 1.0, raw_dir: Path | None = None, *,
                 use_cache: bool = True) -> Iterator[Sample]:
    """Every measured sample in the archive, day by day."""
    base = raw_dir or RAW
    for path in sorted(glob.glob(str(base / "*" / "token.jsonl"))):
        yield from _day_samples(Path(path), band_pct, use_cache)


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


def _cutoff(window_days: float | None, now: datetime | None) -> datetime | None:
    if window_days is None:
        return None
    days = float(window_days)
    if not math.isfinite(days) or days <= 0:
        raise ValueError("baseline window_days must be a finite positive number")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("baseline reference time must be timezone-aware")
    return current.astimezone(timezone.utc) - timedelta(days=days)


def _record_ts(rec: dict) -> datetime | None:
    try:
        value = rec["ts"]
        if not isinstance(value, str):
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _measured(records: Iterable[dict] | None, band_pct: float,
              cutoff: datetime | None) -> Iterator[Sample]:
    """Samples to build from, cached when reading the archive itself.

    `Book.from_record` parses the same `ts` field `_record_ts` does, so the
    cutoff selects the same records on either path.
    """
    if records is None:
        for s in iter_samples(band_pct):
            if cutoff is None or s.ts >= cutoff:
                yield s
        return
    for rec in records:
        if cutoff is not None:
            ts = _record_ts(rec)
            if ts is None or ts < cutoff:
                continue
        s = to_sample(rec, band_pct)
        if s is not None:
            yield s


def build(records: Iterable[dict] | None = None, *, min_samples: int = 300,
          band_pct: float = 1.0, window_days: float | None = None,
          now: datetime | None = None) -> dict[str, Baseline]:
    """Build per-symbol baselines from recorded books."""
    cutoff = _cutoff(window_days, now)
    rth_spread: dict[str, list[float]] = defaultdict(list)
    rth_depth: dict[str, list[float]] = defaultdict(list)
    by_state: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for s in _measured(records, band_pct, cutoff):
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
                       band_pct: float = 1.0,
                       window_days: float | None = None,
                       now: datetime | None = None) -> dict[str, dict[str, dict]]:
    """Median spread and depth per (symbol, market state).

    This is what turns the P2 tiers and P3 bands from round numbers into
    measured percentiles, and what the published calibration table is built on.
    """
    acc: dict[tuple[str, str], list[Sample]] = defaultdict(list)
    cutoff = _cutoff(window_days, now)
    for s in _measured(records, band_pct, cutoff):
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
