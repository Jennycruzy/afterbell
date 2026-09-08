"""Who is on the other side of an off-hours trade?

The project's thesis is that a token keeps trading while its reference market
is shut. The natural follow-up is who it trades against, and whether that
changes when the underlying goes dark. If off-hours flow is measurably more
automated, one sentence reframes the whole project: the counterparty on the
other side of your weekend trade is another agent.

If it is not more automated, that is also a finding, and it is reported the
same way.

**What this does not use.** bStocks trade on a centralised order book, so
on-chain wallet tracking cannot see this flow at all. Everything here is
computed from the trade prints the recorder already stores.

**The sampling limit, stated first because it bounds every number below.** Before
2026-09-05 14:43 UTC, the recorder polled the last 50 trades once a minute. In a
quiet minute that was the whole tape and then some — the median batch spanned
longer than the cycle that fetched it, so consecutive batches overlapped and
nothing was missed. In a busy minute more than 50 trades happened and the rest
were never seen. Trade ids are consecutive per symbol, so the size of what was
missed is knowable exactly: the gap between the highest id of one batch and the
lowest of the next. The recorder now fetches up to 1000 trades per cycle.

That historical truncation matters because the trades lost in those runs were
precisely the ones in bursts, which is the signal automation would show up in.
The burst and inter-arrival figures are computed **only over windows where the
capture was provably complete**, and the coverage those windows represent is
published beside them. Measuring the
truncation rather than the market is the failure this module is written to
avoid; it is the same mistake as recording 20 depth levels and reporting the
ladder's end as the market's depth.

**The limit was ours, not Binance's.** `TRADE_LIMIT` was 50 until 2026-09-05
14:43 UTC, when it was raised to 1000 after measuring that `/api/v3/trades`
costs the same weight at any limit up to 1000. Coverage below therefore spans
two regimes and the table says which: records before that point captured 33.5%
to 77.9% of prints, and records after it capture the whole tape with overlap.
The share is computed from trade ids rather than assumed, so it stays correct
across the change without anyone having to remember it happened.

**The second trap, found the same way.** A first pass reported 45-75% of trades
arriving within 200ms of the previous one, which would be a startling amount of
automation. 36.6% of those gaps were exactly **0ms**: one aggressive order
sweeping several resting orders prints once per maker it consumes. That is one
arrival, not a burst, and counting it as several measures the order book's
shape rather than the counterparty's behaviour. Prints sharing a timestamp are
therefore collapsed into a single **arrival event**, and how many prints each
event consumed is reported separately as sweep depth, because that is a real
and separate finding.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from afterbell.clock import evaluate as clock_at

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

BATCH_LIMIT = 50           # historical pre-fix request; recorder now uses 1000
BURST_MS = 200             # "multiple fills inside 200ms"
ROUND_NOTIONALS = (10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0)

# The recorder and clock use compact enum names internally. Reports are read by
# people, so keep those implementation labels out of the published analysis.
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


@dataclass(frozen=True)
class Trade:
    symbol: str
    id: int
    ts_ms: int
    price: float
    qty: float
    quote_qty: float
    buyer_is_maker: bool

    @property
    def when(self) -> datetime:
        return datetime.fromtimestamp(self.ts_ms / 1000.0, tz=timezone.utc)


@dataclass
class Coverage:
    """How much of the real tape was actually seen."""
    captured: int = 0          # unique trades recorded
    span: int = 0              # trades that occurred, from the id range
    complete_windows: int = 0  # consecutive batches with no gap between them
    windows: int = 0

    @property
    def share(self) -> float | None:
        return None if not self.span else self.captured / self.span

    @property
    def complete_share(self) -> float | None:
        if not self.windows:
            return None
        return self.complete_windows / self.windows


@dataclass
class StateMetrics:
    state: str
    trades: int = 0             # prints
    events: int = 0             # arrivals, after same-instant prints collapse
    timed_pairs: int = 0        # adjacent events with nothing missed between
    swept_events: int = 0       # arrivals that consumed more than one maker
    prints_in_events: int = 0
    seen_ids: int = 0           # prints observed in this state
    span_ids: int = 0           # prints that occurred in it, from the id range
    gaps_ms: list[float] = field(default_factory=list)
    quote_qtys: list[float] = field(default_factory=list)
    hourly_volume: dict[int, float] = field(default_factory=lambda: defaultdict(float))
    bursts: int = 0
    coverage: Coverage = field(default_factory=Coverage)

    @property
    def state_coverage(self) -> float | None:
        """Share of this state's prints that were actually recorded.

        Coverage is not uniform across states — a busy session truncates a
        fixed-size poll harder than a quiet weekend does — so this is the
        number that decides whether two states may be compared at all.
        """
        if not self.span_ids:
            return None
        return self.seen_ids / self.span_ids

    @property
    def mean_sweep(self) -> float | None:
        """Prints per arrival: how many resting orders a taker eats at once."""
        if not self.events:
            return None
        return self.prints_in_events / self.events

    @property
    def sweep_share(self) -> float | None:
        if not self.events:
            return None
        return self.swept_events / self.events

    # -- the four measures ------------------------------------------------

    @property
    def interarrival_cv(self) -> float | None:
        """Coefficient of variation of the gaps between consecutive trades.

        Poisson-ish human flow sits near 1.0. A periodic bot drives it toward
        0. Bursty, scheduled flow pushes it above 1.
        """
        if len(self.gaps_ms) < 30:
            return None
        mean = statistics.fmean(self.gaps_ms)
        if mean <= 0:
            return None
        return statistics.pstdev(self.gaps_ms) / mean

    @property
    def burst_rate(self) -> float | None:
        """Share of arrivals landing within 200ms of the previous arrival.

        Arrivals, not prints: a single order sweeping five makers is one
        arrival here, not four 0ms bursts.
        """
        if len(self.gaps_ms) < 30:
            return None
        return self.bursts / len(self.gaps_ms)

    @property
    def round_notional_share(self) -> float | None:
        """Share of trades struck at a round quote size.

        A human types 100. A market maker quoting continuously does not.
        """
        if len(self.quote_qtys) < 30:
            return None
        hits = sum(1 for q in self.quote_qtys
                   if any(abs(q - r) < 0.005 * r for r in ROUND_NOTIONALS))
        return hits / len(self.quote_qtys)

    @property
    def repeated_size_share(self) -> float | None:
        """Share of trades whose size is not unique to them.

        Quantised sizes repeat; discretionary ones mostly do not.
        """
        if len(self.quote_qtys) < 30:
            return None
        counts: dict[float, int] = defaultdict(int)
        for q in self.quote_qtys:
            counts[round(q, 2)] += 1
        return sum(c for c in counts.values() if c > 1) / len(self.quote_qtys)

def iter_raw(raw_dir: Path | None = None) -> Iterator[dict[str, Any]]:
    for path in sorted((raw_dir or RAW).glob("*/token.jsonl")):
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def collect(raw_dir: Path | None = None
            ) -> tuple[dict[str, list[Trade]], dict[str, Coverage]]:
    """Deduplicate the overlapping batches and measure what was missed.

    Batches overlap in quiet minutes, so the same trade arrives many times and
    is counted once. Between two batches the id gap says exactly how many
    trades happened; when that gap exceeds the batch we fetched, the difference
    was never seen and is recorded as such rather than ignored.
    """
    seen: dict[str, dict[int, Trade]] = defaultdict(dict)
    coverage: dict[str, Coverage] = defaultdict(Coverage)
    last_max: dict[str, int] = {}

    for rec in iter_raw(raw_dir):
        trades = rec.get("trades")
        if not trades:
            continue
        symbol = rec.get("symbol")
        if not symbol:
            continue
        ids = []
        for t in trades:
            try:
                tid = int(t["id"])
                trade = Trade(symbol, tid, int(t["time"]), float(t["price"]),
                              float(t["qty"]), float(t["quoteQty"]),
                              bool(t["isBuyerMaker"]))
            except (KeyError, TypeError, ValueError):
                continue
            ids.append(tid)
            seen[symbol].setdefault(tid, trade)
        if not ids:
            continue

        cov = coverage[symbol]
        low, high = min(ids), max(ids)
        previous = last_max.get(symbol)
        if previous is not None and high >= previous:
            cov.windows += 1
            # No hole: this batch reaches back to at least the last id we held.
            if low <= previous + 1:
                cov.complete_windows += 1
        last_max[symbol] = max(high, previous or high)

    for symbol, trades in seen.items():
        cov = coverage[symbol]
        cov.captured = len(trades)
        ids = trades.keys()
        cov.span = max(ids) - min(ids) + 1 if trades else 0
    return {s: sorted(t.values(), key=lambda x: (x.ts_ms, x.id))
            for s, t in seen.items()}, dict(coverage)


def diurnal_flatness(trades: list[Trade]) -> float | None:
    """Quietest hour's volume over the busiest hour's, across the whole day.

    Computed per symbol rather than per market state, because a state cannot
    answer the question: the open session covers 6.5 hours of the clock by
    definition, so its "quietest hour" is an artefact of the session's edges
    rather than a fact about who is trading. The question is whether volume
    dips at 4am, and only the full day can answer it.
    """
    hourly: dict[int, float] = defaultdict(float)
    for t in trades:
        hourly[t.when.hour] += t.quote_qty
    if len(hourly) < 24:
        return None
    vols = list(hourly.values())
    return min(vols) / max(vols)


def arrivals(trades: list[Trade]) -> list[list[Trade]]:
    """Group prints into arrival events.

    Prints sharing a timestamp came from one aggressive order consuming
    several resting orders. That is one arrival. Treating it as several was the
    error that made the first pass report 45-75% "bursts".
    """
    events: list[list[Trade]] = []
    for t in trades:
        if events and events[-1][0].ts_ms == t.ts_ms:
            events[-1].append(t)
        else:
            events.append([t])
    return events


def measure(trades: list[Trade], coverage: Coverage) -> dict[str, StateMetrics]:
    """Metrics per market state, with timing measured only where complete.

    A gap between two arrivals is only meaningful if no trade was lost between
    them. Consecutive ids across the whole span of both events prove that;
    anything else is skipped, so a burst truncated by the poll limit cannot
    masquerade as a quiet stretch.
    """
    out: dict[str, StateMetrics] = {}
    events = arrivals(trades)
    previous: list[Trade] | None = None

    for event in events:
        head = event[0]
        state = clock_at(head.when).state.value
        m = out.setdefault(state, StateMetrics(state))
        m.trades += len(event)
        m.events += 1
        m.prints_in_events += len(event)
        if len(event) > 1:
            m.swept_events += 1
        for t in event:
            m.quote_qtys.append(t.quote_qty)
            m.hourly_volume[t.when.hour] += t.quote_qty

        if previous is not None:
            # Ids are consecutive per symbol, so the distance between two
            # observed prints is exactly how many occurred between them.
            step = head.id - previous[-1].id
            if step > 0:
                m.span_ids += step
                m.seen_ids += min(len(event), step)

        if previous is not None and head.id == previous[-1].id + 1:
            # Provably adjacent arrivals: nothing was missed between them.
            gap = float(head.ts_ms - previous[0].ts_ms)
            if gap > 0:
                m.timed_pairs += 1
                m.gaps_ms.append(gap)
                if gap <= BURST_MS:
                    m.bursts += 1
        previous = event

    for m in out.values():
        m.coverage = coverage
    return out


def _fmt(value: float | None, spec: str = ".2f", suffix: str = "") -> str:
    return "–" if value is None else f"{value:{spec}}{suffix}"


@dataclass
class StateAggregate:
    """One market state, averaged across the symbols that have samples."""
    state: str
    arrivals: int
    interarrival_cv: float | None
    burst_rate: float | None
    round_share: float | None
    repeated_share: float | None
    mean_sweep: float | None


def aggregate(by_symbol: dict[str, dict[str, StateMetrics]]
              ) -> dict[str, StateAggregate]:
    """Average each measure across symbols, so states can be compared.

    An unweighted mean across symbols, not a pooled one: pooling would let the
    two heavily-traded symbols speak for the other three.
    """
    buckets: dict[str, list[StateMetrics]] = defaultdict(list)
    for states in by_symbol.values():
        for state, m in states.items():
            buckets[state].append(m)

    def mean(values: list[float | None]) -> float | None:
        present = [v for v in values if v is not None]
        return statistics.fmean(present) if present else None

    return {
        state: StateAggregate(
            state=state,
            arrivals=sum(m.events for m in ms),
            interarrival_cv=mean([m.interarrival_cv for m in ms]),
            burst_rate=mean([m.burst_rate for m in ms]),
            round_share=mean([m.round_notional_share for m in ms]),
            repeated_share=mean([m.repeated_size_share for m in ms]),
            mean_sweep=mean([m.mean_sweep for m in ms]),
        )
        for state, ms in buckets.items()
    }


# Two states may only be compared when both were captured nearly completely.
# Below this, the comparison measures the poll limit rather than the market.
MIN_COMPARABLE_COVERAGE = 0.95


def finding(agg: dict[str, StateAggregate],
            by_symbol: dict[str, dict[str, StateMetrics]]) -> list[str]:
    """State what the numbers say, or refuse to state anything.

    The question worth testing was whether off-hours flow is more automated.
    Answering it means comparing two market periods, and that is only legitimate
    when both were sampled the same way. They were not, for most of the
    recorded period, so this refuses rather than reporting a direction it
    cannot support — the same rule the baselines follow when a symbol has too
    few samples.
    """
    rth, wknd = agg.get("RTH_OPEN"), agg.get("CLOSED_WEEKEND")
    if not rth or not wknd:
        return ["### What the numbers say", "",
                "Not enough market states observed yet to compare."]

    def coverage(state: str) -> float | None:
        seen = sum(m.seen_ids for s in by_symbol.values()
                   if (m := s.get(state)))
        span = sum(m.span_ids for s in by_symbol.values()
                   if (m := s.get(state)))
        return seen / span if span else None

    cov_rth, cov_wknd = coverage("RTH_OPEN"), coverage("CLOSED_WEEKEND")
    worst = min(c for c in (cov_rth, cov_wknd) if c is not None)

    if worst < MIN_COMPARABLE_COVERAGE:
        return [
            "### What the numbers say",
            "",
            "**Not enough of the tape was captured to answer the question, and "
            "the honest result is to say so rather than to publish a "
            "direction.**",
            "",
            f"The question worth testing was whether the counterparty on the "
            f"other side of a weekend trade is more automated. Answering it "
            f"means comparing two market periods, and that is only legitimate "
            f"if both were sampled the same way. They were not: regular hours "
            f"were captured at {100 * (cov_rth or 0):.1f}% and the weekend at "
            f"{100 * (cov_wknd or 0):.1f}%, because a historical fixed 50-print poll "
            f"truncated a busy session far harder than a quiet weekend.",
            "",
            "That difference is not a detail. Measured both ways, the answer "
            "reverses. Counting every consecutive-id pair over-samples busy "
            "minutes, whose prints are the ones that survive truncation, and "
            "makes regular hours look burstier than the weekend. Restricting "
            "to minutes captured without a hole over-samples quiet minutes "
            "instead, and makes the weekend look burstier than regular hours. "
            "Both estimators are biased, in opposite directions, and both bite "
            "hardest on the busiest state. A finding that flips depending on "
            "which of two flawed estimators is chosen is not a finding.",
            "",
            "The cause was a recorder limit, not a market: it fetched only "
            "50 prints per minute. That limit was raised to 1000 on 2026-09-05 "
            "at 14:43 UTC, and "
            "since then every cycle has been captured with no holes at all. "
            "Once a full session and a full closure have been recorded that "
            "way, this comparison becomes answerable and the answer will "
            "appear here.",
            "",
            "The per-state tables below stand on their own — they describe "
            "what was seen, which is a fact — but no comparison **between** "
            "states should be read off them until coverage is even.",
        ]

    more_bursty = (wknd.burst_rate or 0) > (rth.burst_rate or 0)
    rounder = sum(
        1 for states in by_symbol.values()
        if (states.get("RTH_OPEN") and states.get("CLOSED_WEEKEND")
            and (states["CLOSED_WEEKEND"].round_notional_share or 0)
            > (states["RTH_OPEN"].round_notional_share or 0)))
    total = sum(1 for s in by_symbol.values()
                if s.get("RTH_OPEN") and s.get("CLOSED_WEEKEND"))
    return [
        "### What the numbers say",
        "",
        f"Both states were captured at {100 * worst:.1f}% or better, so they "
        f"can be compared.",
        "",
        f"Weekend arrivals are {'more' if more_bursty else 'less'} clustered "
        f"than regular-hours ones: {100 * (wknd.burst_rate or 0):.1f}% of "
        f"weekend arrivals land within {BURST_MS}ms of the previous one, "
        f"against {100 * (rth.burst_rate or 0):.1f}% during regular trading. "
        f"Round-number trade sizes run {100 * (rth.round_share or 0):.2f}% "
        f"during regular hours against {100 * (wknd.round_share or 0):.2f}% on "
        f"the weekend, higher off-hours in {rounder} of {total} symbols.",
        "",
        "Round sizes are the signature of somebody typing a number; a market "
        "maker quoting continuously does not deal in hundreds.",
    ]


def render(by_symbol: dict[str, dict[str, StateMetrics]],
           coverage: dict[str, Coverage],
           diurnal: dict[str, float | None]) -> str:
    lines = [
        "# Who trades when the reference market is closed?",
        "",
        "> **Short answer:** this report does not claim that weekend flow is "
        "more automated yet. The historical recorder captured regular hours "
        "and closures at different rates, so that comparison would be "
        "misleading. The recorder was corrected on 2026-09-05; one complete "
        "like-for-like session is still needed before the result is publishable.",
        "",
        "**Why it matters:** Afterbell studies whether a tokenized equity keeps "
        "a healthy market when the underlying reference market is closed, and "
        "whether the trading pattern changes outside regular hours.",
        "",
        "**What is reliable today:** the capture coverage, trade counts, and "
        "per-period measurements below. **What is not reliable yet:** a claim "
        "that one period has a more automated counterparty than another.",
        "",
        "Computed from the trade records the recorder already stores. bStocks "
        "trade on a centralised order book, so this analysis uses the public "
        "trade tape rather than wallet tracking.",
        "",
        "## How much of the tape we captured",
        "",
        "Before 2026-09-05 14:43 UTC, the recorder fetched the last 50 trades "
        "once a minute; that historical limit caused the coverage bias described "
        "below. It now fetches up to 1000 trades per cycle. Trade ids are "
        "consecutive, so the size of anything missed is knowable exactly and is "
        "reported rather than assumed away.",
        "",
        "| Symbol | Prints captured | Prints that occurred | Share of tape | "
        "Minutes fully captured | Quietest/busiest hour |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for symbol in sorted(coverage):
        c = coverage[symbol]
        lines.append(
            f"| {symbol} | {c.captured:,} | {c.span:,} | "
            f"{_fmt(None if c.share is None else 100 * c.share, '.1f', '%')} | "
            f"{_fmt(None if c.complete_share is None else 100 * c.complete_share, '.1f', '%')} | "
            f"{_fmt(diurnal.get(symbol), '.3f')} |")

    lines += [
        "",
        "In the historical pre-fix sample, the prints lost were the ones in bursts, which is exactly where "
        "automation would show. Timing figures below are therefore computed "
        "only across pairs of arrivals with consecutive ids, where nothing "
        "can have been missed between them.",
        "",
        "The quietest/busiest-hour ratio is the quietest hour's volume divided "
        "by the busiest hour's volume across the whole day. A result of 1.0 "
        "means activity is evenly spread. It is measured per symbol, not per "
        "period, because the open session covers only 6.5 hours of the clock.",
        "",
        "## Measurements by market period",
        "",
        "| Symbol | Market period | Prints | Arrivals | Timed pairs | "
        "Inter-arrival CV | Bursts <200ms | Prints per arrival | "
        "Round sizes | Repeated sizes |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for symbol in sorted(by_symbol):
        for state in sorted(by_symbol[symbol]):
            m = by_symbol[symbol][state]
            lines.append(
                f"| {symbol} | {_public_state_label(state)} | {m.trades:,} | {m.events:,} | "
                f"{m.timed_pairs:,} | {_fmt(m.interarrival_cv)} | "
                f"{_fmt(None if m.burst_rate is None else 100 * m.burst_rate, '.1f', '%')} | "
                f"{_fmt(m.mean_sweep)} | "
                f"{_fmt(None if m.round_notional_share is None else 100 * m.round_notional_share, '.1f', '%')} | "
                f"{_fmt(None if m.repeated_size_share is None else 100 * m.repeated_size_share, '.1f', '%')} |")

    lines += ["", *finding(aggregate(by_symbol), by_symbol), ""]

    lines += [
        "",
        "**Reading the columns.** An *arrival* is one aggressive order; the "
        "prints it produced against separate resting orders are collapsed into "
        "it, and `prints per arrival` reports how many makers it consumed. "
        "Inter-arrival CV near 1.0 is Poisson-ish arrival, the shape human "
        "order flow takes; below 1.0 is more regular than chance, above it is "
        "burstier. A dash means too few samples to say anything, which is "
        "reported rather than filled in.",
        "",
        "Regenerate with `.venv/bin/python -m afterbell.counterparty`.",
    ]
    return "\n".join(lines)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Counterparty composition")
    ap.add_argument("--raw", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    trades, coverage = collect(Path(a.raw) if a.raw else None)
    by_symbol = {s: measure(t, coverage[s]) for s, t in trades.items()}
    diurnal = {s: diurnal_flatness(t) for s, t in trades.items()}
    text = render(by_symbol, coverage, diurnal)
    if a.out:
        Path(a.out).write_text(text + "\n")
        print(f"wrote {a.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
