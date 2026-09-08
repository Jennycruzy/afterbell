"""Operational dashboard contract tests."""
from __future__ import annotations

import json

import afterbell.dashboard as dashboard


def test_operational_console_page_has_afterbell_sections_not_reference_branding():
    assert "Decision explorer" in dashboard.PAGE
    assert "Data coverage" in dashboard.PAGE
    assert "Configure order limit" in dashboard.PAGE
    assert "Safety limits" not in dashboard.PAGE
    assert "SET IN CONFIG" in dashboard.PAGE
    assert "Paused for approval" not in dashboard.PAGE
    assert "approval" not in dashboard.PAGE.lower()
    assert "READ ONLY" not in dashboard.PAGE
    assert "Decision history" in dashboard.PAGE
    assert "P7" not in dashboard.PAGE
    assert "HUMAN REVIEW" not in dashboard.PAGE
    assert "human review" not in dashboard.PAGE.lower()
    assert "<option>PASS</option>" not in dashboard.PAGE
    assert "<option>BLOCK</option>" not in dashboard.PAGE
    assert "The stock sleeps. The token doesn't." in dashboard.PAGE
    assert "Why the public result may be $0" in dashboard.PAGE
    assert "Public tools advise any agent" in dashboard.PAGE
    assert "fetch('/api/status'" in dashboard.PAGE
    assert "Deltr" not in dashboard.PAGE



def test_public_state_translates_machine_labels(monkeypatch):
    raw = {
        "guard": {
            "status": "BLOCK",
            "binding_constraint": "P7",
            "gates": {
                "P1": "PASS", "P2": "WARN", "P3": "REDUCE",
                "P4": "PASS", "P5": "PASS", "P6": "PASS", "P7": "BLOCK",
            },
            "gate_detail": {"P7": "P7 is required; no snapshot supplied"},
            "market_state": "CLOSED_WEEKEND",
            "policy_status": "UNCALIBRATED",
            "measurements": {"exposure_check": "REQUIRED_BUT_MISSING"},
        },
        "policy": {"status": "PROTECTED", "base_notional": 5000.0},
        "symbols": [{"baseline_status": "CALIBRATED",
                     "n_by_state": {"CLOSED_HOLIDAY": 1440}}],
        "receipts": [{"decision": "BLOCK", "gate_factors": {
            "P1": 1.0, "P7": 0.0}}],
        "calibration_markdown": "Status: CALIBRATED; RTH_OPEN",
        "clock": {"state": "CLOSED_WEEKEND"},
        "build_status": "WARMING",
        "backup": {"status": "OK"},
    }

    public = dashboard._public_state(raw)
    encoded = json.dumps(public)

    assert public["guard"]["status"] == "Blocked"
    assert public["guard"]["main_reason"] == "Account exposure"
    assert public["guard"]["checks"][-1]["name"] == "Account exposure"
    assert "safety_limits_ready" not in public["policy"]
    assert public["policy"]["base_notional"] == 5000.0
    assert "policy_status" not in public["guard"]
    assert "policy_status" not in public["receipts"][0]
    assert public["symbols"][0]["baseline_ready"] is True
    assert public["symbols"][0]["holiday_samples"] == 1440
    assert public["build_status"] == "Loading"
    assert "P7" not in encoded
    assert "UNCALIBRATED" not in encoded
    assert "PROTECTED" not in encoded
    assert "CLOSED_WEEKEND" not in encoded

def test_dashboard_exposes_generated_evidence_without_recomputing_it(
        monkeypatch, tmp_path):
    evaluation = tmp_path / "evaluation.md"
    evaluation.write_text(
        "| Metric | Value |\n|---|---|\n| Live evaluations receipted | 42 |\n")
    backup = tmp_path / "backup_status.json"
    backup.write_text(json.dumps({
        "status": "OK", "covered_through": "2026-09-07",
        "retention_days": "14", "ts": "2026-09-08T08:43:02Z",
    }))
    monkeypatch.setattr(dashboard, "EVALUATION", evaluation)
    monkeypatch.setattr(dashboard, "BACKUP_STATUS", backup)

    assert dashboard._evaluation_metrics()["Live evaluations receipted"] == "42"
    assert dashboard._backup_state()["status"] == "OK"

def test_tail_records_reads_only_complete_recent_rows(tmp_path):
    ledger = tmp_path / "events.jsonl"
    ledger.write_bytes(
        b'{"seq":1}\n{"seq":2}\n{"seq":3}\n{"seq":4}\n')
    assert [row["seq"] for row in dashboard._tail_records(ledger, 2)] == [3, 4]


def test_published_baselines_keep_coverage_separate_from_policy(
        monkeypatch, tmp_path):
    calibration = tmp_path / "calibration.md"
    calibration.write_text(
        "| Symbol | State | n | Median half-spread (bps) | "
        "Median depth ±1% (USDT) | p95 | p05 |\n"
        "|---|---|---:|---:|---:|---:|---:|\n"
        "| NVDABUSDT | CLOSED_HOLIDAY | 1440 | 0.2 | 580000 | 1 | 2 |\n"
        "| NVDABUSDT | RTH_OPEN | 781 | 1.1 | 601000 | 2 | 3 |\n")
    monkeypatch.setattr(dashboard, "CALIBRATION", calibration)

    baseline = dashboard._published_baselines(300)["NVDABUSDT"]

    assert baseline.status == "CALIBRATED"
    assert baseline.n_by_state["CLOSED_HOLIDAY"] == 1440
    assert baseline.spread_ratio(2.2) == 2.0


def test_live_status_is_small_and_excludes_archive_evidence(monkeypatch):
    monkeypatch.setattr(dashboard, "_load_guard_state", lambda: {
        "status": "BLOCK", "gates": {}, "gate_detail": {}, "ts": "now",
    })
    monkeypatch.setattr(dashboard, "_backup_state", lambda: {"status": "OK"})
    monkeypatch.setattr(dashboard, "head_of", lambda path: "abc")
    status = dashboard.live_status()
    assert status["guard"]["status"] == "Blocked"
    assert status["backup"]["status"] == "Healthy"
    assert status["ledger_head"] == "abc"
    assert "status_generated_at" in status
    assert "history" not in status
    assert "receipts" not in status
    assert "calibration_markdown" not in status
