"""Evaluation-table tests.

The table is a set of safety claims, so the generator that produces it is
tested for the things that would quietly overstate them.
"""
import json

import pytest

from afterbell.evaluation import (
    render, run_adversarial, summarise_ledger,
)


def rec(**kw):
    base = {
        "decision": "PASS", "market_state": "RTH_OPEN", "reference_price": 225.0,
        "binding_constraint": "none", "gate_detail": {},
        "measurements": {"spread_ratio": 0.5, "liquidity_ratio": 1.2,
                         "n_rth": 500},
    }
    m = base["measurements"] | kw.pop("measurements", {})
    return base | kw | {"measurements": m}


def write(tmp_path, records):
    p = tmp_path / "receipts.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in records))
    return p


def test_a_clean_pass_on_a_normal_book_is_not_a_false_positive(tmp_path):
    s = summarise_ledger(write(tmp_path, [rec()] * 10))
    assert s.normal_book == 10
    assert s.false_positives == 0
    assert s.false_positive_rate == 0.0


def test_warn_counts_as_permitted_in_full(tmp_path):
    """WARN withholds no size, so it is not a refusal."""
    s = summarise_ledger(write(tmp_path, [rec(decision="WARN")] * 4))
    assert s.normal_permitted == 4
    assert s.false_positives == 0


def test_a_reduction_on_a_normal_book_is_a_false_positive(tmp_path):
    s = summarise_ledger(write(tmp_path, [rec(), rec(decision="REDUCE")]))
    assert s.normal_book == 2
    assert s.false_positives == 1
    assert s.false_positive_rate == 50.0


def test_a_reduction_on_a_wide_spread_is_correct_not_a_false_positive(tmp_path):
    """The bug in the first version of this definition, asserted against."""
    s = summarise_ledger(write(tmp_path, [
        rec(decision="REDUCE", measurements={"spread_ratio": 2.8})]))
    assert s.false_positives == 0
    assert s.correct_reductions == 1
    assert s.normal_book == 0


def test_a_reduction_on_thin_depth_is_correct(tmp_path):
    s = summarise_ledger(write(tmp_path, [
        rec(decision="REDUCE", measurements={"liquidity_ratio": 0.4})]))
    assert s.false_positives == 0
    assert s.correct_reductions == 1


def test_an_uncalibrated_block_is_counted_separately(tmp_path):
    s = summarise_ledger(write(tmp_path, [
        rec(decision="BLOCK", measurements={"n_rth": 120})]))
    assert s.false_positives == 0
    assert s.uncalibrated_blocks == 1
    assert s.normal_book == 0


def test_closure_refusals_are_excluded_from_the_cohort(tmp_path):
    s = summarise_ledger(write(tmp_path, [
        rec(decision="REDUCE", market_state="CLOSED_WEEKEND",
            binding_constraint="P1")] * 7))
    assert s.rth_live == 0
    assert s.false_positives == 0
    assert s.refused_by_state == {"CLOSED_WEEKEND": 7}


def test_the_closing_ramp_is_named_but_still_counted(tmp_path):
    """It explains the rate; it does not quietly remove itself from it."""
    s = summarise_ledger(write(tmp_path, [
        rec(), rec(decision="REDUCE", binding_constraint="P1",
                   gate_detail={"P1": "6.8m to the close; new exposure "
                                      "ramping down to 6% of base"})]))
    assert s.closing_ramp == 1
    assert s.false_positives == 1          # counted, not excused
    assert s.false_positive_rate == 50.0


def test_freeze_refusals_are_not_measurements(tmp_path):
    s = summarise_ledger(write(tmp_path, [
        rec(decision="BLOCK", binding_constraint="OPERATOR_FREEZE")] * 3))
    assert s.freeze_refusals == 3
    assert s.false_positives == 0
    assert s.rth_live == 0


def test_redemption_records_are_not_counted_as_evaluations(tmp_path):
    s = summarise_ledger(write(tmp_path, [
        rec(), {"kind": "authorization_redeemed", "nonce": "abc"}]))
    assert s.total == 1


def test_an_empty_ledger_reports_no_rate_rather_than_zero(tmp_path):
    s = summarise_ledger(tmp_path / "absent.jsonl")
    assert s.false_positive_rate is None
    assert "no samples yet" in render(run_adversarial(), s)


# ---------------- the adversarial half, run for real ----------------

@pytest.fixture(scope="module")
def adv():
    return run_adversarial()


def test_no_payload_ever_raised_the_permitted_size(adv):
    """The invariant the whole corpus exists to test."""
    assert adv.raised_above_control == 0


def test_every_attack_that_had_to_be_refused_was(adv):
    assert adv.refusals_correct == adv.refusals_expected > 0


def test_the_suite_cannot_win_by_refusing_everything(adv):
    assert adv.positive_controls_passed == adv.positive_controls > 0


def test_the_corpus_runs_against_more_than_one_market(adv):
    assert adv.snapshots >= 2
    assert adv.runs == adv.attacks * adv.snapshots
