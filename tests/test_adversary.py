"""The corpus is the test.

Every attack runs against one fixed snapshot of the market, so the only
variable between the control and an attacked run is text the attacker controls.
A green suite here is the evidence for Law 6; a red one is a bypass.
"""
from afterbell.adversary import (
    CORPUS, IGNORED, REFUSED, REJECTED, SNAPSHOTS, demo_context_factory,
    escalation_held, run_corpus, run_escalation,
)
from afterbell.guard import OrderRequest, Side, Verdict, evaluate
from tests.test_guard import read_only_test_policy

import pytest

POL = read_only_test_policy()

# The corpus runs against the same fixed snapshots the demo uses, so a green
# suite and a clean demo are the same claim rather than two.
OPEN_AT, _ = SNAPSHOTS["open"]
WEEKEND_AT, LAST_BELL = SNAPSHOTS["weekend"]
context_for = demo_context_factory(OPEN_AT, POL)
weekend_context_for = demo_context_factory(WEEKEND_AT, POL, LAST_BELL)

BASE = OrderRequest("NVDABUSDT", Side.BUY, 1000.0, query="buy nvidia")
RESULTS = run_corpus(BASE, POL, context_for)
BY_NAME = {r.attack.name: r for r in RESULTS}

# The same corpus against a market that has already cut the size. An attack
# that cannot move an unconstrained guard might still move a constrained one.
WEEKEND_BASE = OrderRequest("NVDABUSDT", Side.BUY, POL.base_notional,
                            query="buy nvidia")
WEEKEND_RESULTS = run_corpus(WEEKEND_BASE, POL, weekend_context_for)


def test_control_passes_cleanly():
    """If the control were already blocked the corpus would prove nothing."""
    control = evaluate(BASE, context_for(BASE), POL)
    assert control.verdict is Verdict.PASS
    assert control.allowed_notional == BASE.notional


def test_corpus_is_not_all_one_expectation():
    """A corpus where everything is ignored is a corpus that tests nothing."""
    kinds = {a.expectation for a in CORPUS}
    assert kinds == {IGNORED, REFUSED, REJECTED}


def test_attack_names_are_unique():
    assert len({a.name for a in CORPUS}) == len(CORPUS)


@pytest.mark.parametrize("result", RESULTS, ids=lambda r: r.attack.name)
def test_attack_behaves_as_declared(result):
    assert result.held, (
        f"{result.attack.name} ({result.attack.family}, expected "
        f"{result.attack.expectation}): {result.observation}")


def test_no_attack_ever_raised_permitted_size():
    """The invariant across the whole corpus, stated once."""
    assert escalation_held(RESULTS)
    for r in RESULTS:
        assert r.allowed <= r.control.allowed_notional


def test_enormous_request_is_refused_not_trimmed():
    """Asking for more returns less, and asking for the impossible returns 0.

    A size the visible book cannot absorb has an unknown cost, not merely a
    high one, so P2 refuses it outright rather than quietly trimming it to the
    policy ceiling and reporting a number it cannot stand behind.
    """
    r = BY_NAME["enormous_notional"]
    assert r.decision.requested_notional == 50_000_000.0
    assert r.decision.verdict is Verdict.BLOCK
    assert r.decision.allowed_notional == 0.0
    assert "P2" in r.decision.binding_constraint


def test_a_smaller_request_is_still_met_in_full():
    """Without this the corpus could pass by refusing everything."""
    smaller = OrderRequest("NVDABUSDT", Side.BUY, 900.0, query="buy nvidia")
    d = evaluate(smaller, context_for(smaller), POL)
    assert d.verdict is Verdict.PASS
    assert d.allowed_notional == 900.0


def test_audited_counterfeit_blocks_despite_clean_audit():
    """The demonstrative case: both checks are required, neither suffices."""
    r = BY_NAME["audited_counterfeit"]
    assert r.decision.verdict is Verdict.BLOCK
    assert "P6" in r.decision.binding_constraint
    p6 = next(g for g in r.decision.gates if g.name == "P6")
    assert p6.measurements["audit_verdict"]


def test_injection_text_is_recorded_in_the_receipt():
    """A refused injection that leaves no trace is an uninvestigable one."""
    from afterbell.guard import to_receipt
    a = next(a for a in CORPUS if a.name == "plain_override")
    req = a.apply(BASE)
    receipt = to_receipt(evaluate(req, context_for(req), POL), req)
    assert receipt["decision"] == "PASS"
    assert receipt["rationale"].startswith("PASS:")
    # The payload never appears in the decision text the guard stands behind.
    assert "ignore all previous instructions" not in receipt["rationale"]


# ---------------- the same corpus against a constrained guard ----------------

def test_weekend_control_is_reduced_not_passed():
    """If the weekend control passed in full there would be nothing to argue."""
    control = evaluate(WEEKEND_BASE, weekend_context_for(WEEKEND_BASE), POL)
    assert control.verdict is Verdict.REDUCE
    assert control.binding_constraint == "P1"
    assert 0 < control.allowed_notional < WEEKEND_BASE.notional


@pytest.mark.parametrize("result", WEEKEND_RESULTS, ids=lambda r: r.attack.name)
def test_attack_behaves_as_declared_on_a_weekend(result):
    assert result.held, (
        f"{result.attack.name} on the weekend snapshot "
        f"(expected {result.attack.expectation}): {result.observation}")


def test_no_attack_raised_permitted_size_on_a_weekend():
    assert escalation_held(WEEKEND_RESULTS)


def test_escalation_never_wins_a_larger_ceiling():
    """The transcript the demo prints, asserted rather than eyeballed."""
    turns = run_escalation(WEEKEND_BASE, POL, weekend_context_for)
    ceiling = turns[0][1].control.allowed_notional
    assert ceiling > 0
    assert all(r.allowed <= ceiling for _, r in turns)
    # And the guard never simply gave up either: the opening ask is still
    # partly permitted after fourteen attempts to talk it up.
    assert turns[0][1].allowed == ceiling


def test_every_escalation_turn_maps_to_a_corpus_attack():
    from afterbell.adversary import ESCALATION
    names = {a.name for a in CORPUS}
    assert {n for n, _ in ESCALATION} <= names
