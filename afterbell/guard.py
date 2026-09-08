"""The guard: seven protections, one sizing function, no override.

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

The operator freeze runs ahead of all seven protections. It is the only control
here that is not a measurement: a file exists or it does not, and while it does
this module returns BLOCK without consulting the market at all.
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
    Book, BookProblem, Side, basis_bps, depth_within,
    half_spread_bps, walk_cost_bps,
)
from afterbell.positions import (
    PositionSnapshot, PositionSnapshotError, load_public_key, verify_snapshot,
)
from afterbell.policy import Policy
from afterbell.resolver import ContractCheck, Resolution


# The plain-language name of each check, in the order they are applied. The
# guard works in short ids; every surface that shows a result to a person shows
# these instead, and they are defined once here so the two cannot drift apart.
CHECK_NAMES = {
    "P1": "Market timing",
    "P2": "Liquidity",
    "P3": "Price agreement",
    "P4": "Corporate actions",
    "P5": "Instrument identity",
    "P6": "Contract address",
    "P7": "Account exposure",
}


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
    # Receipts distinguish an actual requested action from the periodic,
    # read-only evaluation that powers the public guard-status panel.
    evaluation_source: str = "external_request"

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
    # P4/P6 are source-gated. Direct test/rehearsal contexts may explicitly
    # provide their own status; the live engine sets these from public checks.
    corporate_action_checked: bool = True
    # A current venue status is not the same thing as a future-action query.
    # Direct contexts default to the old, fully-specified test contract; the
    # live engine sets this false when the Alpaca lookahead is not configured.
    corporate_action_lookahead_checked: bool = True
    corporate_action_source: str | None = None
    corporate_action_note: str | None = None

    # D5: signed account state supplied by the supported client.  There is no
    # live position feed in AFTERBELL.
    position_snapshot: PositionSnapshot | None = None

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
    # The checksum identifies the exact policy bytes; this status records
    # whether those bytes have passed the human calibration review required
    # before an actionable authorization may be signed.
    policy_status: str = "UNKNOWN"

    @property
    def gate_map(self) -> dict[str, str]:
        return {g.name: g.verdict.value for g in self.gates}


def _bands_by_width(bands: dict[str, dict]) -> list[tuple[str, dict]]:
    """Basis bands narrowest first, with the open-ended band last.

    `max_abs_bps: null` means "everything wider than the rest", so it is the
    tail of the ladder wherever it happens to sit in the file.
    """
    return sorted(bands.items(),
                  key=lambda kv: (kv[1].get("max_abs_bps") is None,
                                  float(kv[1].get("max_abs_bps") or 0.0)))


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
        return GateResult("P2", Verdict.BLOCK, 0.0,
                          f"no calibrated RTH baseline for this symbol "
                          f"({n} samples, {pol.min_rth_samples} required); "
                          "the affected path is blocked until it is measured",
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

    # Ordered by the width of the band, not by the order they appear in the
    # file. Reading them in file order made the ladder silently dependent on
    # YAML key order: re-serialising the policy alphabetically puts BROKEN
    # first, whose cap is null, so it matched every basis and blocked
    # everything. A rule that changes meaning when a file is tidied is a rule
    # nobody can review.
    band_name, factor = "BROKEN", 0.0
    for name, cfg in _bands_by_width(pol.basis_bands):
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


# --------------------- Corporate-action status ---------------------

def gate_corporate_action(ctx: MarketContext, pol: Policy) -> GateResult:
    status = (ctx.exchange_status or "UNKNOWN").upper()
    # Allowlist, not blocklist: an unrecognised status is not a passing one.
    if status not in pol.tradable_statuses:
        return GateResult("P4", Verdict.BLOCK, 0.0,
                          f"pair status {status} is not a tradable status "
                          f"({', '.join(sorted(pol.tradable_statuses))})",
                          {"exchange_status": status})
    if not ctx.corporate_action_checked:
        return GateResult("P4", Verdict.BLOCK, 0.0,
                          "corporate-action status was not verified; "
                          "the affected path is halted rather than assumed clear",
                          {"exchange_status": status,
                           "corporate_action_check": "NOT_VERIFIED",
                           "note": ctx.corporate_action_note})
    if ctx.corporate_action:
        return GateResult("P4", Verdict.BLOCK, 0.0,
                          f"corporate action within "
                          f"{pol.corp_action_lookahead_h:.0f}h: "
                          f"{ctx.corporate_action}",
                          {"corporate_action": ctx.corporate_action,
                           "corporate_action_check": "VERIFIED"})
    measurements = {"exchange_status": status,
                    "corporate_action_check": "VERIFIED",
                    "corporate_action_lookahead":
                        ("VERIFIED" if ctx.corporate_action_lookahead_checked
                         else "PARTIAL")}
    if not ctx.corporate_action_lookahead_checked:
        if ctx.corporate_action_source:
            measurements["corporate_action_source"] = ctx.corporate_action_source
        if ctx.corporate_action_note:
            measurements["note"] = ctx.corporate_action_note
        return GateResult(
            "P4", Verdict.WARN, 1.0,
            f"Binance processing status {status} verified; advance corporate-action "
            "notice is not guaranteed, so this protection is partial and cannot "
            "claim a clean lookahead result",
            measurements)
    if ctx.corporate_action_note:
        measurements["note"] = ctx.corporate_action_note
    return GateResult("P4", Verdict.PASS, 1.0, f"Binance processing status {status} verified; no current "
                      "corporate-action restriction reported",
                      measurements)


# ----------------------------- P5, P6 -----------------------------

def gate_resolution(ctx: MarketContext, req: OrderRequest) -> GateResult:
    r = ctx.resolution
    if r is None or not r.resolved:
        status = r.status.value if r else "NOT_ATTEMPTED"
        return GateResult("P5", Verdict.BLOCK, 0.0,
                          f"instrument not resolved ({status}); the guard does "
                          "not act on an unresolved instrument",
                          {"resolution_status": status})
    i = r.instrument
    if i.token_symbol != req.symbol.upper():
        return GateResult("P5", Verdict.BLOCK, 0.0,
                          f"resolved token {i.token_symbol} does not match "
                          f"requested pair {req.symbol.upper()}",
                          {"resolution_status": "SYMBOL_MISMATCH",
                           "resolved_symbol": i.token_symbol,
                           "requested_symbol": req.symbol.upper()})
    return GateResult("P5", Verdict.PASS, 1.0,
                      f"{i.token_asset} resolved to {i.underlying} via "
                      f"{i.issuer}", {"resolution_status": "RESOLVED",
                                      "token_symbol": i.token_symbol})


def gate_canonical(ctx: MarketContext) -> GateResult:
    c = ctx.contract
    if c is None:
        # Binance Spot requests do not carry a contract address. The checked-in
        # registry is authoritative for the venue-internal pair; an on-chain
        # request must supply an address and is handled by the branch below.
        return GateResult("P6", Verdict.PASS, 1.0,
                          "venue-internal spot pair; canonical registry applies",
                          {"contract_check": "NOT_APPLICABLE"})
    common = {"contract_check": c.status.value, "expected": c.expected,
              "observed": c.observed, "audit_verdict": c.audit_verdict,
              "audit_status": c.audit_status,
              "audit_supported": c.audit_supported,
              "audit_passed": c.audit_passed}
    if not c.canonical:
        detail = f"contract {c.status.value.lower().replace('_', ' ')}"
        if c.audit_verdict:
            detail += (f"; token audit reported '{c.audit_verdict}' and the guard "
                       "blocks it regardless - either check alone is insufficient")
        return GateResult("P6", Verdict.BLOCK, 0.0, detail, common)
    if c.audit_passed is False:
        return GateResult("P6", Verdict.BLOCK, 0.0,
                          "canonical contract matched, but the token audit "
                          "reported an unsafe result", common)
    if c.audit_supported is False:
        return GateResult("P6", Verdict.PASS, 1.0,
                          "canonical contract matched; token audit does not "
                          "support bStocks, so P6 is explicitly registry-only",
                          common)
    if c.audit_passed is not True:
        return GateResult("P6", Verdict.BLOCK, 0.0,
                          "canonical contract matched, but no usable token-audit "
                          "result was returned", common)
    return GateResult("P6", Verdict.PASS, 1.0,
                      "contract matches the canonical registry and token audit "
                      "returned a safe result", common)


# ----------------------------- P7 -----------------------------
def _max_exposure_order(snapshot: PositionSnapshot, req: OrderRequest,
                        cap: float) -> tuple[float, float, float, float]:
    """Return max order, current gross, projected gross, and current position.
    The ceiling applies to gross net-position notionals. A reducing order may
    close an existing position even when the account is already above the
    ceiling; it may not turn that reduction into a new short/long position.
    """
    symbol = req.symbol.upper()
    current = float(snapshot.positions.get(symbol, 0.0))
    gross = snapshot.gross_exposure_usdt
    other = gross - abs(current)
    direction = 1.0 if req.side is Side.BUY else -1.0
    # Spot SELLs cannot be used to create a position from zero. A signed
    # snapshot still handles a short account conservatively if one is supplied.
    if req.side is Side.SELL and current == 0.0:
        return 0.0, gross, gross, current
    room_for_symbol = cap - other
    reducing = current * direction < 0.0
    if room_for_symbol < 0.0:
        max_order = abs(current) if reducing else 0.0
    elif reducing:
        max_order = min(abs(current), room_for_symbol + abs(current))
    else:
        max_order = max(0.0, room_for_symbol - abs(current))
    max_order = max(0.0, float(max_order))
    projected = other + abs(current + direction * req.notional)
    return max_order, gross, projected, current


def gate_exposure(ctx: MarketContext, req: OrderRequest,
                  pol: Policy) -> GateResult:
    """P7: cap new gross account exposure from signed account state."""
    snapshot = ctx.position_snapshot
    if snapshot is None:
        measurements = {
            "exposure_check": ("REQUIRED_BUT_MISSING"
                               if pol.exposure_requires_snapshot
                               else "NOT_REQUIRED"),
            "max_gross_usdt": pol.exposure_max_gross_usdt,
        }
        if pol.exposure_requires_snapshot:
            return GateResult(
                "P7", Verdict.BLOCK, 0.0,
                "no signed position snapshot was supplied; aggregate exposure "
                "cannot be measured and new exposure is refused",
                measurements)
        return GateResult(
            "P7", Verdict.PASS, 1.0,
            "no signed position snapshot supplied; P7 is not required by the "
            "current read-only policy",
            measurements)
    try:
        public_key = load_public_key(pol.exposure_position_public_key)
        age_s = verify_snapshot(
            snapshot, public_key, now=ctx.clock.ts,
            max_age_s=pol.exposure_snapshot_max_age_s)
    except PositionSnapshotError as exc:
        return GateResult(
            "P7", Verdict.BLOCK, 0.0,
            f"position snapshot refused: {exc}",
            {"exposure_check": "UNVERIFIED",
             "max_gross_usdt": pol.exposure_max_gross_usdt})
    max_order, gross, projected, current = _max_exposure_order(
        snapshot, req, pol.exposure_max_gross_usdt)
    factor = min(1.0, max_order / pol.base_notional)
    measurements = {
        "exposure_check": "VERIFIED",
        "snapshot_digest": snapshot.digest,
        "snapshot_source": snapshot.source,
        "snapshot_age_s": age_s,
        "gross_exposure_usdt": gross,
        "max_gross_usdt": pol.exposure_max_gross_usdt,
        "symbol_position_usdt": current,
        "requested_projected_gross_usdt": projected,
        "max_order_usdt": max_order,
    }
    if max_order <= 0.0:
        return GateResult(
            "P7", Verdict.BLOCK, 0.0,
            f"gross exposure {gross:,.2f} USDT leaves no room for this "
            f"{req.side.value} {req.symbol} request under the "
            f"{pol.exposure_max_gross_usdt:,.2f} USDT account ceiling",
            measurements)
    verdict = Verdict.PASS if factor >= 1.0 else Verdict.REDUCE
    detail = (
        f"gross exposure {gross:,.2f} USDT; {req.side.value} {req.symbol} "
        f"permits up to {max_order:,.2f} USDT under the "
        f"{pol.exposure_max_gross_usdt:,.2f} USDT account ceiling")
    return GateResult("P7", verdict, factor, detail, measurements)


# ----------------------------- the sizing function -----------------------------

def evaluate(req: OrderRequest, ctx: MarketContext, pol: Policy) -> Decision:
    """One function, no override (Law 7).

    Factors combine by min(), never by product: multiplying them would invent a
    precision the measurements do not have, and would let three merely-cautious
    signals compound into a block that no single measurement supports.
    """
    if req.notional <= 0:
        raise ValueError("requested notional must be positive")

    # The operator freeze is checked before anything else, and deliberately
    # before the measurements are even read. A control that runs first cannot
    # be argued past by any input, because no input has been consulted yet.
    if pol.freeze_active():
        frozen = GateResult(
            "OPERATOR_FREEZE", Verdict.BLOCK, 0.0,
            f"operator freeze engaged; {pol.kill_file} is present. No "
            "authorization is issued while it exists",
            {"operator_freeze": True, "kill_file": str(pol.kill_file)})
        return Decision(
            Verdict.BLOCK, 0.0, req.notional, "OPERATOR_FREEZE", [frozen],
            _rationale(Verdict.BLOCK, 0.0, req, ctx, [frozen]), ctx,
            pol.sha256, pol.status)

    gates = [
        gate_clock(ctx, pol),
        gate_liquidity(ctx, req, pol),
        gate_basis(ctx, pol),
        gate_corporate_action(ctx, pol),
        gate_resolution(ctx, req),
        gate_canonical(ctx),
        gate_exposure(ctx, req, pol),
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
                        ctx, pol.sha256, pol.status)

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
                    pol.sha256, pol.status)


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
        "evaluation_source": req.evaluation_source,
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
        "policy_status": d.policy_status,
        "registry_sha256": registry_sha256(),
        "rationale": d.rationale,
        "corporate_action_note": ctx.corporate_action_note,
        "corporate_action_source": ctx.corporate_action_source,
        "corporate_action_lookahead":
            ("VERIFIED" if ctx.corporate_action_lookahead_checked
             else "PARTIAL"),
    }
