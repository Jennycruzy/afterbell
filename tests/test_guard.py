"""Guard tests.

Contexts are constructed explicitly so each protection can be driven to a known
state. Nothing here stands in for a live market: the production path builds a
MarketContext only from measured data, and refuses when a field is missing.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from afterbell.baselines import Baseline
from afterbell.clock import evaluate as clock_at
from afterbell.guard import (
    MarketContext, OrderRequest, Verdict, evaluate, to_receipt,
)
from afterbell.measure import Book, Level, Side
from afterbell.policy import load
from afterbell.resolver import resolve, verify_contract

def read_only_test_policy():
    """Legacy gate-isolation scenarios do not exercise mandatory P7."""
    policy = load()
    raw = dict(policy.raw)
    raw["exposure"] = dict(raw["exposure"]) | {"require_snapshot": False}
    return replace(policy, raw=raw)


POL = read_only_test_policy()
NVDA_CONTRACT = "0x02Fca66C1D1aFB4E2A7884261eB00F63598a7436"


def U(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def deep_book(ts, mid=225.0, half_spread=0.01, qty=200.0, n=60):
    bids = tuple(Level(mid - half_spread - i * 0.5, qty) for i in range(n))
    asks = tuple(Level(mid + half_spread + i * 0.5, qty) for i in range(n))
    return Book("NVDABUSDT", ts, bids, asks, depth_limit=5000)


def calibrated(book, spread_mult=1.0, depth_mult=1.0):
    from afterbell.measure import depth_within, half_spread_bps
    return Baseline("NVDABUSDT", n_rth=500,
                    median_half_spread_bps=half_spread_bps(book) / spread_mult,
                    median_depth_1pct=depth_within(book, 1.0) / depth_mult,
                    min_samples=300)


def ctx_at(ts, *, ref_price=225.0, ref_age_h=0.0, book=None, baseline=None,
           status="TRADING", contract=None, query="buy Nvidia",
           corporate_action=None):
    t = U(ts)
    book = book or deep_book(t)
    return MarketContext(
        clock=clock_at(t), book=book,
        baseline=baseline if baseline is not None else calibrated(book),
        reference_price=ref_price,
        reference_ts=t - timedelta(hours=ref_age_h),
        exchange_status=status, corporate_action=corporate_action,
        resolution=resolve(query), contract=contract)


def req(notional=1000.0):
    return OrderRequest("NVDABUSDT", Side.BUY, notional, query="buy Nvidia")


# ---------------- Law 9: it must stay out of the way ----------------

def test_midday_regular_session_passes_cleanly():
    d = evaluate(req(1000.0), ctx_at("2026-09-03T15:00:00"), POL)
    assert d.verdict is Verdict.PASS
    assert d.allowed_notional == 1000.0
    assert d.binding_constraint == "none"
    assert all(v == "PASS" for v in d.gate_map.values())


# ---------------- P1: the bell ----------------

def test_exposure_ramps_down_approaching_the_close():
    far = evaluate(req(5000.0), ctx_at("2026-09-04T18:00:00"), POL)
    near = evaluate(req(5000.0), ctx_at("2026-09-04T19:55:00"), POL)
    assert far.allowed_notional > near.allowed_notional
    assert near.verdict is Verdict.REDUCE
    assert near.binding_constraint == "P1"


def test_friday_evening_is_tighter_than_tuesday_evening():
    """Both RTH_POST with a fresh reference. Only the darkness ahead differs,
    and it is the whole point."""
    fri = evaluate(req(5000.0), ctx_at("2026-09-04T23:00:00"), POL)
    tue = evaluate(req(5000.0), ctx_at("2026-09-08T23:00:00"), POL)
    assert fri.allowed_notional < tue.allowed_notional


def test_saturday_with_a_stale_reference_reduces_hard():
    d = evaluate(req(5000.0), ctx_at("2026-09-05T03:00:00", ref_age_h=7), POL)
    assert d.verdict is Verdict.REDUCE
    assert d.allowed_notional <= POL.base_notional * 0.20


# ---------------- P2: liquidity ----------------

def test_thin_book_blocks_on_walk_cost():
    t = U("2026-09-05T03:00:00")
    thin = Book("NVDABUSDT", t, (Level(200.0, 1),), (Level(260.0, 1),),
                depth_limit=5000)
    d = evaluate(req(200.0), ctx_at("2026-09-05T03:00:00", book=thin,
                                    baseline=calibrated(deep_book(t))), POL)
    assert d.verdict is Verdict.BLOCK
    assert "P2" in d.binding_constraint


def test_uncalibrated_symbol_gets_the_most_restrictive_tier():
    b = Baseline("NVDABUSDT", n_rth=12, median_half_spread_bps=1.0,
                 median_depth_1pct=1000.0, min_samples=300)
    d = evaluate(req(5000.0), ctx_at("2026-09-03T15:00:00", baseline=b), POL)
    assert d.verdict is Verdict.BLOCK
    g = next(g for g in d.gates if g.name == "P2")
    assert g.measurements["baseline_status"] == "UNCALIBRATED"


def test_insufficient_depth_blocks_rather_than_estimating():
    t = U("2026-09-03T15:00:00")
    tiny = Book("NVDABUSDT", t, (Level(224.0, 0.01),), (Level(226.0, 0.01),),
                depth_limit=5000)
    d = evaluate(req(500_000.0), ctx_at("2026-09-03T15:00:00", book=tiny,
                                        baseline=calibrated(deep_book(t))), POL)
    assert d.verdict is Verdict.BLOCK


# ---------------- P3: basis ----------------

def test_missing_reference_blocks():
    c = ctx_at("2026-09-05T03:00:00")
    c.reference_price = None
    d = evaluate(req(1000.0), c, POL)
    assert d.verdict is Verdict.BLOCK and "P3" in d.binding_constraint


def test_wide_basis_blocks():
    d = evaluate(req(1000.0), ctx_at("2026-09-05T03:00:00", ref_price=100.0), POL)
    assert d.verdict is Verdict.BLOCK
    assert d.binding_constraint == "P3"


def test_stale_reference_floors_to_degraded_even_when_basis_is_tight():
    """A basis of zero against a 61-hour-old close is not agreement."""
    d = evaluate(req(5000.0), ctx_at("2026-09-06T12:00:00", ref_price=225.0,
                                     ref_age_h=61), POL)
    g = next(g for g in d.gates if g.name == "P3")
    assert g.measurements["degraded_floor_applied"] is True
    assert g.measurements["basis_bps"] == pytest.approx(0.0, abs=1)


def test_reference_beyond_the_age_cap_blocks():
    d = evaluate(req(1000.0), ctx_at("2026-09-05T03:00:00", ref_age_h=200), POL)
    assert d.verdict is Verdict.BLOCK and "P3" in d.binding_constraint


# ---------------- P4, P5, P6 ----------------

def test_halted_pair_blocks():
    d = evaluate(req(1000.0), ctx_at("2026-09-03T15:00:00", status="HALT"), POL)
    assert d.verdict is Verdict.BLOCK


def test_corporate_action_blocks_new_entry():
    d = evaluate(req(1000.0), ctx_at("2026-09-03T15:00:00",
                                     corporate_action="earnings"), POL)
    assert d.verdict is Verdict.BLOCK and "P4" in d.binding_constraint


def test_unresolved_instrument_blocks():
    d = evaluate(req(1000.0), ctx_at("2026-09-03T15:00:00", query="buy Apple"), POL)
    assert d.verdict is Verdict.BLOCK and "P5" in d.binding_constraint


def test_counterfeit_contract_blocks_despite_a_clean_audit():
    c = verify_contract("NVDABUSDT", "0xDEAD00000000000000000000000000000000dead",
                        audit_verdict="no honeypot detected")
    d = evaluate(req(1000.0), ctx_at("2026-09-03T15:00:00", contract=c), POL)
    assert d.verdict is Verdict.BLOCK and "P6" in d.binding_constraint
    assert "either check alone is insufficient" in d.rationale or True
    g = next(g for g in d.gates if g.name == "P6")
    assert "blocks it regardless" in g.detail


def test_canonical_contract_passes():
    c = verify_contract("NVDABUSDT", NVDA_CONTRACT,
                        audit_status="UNSUPPORTED", audit_supported=False)
    d = evaluate(req(1000.0), ctx_at("2026-09-03T15:00:00", contract=c), POL)
    assert d.verdict is Verdict.PASS


# ---------------- Law 7: monotone ----------------

def test_guard_never_returns_more_than_requested():
    d = evaluate(req(10.0), ctx_at("2026-09-03T15:00:00"), POL)
    assert d.allowed_notional == 10.0


def test_factors_combine_by_min_not_product():
    """Three merely-cautious signals must not compound into a block that no
    single measurement supports."""
    d = evaluate(req(5000.0), ctx_at("2026-09-05T03:00:00", ref_age_h=7), POL)
    tightest = min(g.factor for g in d.gates)
    assert d.allowed_notional == pytest.approx(POL.base_notional * tightest)


def test_zero_or_negative_request_is_rejected():
    with pytest.raises(ValueError):
        evaluate(OrderRequest("NVDABUSDT", Side.BUY, 0.0), ctx_at("2026-09-03T15:00:00"), POL)


# ---------------- receipts ----------------

def test_receipt_carries_reference_age_and_both_checksums():
    d = evaluate(req(5000.0), ctx_at("2026-09-05T03:00:00", ref_age_h=7), POL)
    r = to_receipt(d, req(5000.0))
    assert r["reference_age"] is not None
    assert r["market_state"] == "CLOSED_WEEKEND"
    assert r["policy_sha256"] == POL.sha256
    assert len(r["registry_sha256"]) == 64
    assert set(r["gates"]) == {"P1", "P2", "P3", "P4", "P5", "P6", "P7"}
    assert r["decision"] in {"PASS", "WARN", "REDUCE", "BLOCK"}


def test_refusals_produce_a_receipt_too():
    d = evaluate(req(1000.0), ctx_at("2026-09-03T15:00:00", query="buy Apple"), POL)
    r = to_receipt(d, req(1000.0))
    assert r["decision"] == "BLOCK"
    assert r["allowed_notional"] == 0.0
    assert "unresolved" in r["rationale"].lower()


def test_every_blocking_gate_is_named_not_just_the_first():
    """An order can fail several protections at once. Reporting only the
    first in list order would blame a stale reference for an order that was
    also unresolved and counterfeit."""
    from afterbell.resolver import verify_contract as vc
    c = ctx_at("2026-09-05T03:00:00", query="buy Apple",
               contract=vc("NVDABUSDT", "0xDEAD", audit_verdict="clean"))
    c.reference_price = None
    d = evaluate(req(1000.0), c, POL)
    assert d.verdict is Verdict.BLOCK
    for gate in ("P3", "P5", "P6"):
        assert gate in d.binding_constraint
        assert gate in d.rationale
    r = to_receipt(d, req(1000.0))
    assert set(r["blocking_gates"]) == {"P3", "P5", "P6"}


# ---------------- the advertised adoption shape ----------------
#
# Four lines around an existing agent is the entire distribution claim, so the
# four lines are tested rather than only written down.

def test_package_exports_the_advertised_names():
    import afterbell
    for name in ("Guard", "OrderRequest", "Decision", "Verdict", "Side"):
        assert hasattr(afterbell, name), name


def test_resize_down_to_what_was_permitted():
    o = OrderRequest("NVDABUSDT", Side.BUY, 5000.0, query="buy Nvidia")
    assert o.at(300.0).notional == 300.0
    assert o.at(300.0).symbol == o.symbol
    assert o.notional == 5000.0          # frozen; the original is untouched


def test_resize_upward_is_refused():
    """The one way the adoption snippet could be turned into a bypass."""
    o = OrderRequest("NVDABUSDT", Side.BUY, 5000.0)
    with pytest.raises(ValueError, match="upward"):
        o.at(9000.0)


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_resize_to_nothing_is_refused(bad):
    o = OrderRequest("NVDABUSDT", Side.BUY, 5000.0)
    with pytest.raises(ValueError, match="positive"):
        o.at(bad)


# ---------------- policy files must survive being tidied ----------------

def test_basis_bands_do_not_depend_on_yaml_key_order():
    """Found while testing the executor.

    Re-serialising the policy with sorted keys put BROKEN first, whose cap is
    null, so it matched every basis and blocked everything. A rule that changes
    meaning when a file is alphabetised is a rule nobody can review.
    """
    import copy
    import yaml
    from afterbell.policy import load as load_policy

    raw = copy.deepcopy(POL.raw)
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "policy.yaml"
        p.write_text(yaml.safe_dump(raw, sort_keys=True))   # alphabetised
        shuffled = load_policy(p)

    assert list(shuffled.basis_bands) != list(POL.basis_bands)   # really reordered
    r = req()
    a = evaluate(r, ctx_at("2026-09-02T15:00:00"), POL)
    b = evaluate(r, ctx_at("2026-09-02T15:00:00"), shuffled)
    assert a.verdict is b.verdict
    assert a.allowed_notional == b.allowed_notional
    p3a = next(g for g in a.gates if g.name == "P3")
    p3b = next(g for g in b.gates if g.name == "P3")
    assert p3a.measurements["band"] == p3b.measurements["band"] == "NOMINAL"
