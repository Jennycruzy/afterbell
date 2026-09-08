"""Judge-facing dashboard contract tests."""
from __future__ import annotations

import json

import afterbell.dashboard as dashboard


def test_judge_facing_page_has_afterbell_sections_not_reference_branding():
    assert "JUDGE BRIEF" in dashboard.PAGE
    assert "LIVE GUARD" in dashboard.PAGE
    assert "EVIDENCE PACK" in dashboard.PAGE
    assert "AUDIT TRAIL" in dashboard.PAGE
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
