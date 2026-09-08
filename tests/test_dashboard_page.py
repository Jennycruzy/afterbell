"""Operational dashboard contract tests."""
from __future__ import annotations

import json

import afterbell.dashboard as dashboard


def test_operational_console_page_has_afterbell_sections_not_reference_branding():
    assert "Decision console" in dashboard.PAGE
    assert "Baseline coverage" in dashboard.PAGE
    assert "Policy review" in dashboard.PAGE
    assert "Receipt activity" in dashboard.PAGE
    assert "Deltr" not in dashboard.PAGE


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
