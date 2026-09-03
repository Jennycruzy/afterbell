"""The guard: six protections, one sizing function, no override.

Law 5: nothing in this module asks a language model anything. Every number is
computed here from measured inputs. The model narrates the result afterwards
and cannot change it.

Law 6: every threshold is read from the signed policy. There is no argument, no
keyword and no request field that raises a limit, because no such path exists
to be discovered.

Law 7: the guard's entire output space is PASS, WARN, REDUCE, BLOCK. It never
originates an order and never returns more than was asked for. Its action space
is provably risk-reducing, which is what makes it safe to grant autonomy to.

Law 9: during regular hours with a live reference, tight spreads and normal
depth, this passes cleanly and stays out of the way.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from afterbell.baselines import Baseline
from afterbell.clock import ClockReading, MarketState, format_age
from afterbell.instruments import registry_sha256
from afterbell.measure import (
    Book, BookProblem, Side, WalkResult, basis_bps, depth_within,
    half_spread_bps, walk_cost_bps,
)
from afterbell.policy import Policy
from afterbell.resolver import ContractCheck, Resolution


class Verdict(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    REDUCE = "REDUCE"
    BLOCK = "BLOCK"


_SEVERITY = {Verdict.PASS: 0, Verdict.WARN: 1, Verdict.REDUCE: 2, Verdict.BLOCK: 3}


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Side
    notional: float
    query: str = ""
    observed_contract: str | None = None
    audit_verdict: str | None = None

    def at(self, notional: float) -> "OrderRequest":
        """The same request, resized to what the guard permitted.

        This is the last line of the adoption snippet, so it enforces the one
        property that snippet depends on: the guard never returns more than was
        asked for, and a caller cannot use this to ask for more than it did
        (Law 7). Resizing upward raises rather than quietly obliging.
        """
        if notional <= 0:
            raise ValueError("permitted notional must be positive; a blocked "
                             "decision has no order to place")
        if notional > self.notional:
            raise ValueError(
                f"cannot resize {self.symbol} upward from {self.notional:,.2f} "
                f"to {notional:,.2f}; the guard never permits more than was "
                f"requested and this path must not become the exception")
        return replace(self, notional=notional)


@dataclass
class MarketContext:
    """Everything measured, assembled by the caller before the guard runs."""
    clock: ClockReading
    book: Book | None = None
    baseline: Baseline | None = None
    reference_price: float | None = None
    reference_ts: datetime | None = None
    exchange_status: str | None = None
    corporate_action: str | None = None
    resolution: Resolution | None = None
    contract: ContractCheck | None = None
    # Why the reference is missing, when it is. A blank reason on a blocked
    # receipt is uninvestigable after the fact.
    reference_note: str | None = None

    @property
    def reference_age_s(self) -> float | None:
        if self.reference_ts is None:
            return None
        return (self.clock.ts - self.reference_ts.astimezone(timezone.utc)
                ).total_seconds()


@dataclass
class GateResult:
    name: str
    verdict: Verdict
    factor: float           # 1.0 = unconstrained; 0.0 = hard block
    detail: str
    measurements: dict[str, Any] = field(default_factory=dict)

    @property
    def is_hard_block(self) -> bool:
        return self.verdict is Verdict.BLOCK


@dataclass
class Decision:
    verdict: Verdict
    allowed_notional: float
    requested_notional: float
    binding_constraint: str
    gates: list[GateResult]
    rationale: str
    context: MarketContext
    policy_sha256: str

    @property
    def gate_map(self) -> dict[str, str]:
        return {g.name: g.verdict.value for g in self.gates}


def _ladder(rows: list[dict], key: str, value: float) -> float:
    """First row whose bound the value falls under. A null bound is the tail."""
    for row in rows:
        bound = row[key]
        if bound is None or value <= float(bound):
            return float(row["factor"])
    return float(rows[-1]["factor"])


# ----------------------------- P1 -----------------------------

def gate_clock(ctx: MarketContext, pol: Policy) -> GateResult:
    c = ctx.clock
    f = pol.clock_factors

    if c.state in (MarketState.HALTED, MarketState.UNKNOWN):
        return GateResult("P1", Verdict.BLOCK, 0.0,
                          f"reference market state is {c.state.value}; the most "
                          "restrictive treatment applies, never the loosest",
                          {"market_state": c.state.value})

    backward = (_ladder(pol.backward_gap, "max_age_s", ctx.reference_age_s)
                if ctx.reference_age_s is not None else 1.0)
    forward = _ladder(pol.forward_gap, "max_gap_s", c.seconds_to_next_open)

    if c.state is MarketState.RTH_OPEN:
        # While the reference market is open a position can still be exited
        # against a live venue, so the darkness ahead does not constrain the
        # whole session - it sets the floor the intraday ramp descends to. A
        # Friday ramps toward the holiday-weekend floor; a Tuesday toward the
        # ordinary one. Flattening the entire session to the forward factor
        # would make the ramp meaningless and would size 14:00 identically to
        # 15:55.
        ramp_s = pol.ramp_start_minutes * 60.0
        to_close = c.seconds_to_close or 0.0
        floor = min(pol.ramp_floor, forward)
        if to_close > ramp_s:
            factor = f["RTH_OPEN"]
            detail = (f"regular session, {to_close/60:.0f}m to the close; "
                      "no clock constraint")
            binding = "state"
        else:
            frac = max(0.0, min(1.0, to_close / ramp_s))
            factor = floor + (f["RTH_OPEN"] - floor) * frac
            detail = (f"{to_close/60:.1f}m to the close; new exposure ramping "
                      f"down to {floor:.0%} of base")
            binding = "closing_ramp"
        state_factor = factor
    else:
        # The reference market is shut. Now the gap in both directions binds:
        # how stale the last print already is, and how long until the next one.
        state_factor = f[c.state.value]
        factor = min(state_factor, backward, forward)
        binding = min((state_factor, "state"), (backward, "reference_age"),
                      (forward, "gap_ahead"), key=lambda t: t[0])[1]
        detail = (f"reference market {c.state.value}; "
                  f"{c.hours_to_next_open:.1f}h until the next regular print")
        if c.holiday:
            detail += f" ({c.holiday})"
        elif c.extended_closure_ahead:
            detail += " (extended closure)"

    verdict = (Verdict.BLOCK if factor <= 0.0
               else Verdict.PASS if factor >= 1.0 else Verdict.REDUCE)
    return GateResult("P1", verdict, factor, detail, {
        "market_state": c.state.value,
        "seconds_to_close": c.seconds_to_close,
        "seconds_to_next_open": c.seconds_to_next_open,
        "reference_age_s": ctx.reference_age_s,
        "extended_closure_ahead": c.extended_closure_ahead,
        "state_factor": state_factor, "backward_factor": backward,
        "forward_factor": forward, "binding_ladder": binding,
    })


# ----------------------------- P2 -----------------------------

def gate_liquidity(ctx: MarketContext, req: OrderRequest,
                   pol: Policy) -> GateResult:
    if ctx.book is None:
        return GateResult("P2", Verdict.BLOCK, 0.0,
                          "no order book available; liquidity cannot be "
                          "measured and will not be assumed")

    hs = half_spread_bps(ctx.book)
    depth = depth_within(ctx.book, pol.depth_band_pct)
    if hs is None or depth is None:
        return GateResult("P2", Verdict.BLOCK, 0.0,
                          "order book could not be measured (crossed or "
                          "truncated inside the measurement band)")

    walk = walk_cost_bps(ctx.book, req.notional, req.side)
    if isinstance(walk, BookProblem):
        return GateResult("P2", Verdict.BLOCK, 0.0,
                          f"walk cost unmeasurable: {walk.value}; the visible "
                          "book cannot fill this size and the true cost is "
                          "unknown", {"half_spread_bps": hs, "depth": depth})

    m: dict[str, Any] = {
        "half_spread_bps": hs, "depth_1pct": depth,
        "walk_cost_bps": walk.cost_bps, "levels_consumed": walk.levels_consumed,
    }

    if walk.cost_bps > pol.walk_cost_cap_bps:
        return GateResult("P2", Verdict.BLOCK, 0.0,
                          f"walk cost {walk.cost_bps:.0f}bps exceeds the "
                          f"{pol.walk_cost_cap_bps:.0f}bps cap for this size",
                          m)

    bl = ctx.baseline
    if bl is None or not bl.is_calibrated:
        n = bl.n_rth if bl else 0
        return GateResult("P2", Verdict.REDUCE, pol.liquidity_tiers[-1]["factor"],
                          f"no calibrated RTH baseline for this symbol "
                          f"({n} samples, {pol.min_rth_samples} required); "
                          "the most restrictive tier applies",
                          {**m, "baseline_status": "UNCALIBRATED", "n_rth": n})

    sr = bl.spread_ratio(hs)
    lr = bl.liquidity_ratio(depth)
    m |= {"spread_ratio": sr, "liquidity_ratio": lr,
          "rth_median_half_spread_bps": bl.median_half_spread_bps,
          "rth_median_depth_1pct": bl.median_depth_1pct, "n_rth": bl.n_rth}

    for tier in pol.liquidity_tiers:
        if sr <= tier["max_spread_ratio"] and lr >= tier["min_liquidity_ratio"]:
            factor = float(tier["factor"])
            verdict = Verdict.PASS if factor >= 1.0 else Verdict.REDUCE
            return GateResult("P2", verdict, factor,
                              f"spread {sr:.1f}x its RTH median, depth "
                              f"{lr:.0%} of it", m)

    return GateResult("P2", Verdict.BLOCK, pol.liquidity_otherwise,
                      f"spread {sr:.1f}x its RTH median and depth {lr:.0%} of "
                      "it; outside every permitted tier", m)


# ----------------------------- P3 -----------------------------

def gate_basis(ctx: MarketContext, pol: Policy) -> GateResult:
    if ctx.book is None:
        return GateResult("P3", Verdict.BLOCK, 0.0,
                          "no token price available")
    if ctx.reference_price is None or ctx.reference_ts is None:
        return GateResult("P3", Verdict.BLOCK, 0.0,
                          "no reference price; a basis cannot be computed and "
                          "a missing reference is never treated as agreement")

    age = ctx.reference_age_s or 0.0
    if age > pol.max_reference_age_s:
        return GateResult("P3", Verdict.BLOCK, 0.0,
                          f"reference price is {format_age(age)} old, beyond "
                          f"the {format_age(pol.max_reference_age_s)} cap",
                          {"reference_age_s": age})

    b = basis_bps(ctx.book.mid, ctx.reference_price)
    m = {"basis_bps": b, "reference_age_s": age,
         "reference_price": ctx.reference_price, "token_price": ctx.book.mid}

    band_name, factor = "BROKEN", 0.0
    for name, cfg in pol.basis_bands.items():
        cap = cfg.get("max_abs_bps")
        if cap is None or abs(b) <= float(cap):
            band_name, factor = name, float(cfg["factor"])
            break

    # A long-stale reference cannot be called NOMINAL however close the basis
    # looks: the number it is close to is old.
    floored = False
    if age > pol.degraded_floor_reference_age_s:
        degraded = float(pol.basis_bands["DEGRADED"]["factor"])
        if factor > degraded:
            band_name, factor, floored = "DEGRADED", degraded, True

    m |= {"band": band_name, "degraded_floor_applied": floored}
    detail = (f"token {b:+.0f}bps against a reference "
              f"{format_age(age)} old [{band_name}]")
    if floored:
        detail += "; floored to DEGRADED on reference age alone"
    verdict = (Verdict.BLOCK if factor <= 0.0
               else Verdict.PASS if factor >= 1.0 else Verdict.REDUCE)
    return GateResult("P3", verdict, factor, detail, m)


# ----------------------------- P4 -----------------------------

def gate_corporate_action(ctx: MarketContext, pol: Policy) -> GateResult:
    status = (ctx.exchange_status or "UNKNOWN").upper()
    # Allowlist, not blocklist: an unrecognised status is not a passing one.
    if status not in pol.tradable_statuses:
        return GateResult("P4", Verdict.BLOCK, 0.0,
                          f"pair status {status} is not a tradable status "
                          f"({', '.join(sorted(pol.tradable_statuses))})",
                          {"exchange_status": status})
    if ctx.corporate_action:
        return GateResult("P4", Verdict.BLOCK, 0.0,
                          f"corporate action within "
                          f"{pol.corp_action_lookahead_h:.0f}h: "
                          f"{ctx.corporate_action}",
                          {"corporate_action": ctx.corporate_action})
    return GateResult("P4", Verdict.PASS, 1.0, f"pair status {status}, no "
                      "corporate action in the lookahead window",
                      {"exchange_status": status})


# ----------------------------- P5, P6 -----------------------------

def gate_resolution(ctx: MarketContext) -> GateResult:
    r = ctx.resolution
    if r is None or not r.resolved:
        status = r.status.value if r else "NOT_ATTEMPTED"
        return GateResult("P5", Verdict.BLOCK, 0.0,
                          f"instrument not resolved ({status}); the guard does "
                          "not act on an unresolved instrument",
                          {"resolution_status": status})
    i = r.instrument
    return GateResult("P5", Verdict.PASS, 1.0,
                      f"{i.token_asset} resolved to {i.underlying} via "
                      f"{i.issuer}", {"resolution_status": "RESOLVED",
                                      "token_symbol": i.token_symbol})


def gate_canonical(ctx: MarketContext) -> GateResult:
    c = ctx.contract
    if c is None:
        # Spot trading on Binance does not deliver a contract address; the
        # registry is authoritative and the pair is the canonical listing.
        return GateResult("P6", Verdict.PASS, 1.0,
                          "venue-internal spot pair; canonical registry applies",
                          {"contract_check": "NOT_APPLICABLE"})
    if c.canonical:
        return GateResult("P6", Verdict.PASS, 1.0,
                          "contract matches the canonical registry",
                          {"contract_check": c.status.value,
                           "observed": c.observed})
    detail = f"contract {c.status.value.lower().replace('_', ' ')}"
    if c.audit_verdict:
        detail += (f"; token audit reported '{c.audit_verdict}' and the guard "
                   "blocks it regardless - either check alone is insufficient")
    return GateResult("P6", Verdict.BLOCK, 0.0, detail,
                      {"contract_check": c.status.value,
                       "expected": c.expected, "observed": c.observed,
                       "audit_verdict": c.audit_verdict})


# ----------------------------- the sizing function -----------------------------

def evaluate(req: OrderRequest, ctx: MarketContext, pol: Policy) -> Decision:
    """One function, no override (Law 7).

    Factors combine by min(), never by product: multiplying them would invent a
    precision the measurements do not have, and would let three merely-cautious
    signals compound into a block that no single measurement supports.
    """
    if req.notional <= 0:
        raise ValueError("requested notional must be positive")

    gates = [
        gate_clock(ctx, pol),
        gate_liquidity(ctx, req, pol),
        gate_basis(ctx, pol),
        gate_corporate_action(ctx, pol),
        gate_resolution(ctx),
        gate_canonical(ctx),
    ]

    blocking = [g for g in gates if g.is_hard_block]
    if blocking:
        # Several protections can refuse the same order. Naming only the first
        # in list order would report a stale reference as the reason an order
        # was refused when the instrument was also unresolved and the contract
        # counterfeit, so every blocker is recorded and the rationale names
        # them all.
        binding = ",".join(g.name for g in blocking)
        return Decision(Verdict.BLOCK, 0.0, req.notional, binding, gates,
                        _rationale(Verdict.BLOCK, 0.0, req, ctx, blocking),
                        ctx, pol.sha256)

    tightest = min(gates, key=lambda g: g.factor)
    ceiling = pol.base_notional * tightest.factor
    allowed = min(req.notional, ceiling)          # never more than asked

    if allowed <= 0.0:
        verdict = Verdict.BLOCK
    elif allowed < req.notional:
        verdict = Verdict.REDUCE
    elif any(g.verdict is Verdict.WARN for g in gates):
        verdict = Verdict.WARN
    else:
        verdict = Verdict.PASS

    binding = tightest.name if allowed < req.notional else "none"
    return Decision(verdict, allowed, req.notional, binding, gates,
                    _rationale(verdict, allowed, req, ctx, [tightest]), ctx,
                    pol.sha256)


def _rationale(verdict: Verdict, allowed: float, req: OrderRequest,
               ctx: MarketContext, binding: list[GateResult]) -> str:
    """Deterministic rationale.

    This is the text of record. The language model may narrate a receipt more
    fluently for a human reader, but it never replaces this string and never
    supplies a number that is not already here (Law 5).
    """
    age = ("no reference" if ctx.reference_age_s is None
           else format_age(ctx.reference_age_s))
    head = (f"{verdict.value}: {req.side.value} {req.symbol} "
            f"{req.notional:,.0f} USDT requested")
    if verdict is Verdict.BLOCK:
        reasons = "; ".join(f"{g.name} - {g.detail}" for g in binding)
        return (f"{head}; blocked by {reasons}. "
                f"Reference market {ctx.clock.state.value}, REFERENCE_AGE {age}.")
    b = binding[0]
    if verdict is Verdict.REDUCE:
        return (f"{head}, {allowed:,.0f} permitted; bound by {b.name} - "
                f"{b.detail}. Reference market {ctx.clock.state.value}, "
                f"REFERENCE_AGE {age}.")
    return (f"{head} and permitted in full. Reference market "
            f"{ctx.clock.state.value}, REFERENCE_AGE {age}. "
            f"Tightest measurement: {b.name} - {b.detail}.")


def to_receipt(d: Decision, req: OrderRequest) -> dict[str, Any]:
    """The receipt written to the ledger. Refusals included - especially."""
    ctx = d.context
    m: dict[str, Any] = {}
    for g in d.gates:
        m |= g.measurements
    return {
        "symbol": req.symbol,
        "market_state": ctx.clock.state.value,
        "reference_age_s": ctx.reference_age_s,
        "reference_age": (None if ctx.reference_age_s is None
                          else format_age(ctx.reference_age_s)),
        "reference_price": ctx.reference_price,
        "reference_ts": (ctx.reference_ts.isoformat()
                         if ctx.reference_ts else None),
        "token_price": ctx.book.mid if ctx.book else None,
        "requested": {"side": req.side.value, "notional": req.notional},
        "gates": d.gate_map,
        "gate_detail": {g.name: g.detail for g in d.gates},
        "gate_factors": {g.name: g.factor for g in d.gates},
        "measurements": m,
        "decision": d.verdict.value,
        "allowed_notional": d.allowed_notional,
        "binding_constraint": d.binding_constraint,
        "blocking_gates": [g.name for g in d.gates if g.is_hard_block],
        "policy_sha256": d.policy_sha256,
        "registry_sha256": registry_sha256(),
        "rationale": d.rationale,
    }
