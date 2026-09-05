"""Execution.

Every test here asks the same question in a different way: can anything make
the executor place more than the guard permitted? The answer has to be no by
construction, not by convention.
"""
import copy
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from afterbell.baselines import Baseline
from afterbell.clock import evaluate as clock_at
from afterbell.executor import (
    ExecutionRefused, execute, plan,
)
from afterbell.guard import MarketContext, OrderRequest, Verdict, evaluate
from afterbell.measure import Book, Level, Side, depth_within, half_spread_bps
from afterbell.policy import PolicyError, load

BASE = load()
WHEN = datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc)


def enabled_policy(tmp_path, **over):
    raw = copy.deepcopy(BASE.raw)
    raw["executor"] = {"enabled": True, "max_order_usdt": 25.0,
                       "symbols": ["NVDABUSDT"],
                       "require_manual_invocation": True}
    raw["executor"].update(over)
    p = tmp_path / "policy.yaml"
    p.write_text(yaml.safe_dump(raw))
    return load(p)


def book():
    bids = tuple(Level(225.0 - 0.01 - i * 0.5, 200.0) for i in range(60))
    asks = tuple(Level(225.0 + 0.01 + i * 0.5, 200.0) for i in range(60))
    return Book("NVDABUSDT", WHEN, bids, asks, depth_limit=5000)


def ctx(pol):
    from afterbell.resolver import resolve
    b = book()
    return MarketContext(
        clock=clock_at(WHEN), book=b,
        baseline=Baseline("NVDABUSDT", n_rth=500,
                          median_half_spread_bps=half_spread_bps(b),
                          median_depth_1pct=depth_within(b, pol.depth_band_pct),
                          min_samples=300),
        reference_price=225.0, reference_ts=WHEN - timedelta(seconds=30),
        exchange_status="TRADING", resolution=resolve("buy nvidia"))


def decide(pol, notional=1000.0):
    req = OrderRequest("NVDABUSDT", Side.BUY, notional, query="buy nvidia")
    return req, evaluate(req, ctx(pol), pol)


# ---------------- the ceilings ----------------

def test_disabled_by_default_in_the_shipped_policy():
    assert BASE.executor_enabled is False
    req, d = decide(BASE)
    with pytest.raises(ExecutionRefused, match="disabled in policy"):
        plan(d, req, BASE)


def test_hand_set_cap_binds_below_what_the_guard_permitted(tmp_path):
    pol = enabled_policy(tmp_path)
    req, d = decide(pol)
    assert d.allowed_notional == 1000.0
    p = plan(d, req, pol)
    assert p.notional == 25.0
    assert p.binding_ceiling == "executor.max_order_usdt"
    assert p.was_capped


def test_guard_binds_when_it_is_the_tighter_of_the_two(tmp_path):
    pol = enabled_policy(tmp_path, max_order_usdt=5000.0)
    req, d = decide(pol, notional=10.0)
    p = plan(d, req, pol)
    assert p.notional == 10.0
    assert p.binding_ceiling == "guard"
    assert not p.was_capped


def test_a_blocked_decision_has_no_order(tmp_path):
    from afterbell.resolver import resolve
    pol = enabled_policy(tmp_path)
    req = OrderRequest("NVDABUSDT", Side.BUY, 1000.0, query="buy apple")
    c = ctx(pol)
    c.resolution = resolve("buy apple")          # P5 blocks
    d = evaluate(req, c, pol)
    assert d.verdict is Verdict.BLOCK
    with pytest.raises(ExecutionRefused, match="no order"):
        plan(d, req, pol)


def test_symbol_absent_from_the_allowlist_is_blocked(tmp_path):
    pol = enabled_policy(tmp_path, symbols=["TSLABUSDT"])
    req, d = decide(pol)
    with pytest.raises(ExecutionRefused, match="allowlist"):
        plan(d, req, pol)


def test_placed_size_never_exceeds_the_permitted_size(tmp_path):
    """The invariant, swept across sizes rather than asserted once."""
    pol = enabled_policy(tmp_path, max_order_usdt=5000.0)
    for notional in (1.0, 10.0, 100.0, 1000.0, 5000.0):
        req, d = decide(pol, notional=notional)
        if d.verdict is Verdict.BLOCK:
            continue
        p = plan(d, req, pol)
        assert p.notional <= d.allowed_notional
        assert p.notional <= req.notional


# ---------------- the policy loader ----------------

def test_enabled_with_no_cap_is_refused_at_load(tmp_path):
    with pytest.raises(PolicyError, match="not a cap"):
        enabled_policy(tmp_path, max_order_usdt=0.0)


def test_cap_looser_than_base_notional_is_refused_at_load(tmp_path):
    with pytest.raises(PolicyError, match="may never be looser"):
        enabled_policy(tmp_path, max_order_usdt=BASE.base_notional + 1)


def test_enabled_with_an_empty_allowlist_is_refused_at_load(tmp_path):
    with pytest.raises(PolicyError, match="empty symbol allowlist"):
        enabled_policy(tmp_path, symbols=[])


# ---------------- receipts ----------------

def test_dry_run_places_nothing_and_still_receipts(tmp_path):
    pol = enabled_policy(tmp_path)
    req, d = decide(pol)
    ledger = tmp_path / "executions.jsonl"
    rec = execute(plan(d, req, pol), decision_hash="abc", ledger_path=ledger)
    assert rec["sent"] is False
    assert rec["response"] is None
    assert rec["placed_notional"] == 25.0
    assert rec["decision_hash"] == "abc"
    assert ledger.exists()


def test_receipt_records_both_sizes_so_the_cap_is_auditable(tmp_path):
    pol = enabled_policy(tmp_path)
    req, d = decide(pol)
    rec = execute(plan(d, req, pol),
                  ledger_path=tmp_path / "executions.jsonl")
    assert rec["guard_permitted_notional"] == 1000.0
    assert rec["placed_notional"] == 25.0
    assert rec["capped_below_guard"] is True




def test_the_package_root_exposes_nothing_that_can_trade():
    import afterbell
    assert "executor" not in afterbell.__all__
    assert not hasattr(afterbell, "execute")


def test_live_execution_is_refused_without_a_python_credential_path(tmp_path):
    pol = enabled_policy(tmp_path)
    req, d = decide(pol)
    with pytest.raises(ExecutionRefused, match="never receives a Binance OAuth token"):
        execute(plan(d, req, pol), live=True,
                ledger_path=tmp_path / "executions.jsonl")
