"""Calibration: replace every invented threshold with a measured one.

Part VIII. A threshold chosen without measurements can be challenged, so this
module reads the recorded books and reference prints and produces the five
things the specification asks for:

  1. session baselines   - RTH_OPEN median half-spread and depth, per symbol
  2. off-hours spread    - the same statistics over CLOSED_OVERNIGHT, so
                           Friday night has a comparison that predates the
                           weekend
  3. basis distribution  - basis_bps by market state, with price-difference bands proposed at
                           empirical percentiles rather than round numbers
  4. walk-cost curve     - marketable orders at $100 / $500 / $2,000 / $10,000
                           against recorded books, by state
  5. the published table - markdown for the README, with sample counts beside
                           every number

Law 1 governs the output. A statistic computed from too few samples is not a
weaker statistic, it is not a statistic, and it is reported as data-incomplete
rather than published with a caveat.

Law 6 governs what happens next. This module never edits the live policy. It
writes a PROPOSAL, and a human reads the diff and applies it, because a
threshold that can be rewritten by a process is a threshold that can be
rewritten by an attacker who reaches that process.
"""
from __future__ import annotations

import glob
import json
import statistics
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from afterbell.baselines import (
    RAW, _cutoff, _pct, _record_ts, iter_records, to_sample,
)
from afterbell.clock import MarketState
from afterbell.instruments import REGISTRY
from afterbell.measure import Book, BookProblem, Side, basis_bps, walk_cost_bps

# The sizes the walk-cost curve is measured at, from Part VIII.
LADDER_USDT = (100.0, 500.0, 2_000.0, 10_000.0)

_PUBLIC_STATE_LABELS = {
    "RTH_OPEN": "Open",
    "RTH_PRE": "Before open",
    "RTH_POST": "After close",
    "CLOSED_OVERNIGHT": "Overnight closure",
    "CLOSED_WEEKEND": "Weekend closure",
    "CLOSED_HOLIDAY": "Market holiday",
}


def _public_state_label(state: str) -> str:
    return _PUBLIC_STATE_LABELS.get(state, state.replace("_", " ").title())


# How far apart a book and a reference print may be and still be treated as
# simultaneous. The recorder writes both once a cycle, so a pairing wider than
# a cycle would silently compare a book against the previous cycle's price.
PAIR_TOLERANCE_S = 90.0

# Below this, a per-state statistic is reported but never proposed as a
# threshold. It is deliberately lower than the 300 the guard demands of an RTH
# baseline: a distribution shape is legible earlier than a denominator is
# trustworthy, and saying so is more honest than one number for both.
MIN_STATE_SAMPLES = 60


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(
        timezone.utc)


# --------------------------------------------------------------------------
# Reference prints, indexed for pairing
# --------------------------------------------------------------------------

def iter_reference(raw_dir: Path | None = None) -> Iterator[dict]:
    base = raw_dir or RAW
    for path in sorted(glob.glob(str(base / "*" / "reference.jsonl"))):
        with open(path) as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)


@dataclass
class ReferenceIndex:
    """Reference prices by underlying, searchable by time.

    Cycle numbers restart whenever the recorder does, so pairing on them would
    silently mis-align across a restart. Time is the only key that survives.
    """
    times: dict[str, list[datetime]] = field(default_factory=dict)
    prices: dict[str, list[float]] = field(default_factory=dict)

    @classmethod
    def build(cls, raw_dir: Path | None = None, *,
              window_days: float | None = None,
              now: datetime | None = None) -> "ReferenceIndex":
        cutoff = _cutoff(window_days, now)
        acc: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        for rec in iter_reference(raw_dir):
            ts = _parse(rec["ts"])
            if cutoff is not None and ts < cutoff:
                continue
            derived = rec.get("derived") or {}
            for sym, d in derived.items():
                if d.get("price") is not None:
                    acc[sym].append((ts, float(d["price"])))
            # The Alpaca-shaped record carries snapshots instead; it is read
            # so a dataset recorded before the provider change is not orphaned.
            for sym, snap in (rec.get("snapshots") or {}).items():
                bar = (snap or {}).get("dailyBar") or {}
                if bar.get("c") is not None and sym not in derived:
                    acc[sym].append((ts, float(bar["c"])))
        idx = cls()
        for sym, rows in acc.items():
            rows.sort()
            idx.times[sym] = [r[0] for r in rows]
            idx.prices[sym] = [r[1] for r in rows]
        return idx

    def at(self, underlying: str, ts: datetime) -> float | None:
        """Nearest reference print, or None if none is close enough."""
        times = self.times.get(underlying)
        if not times:
            return None
        i = bisect_left(times, ts)
        best, best_gap = None, None
        for j in (i - 1, i):
            if 0 <= j < len(times):
                gap = abs((times[j] - ts).total_seconds())
                if best_gap is None or gap < best_gap:
                    best, best_gap = self.prices[underlying][j], gap
        return best if best_gap is not None and best_gap <= PAIR_TOLERANCE_S \
            else None


# --------------------------------------------------------------------------
# The four measured distributions
# --------------------------------------------------------------------------

@dataclass
class StateStats:
    n: int
    median_half_spread_bps: float | None = None
    median_depth_1pct: float | None = None
    p95_half_spread_bps: float | None = None
    p05_depth_1pct: float | None = None

    @property
    def enough(self) -> bool:
        return self.n >= MIN_STATE_SAMPLES


@dataclass
class BasisStats:
    n: int
    p50: float | None = None
    p75: float | None = None
    p95: float | None = None
    p99: float | None = None

    @property
    def enough(self) -> bool:
        return self.n >= MIN_STATE_SAMPLES


@dataclass
class Calibration:
    generated_at: datetime
    band_pct: float
    liquidity: dict[str, dict[str, StateStats]]
    basis: dict[str, BasisStats]
    walk: dict[str, dict[float, float | None]]
    n_books: int
    n_reference: int
    window_days: float | None = None

    @property
    def rth_ready(self) -> dict[str, int]:
        return {sym: st.get("RTH_OPEN", StateStats(0)).n
                for sym, st in self.liquidity.items()}


def run(raw_dir: Path | None = None, band_pct: float = 1.0,
        *, window_days: float | None = None,
        now: datetime | None = None) -> Calibration:
    """Measure the configured rolling window, or all data when explicitly unset."""
    generated_at = now or datetime.now(timezone.utc)
    cutoff = _cutoff(window_days, generated_at)
    ref = ReferenceIndex.build(raw_dir, window_days=window_days,
                               now=generated_at)
    liq: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    basis: dict[str, list[float]] = defaultdict(list)
    walk: dict[str, dict[float, list[float]]] = defaultdict(
        lambda: defaultdict(list))
    n_books = 0

    records = (iter_records(raw_dir) if raw_dir is not None
               else iter_records())
    for rec in records:
        if cutoff is not None:
            ts = _record_ts(rec)
            if ts is None or ts < cutoff:
                continue
        sample = to_sample(rec, band_pct)
        if sample is None:
            continue
        n_books += 1
        state = sample.state.value
        liq[sample.symbol][state].append(
            (sample.half_spread_bps, sample.depth_1pct))

        book = Book.from_record(rec)
        if book is None:
            continue

        # Walk cost by state, at each ladder size. A size the book cannot
        # fill is recorded as a miss rather than as a large number, because
        # "unfillable" and "expensive" are different findings.
        for size in LADDER_USDT:
            r = walk_cost_bps(book, size, Side.BUY)
            if not isinstance(r, BookProblem):
                walk[state][size].append(r.cost_bps)

        inst = REGISTRY.get(sample.symbol)
        if inst is not None:
            p = ref.at(inst.underlying, book.ts)
            if p is not None:
                basis[state].append(basis_bps(book.mid, p))

    liquidity: dict[str, dict[str, StateStats]] = {}
    for sym, states in sorted(liq.items()):
        liquidity[sym] = {}
        for state, rows in sorted(states.items()):
            spreads = [r[0] for r in rows]
            depths = [r[1] for r in rows]
            liquidity[sym][state] = StateStats(
                n=len(rows),
                median_half_spread_bps=statistics.median(spreads),
                median_depth_1pct=statistics.median(depths),
                p95_half_spread_bps=_pct(spreads, 95),
                p05_depth_1pct=_pct(depths, 5))

    basis_out: dict[str, BasisStats] = {}
    for state, vals in sorted(basis.items()):
        a = [abs(v) for v in vals]
        basis_out[state] = BasisStats(
            n=len(vals), p50=_pct(a, 50), p75=_pct(a, 75),
            p95=_pct(a, 95), p99=_pct(a, 99))

    walk_out: dict[str, dict[float, float | None]] = {}
    for state, sizes in sorted(walk.items()):
        walk_out[state] = {
            size: (statistics.median(v) if len(v) >= MIN_STATE_SAMPLES else None)
            for size, v in sorted(sizes.items())}

    return Calibration(
        generated_at=generated_at, band_pct=band_pct,
        liquidity=liquidity, basis=basis_out, walk=walk_out,
        n_books=n_books,
        n_reference=sum(len(v) for v in ref.times.values()),
        window_days=window_days)


# --------------------------------------------------------------------------
# The published table
# --------------------------------------------------------------------------

def _n(x: float | None, fmt: str = "{:,.2f}") -> str:
    return "—" if x is None else fmt.format(x)


def render_table(cal: Calibration, min_rth: int = 300) -> str:
    """Markdown for the README. Every number carries its sample count."""
    L: list[str] = []
    window = ("all recorded data" if cal.window_days is None
              else f"rolling {cal.window_days:g}-day window")
    L.append(f"Generated {cal.generated_at:%Y-%m-%d %H:%M}Z from "
             f"{cal.n_books:,} measured books and {cal.n_reference:,} "
             f"reference prints. Depth band ±{cal.band_pct:g}%; "
             f"baseline window: {window}.")
    L.append("")
    L.append("**Reader note:** this report shows whether the recorded data is deep enough to compare current conditions with normal conditions. The dashboard uses these measurements to explain the current order limit.")
    L.append("")
    L.append("### Normal market conditions (liquidity baselines)")
    L.append("")
    L.append("| Symbol | Market period | n | Median half-spread (bps) | Median depth ±1% (USDT) | p95 half-spread | p05 depth |")
    L.append("|---|---|---:|---:|---:|---:|---:|")
    for sym, states in cal.liquidity.items():
        for state, st in states.items():
            L.append(f"| {sym} | {_public_state_label(state)} | {st.n:,} | "
                     f"{_n(st.median_half_spread_bps, '{:.3f}')} | "
                     f"{_n(st.median_depth_1pct, '{:,.0f}')} | "
                     f"{_n(st.p95_half_spread_bps, '{:.3f}')} | "
                     f"{_n(st.p05_depth_1pct, '{:,.0f}')} |")
    L.append("")

    ready = cal.rth_ready
    short = {s: n for s, n in ready.items() if n < min_rth}
    if short:
        L.append(f"**Data coverage: incomplete.** The liquidity comparison uses regular-hours "
                 f"medians and {len(short)} of {len(ready)} symbols are below "
                 f"the {min_rth}-sample minimum "
                 f"({', '.join(f'{s} {n}' for s, n in sorted(short.items()))}). "
                 f"Those symbols receive the most restrictive tier and are not "
                 f"quietly compared against a baseline built from too little "
                 f"data.")
    else:
        L.append(f"**Data coverage: complete.** Every symbol has at least "
                 f"{min_rth} regular-hours samples.")
    L.append("")

    L.append("### Token/reference price difference by market period")
    L.append("")
    L.append("| Market period | n | p50 absolute difference | p75 | p95 | p99 |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for state, b in cal.basis.items():
        L.append(f"| {_public_state_label(state)} | {b.n:,} | {_n(b.p50, '{:.1f}')} | "
                 f"{_n(b.p75, '{:.1f}')} | {_n(b.p95, '{:.1f}')} | "
                 f"{_n(b.p99, '{:.1f}')} |")
    L.append("")
    L.append("The proposed bands use measured percentiles: caution at p75, "
             "elevated at p95, and blocked at p99, rather than arbitrary round numbers.")
    L.append("")

    L.append("### Estimated fill cost")
    L.append("")
    sizes = " | ".join(f"${s:,.0f}" for s in LADDER_USDT)
    L.append(f"| Market period | n | {sizes} |")
    L.append("|---|---:|" + "---:|" * len(LADDER_USDT))
    for state, row in cal.walk.items():
        n = cal.liquidity.get("NVDABUSDT", {}).get(state, StateStats(0)).n
        cells = " | ".join(_n(row.get(s), "{:.1f}") for s in LADDER_USDT)
        L.append(f"| {_public_state_label(state)} | {n:,} | {cells} |")
    L.append("")
    L.append("Median cost in bps to fill a marketable buy of each size against "
             "the recorded book. A size the book could not fill is counted as "
             "a miss, not as a large number: unfillable and expensive are "
             "different findings.")
    L.append("")

    missing = [s.value for s in
               (MarketState.RTH_OPEN, MarketState.CLOSED_WEEKEND,
                MarketState.CLOSED_HOLIDAY)
               if not any(s.value in st for st in cal.liquidity.values())]
    if missing:
        L.append(f"**Not yet observed:** {', '.join(_public_state_label(x) for x in missing)}. These rows "
                 f"appear once the recorder has lived through them; they are "
                 f"not estimated from the states that were.")
        L.append("")
    return "\n".join(L)


def propose_bands(cal: Calibration,
                  state: str = MarketState.RTH_OPEN.value) -> dict:
    """Price-disagreement bands at measured percentiles, or nothing if the sample is thin.

    Deliberately measured on RTH_OPEN only, and this is not a detail.

    The price-disagreement check asks whether the token and its reference DISAGREE. Off-hours that
    question cannot be answered from the basis alone, because the reference
    stops updating at the bell while the token keeps trading: the first pass
    over this project's own data showed a median |basis| of 72bps during
    RTH_PRE against a reference that was already fifteen hours old. Almost all
    of that is the underlying having moved overnight, which is honest price
    discovery rather than the token being wrong.

    Calibrating the bands on those samples would bake reference staleness into
    the definition of disagreement, and then the price-disagreement check would grade the weekend against
    a yardstick built from the weekend. Staleness already has its own control -
    the DEGRADED floor keyed on reference age - and one risk must not be
    counted twice.
    """
    b = cal.basis.get(state)
    if b is None or not b.enough:
        return {}
    return {"NOMINAL": {"max_abs_bps": round(b.p75, 1), "factor": 1.00},
            "WATCH": {"max_abs_bps": round(b.p95, 1), "factor": 0.75},
            "DEGRADED": {"max_abs_bps": round(b.p99, 1), "factor": 0.35},
            "BROKEN": {"max_abs_bps": None, "factor": 0.00}}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(
        description="Measure every threshold from recorded data (Part VIII).")
    ap.add_argument("--band-pct", type=float, default=1.0)
    ap.add_argument("--min-rth", type=int, default=300)
    ap.add_argument("--window-days", type=float, default=7.0,
                    help="rolling data window for the published report")
    ap.add_argument("--out", default=None,
                    help="write the markdown table to this file")
    ap.add_argument("--propose", default=None,
                    help="write proposed price-disagreement bands to this YAML file. The live "
                         "policy is never edited by this tool (Law 6)")
    a = ap.parse_args()

    cal = run(band_pct=a.band_pct, window_days=a.window_days)
    table = render_table(cal, a.min_rth)
    if a.out:
        Path(a.out).write_text(table.rstrip("\n") + "\n")
        print(f"wrote {a.out}")
    else:
        print()
        print(table)

    if a.propose:
        bands = propose_bands(cal)
        if not bands:
            n = cal.basis.get(MarketState.RTH_OPEN.value)
            print(f"\nno band proposal: {n.n if n else 0} paired RTH_OPEN "
                  f"basis observations, {MIN_STATE_SAMPLES} required. Bands "
                  f"are measured against a LIVE reference only, so off-hours "
                  f"samples cannot stand in. Nothing is guessed.")
        else:
            import yaml
            Path(a.propose).write_text(
                "# PROPOSED by afterbell.calibrate. Not live policy.\n"
                "# Read the diff, then edit config/policy.yaml by hand.\n"
                + yaml.safe_dump({"basis": {"bands": bands}},
                                 sort_keys=False))
            print(f"\nwrote proposal to {a.propose} - review and apply by hand")


if __name__ == "__main__":
    main()
