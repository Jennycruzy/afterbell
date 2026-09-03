"""Engine lifecycle tests for live baseline refresh behavior."""

from afterbell import engine as engine_module
from afterbell.baselines import Baseline
from afterbell.policy import load


def test_uncalibrated_baseline_is_refreshed_for_a_long_running_guard(
        monkeypatch, tmp_path):
    policy = load()
    first = Baseline("NVDABUSDT", n_rth=0,
                     median_half_spread_bps=None, median_depth_1pct=None,
                     min_samples=policy.min_rth_samples)
    second = Baseline("NVDABUSDT", n_rth=policy.min_rth_samples,
                      median_half_spread_bps=1.0, median_depth_1pct=1.0,
                      min_samples=policy.min_rth_samples)
    calls = []

    def fake_build(**kwargs):
        calls.append(kwargs)
        return {"NVDABUSDT": first if len(calls) == 1 else second}

    monkeypatch.setattr(engine_module.bl, "build", fake_build)
    guard = engine_module.Guard(policy, ledger_path=tmp_path / "receipts.jsonl")

    result = guard.baseline_for("NVDABUSDT")

    assert result is second
    assert len(calls) == 2
    assert calls[0]["window_days"] == policy.baseline_window_days
