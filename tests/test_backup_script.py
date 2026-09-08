"""Focused integration tests for the recorder backup script."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "backup.sh"


def _fixture(tmp_path: Path, *, with_config: bool = True):
    project = tmp_path / "project"
    data = project / "data"
    current = datetime.now(timezone.utc).date()
    old_day = current - timedelta(days=7)
    yesterday = current - timedelta(days=1)
    today = current
    for day in (old_day, yesterday, today):
        (data / "raw" / day.isoformat()).mkdir(parents=True)

    old_file = data / "raw" / old_day.isoformat() / "old.json"
    yesterday_file = data / "raw" / yesterday.isoformat() / "yesterday.json"
    today_file = data / "raw" / today.isoformat() / "today.json"
    old_file.write_text("old\n", encoding="utf-8")
    yesterday_file.write_text("yesterday\n", encoding="utf-8")
    today_file.write_text("today\n", encoding="utf-8")
    for path, day in ((old_file, old_day), (yesterday_file, yesterday)):
        timestamp = datetime.combine(day, datetime.min.time(), timezone.utc).timestamp()
        os.utime(path, (timestamp, timestamp))

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = config_dir / "rclone.conf"
    if with_config:
        config.touch()
    remote = tmp_path / "remote"
    env_file = tmp_path / "backup.env"
    env_file.write_text(
        f"AFTERBELL_BACKUP_REMOTE={remote}\n"
        "AFTERBELL_BACKUP_MIN_AGE=2m\n"
        "AFTERBELL_BACKUP_RETENTION_DAYS=2\n"
        f"RCLONE_CONFIG={config}\n",
        encoding="utf-8")

    script = tmp_path / "backup.sh"
    script.write_text(
        SCRIPT.read_text(encoding="utf-8").replace(
            "ROOT=/home/ubuntu/afterbell", f"ROOT={project}"),
        encoding="utf-8")
    script.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "AFTERBELL_BACKUP_ENV": str(env_file),
        "HOME": str(tmp_path / "home"),
    })
    return script, data, remote, env


@pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone is required")
def test_backup_verifies_stable_copy_and_prunes_only_verified_raw_day(tmp_path):
    script, data, remote, env = _fixture(tmp_path)
    result = subprocess.run(
        ["bash", str(script)], env=env, text=True,
        capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert (remote / "raw" / (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat() / "yesterday.json").is_file()
    assert not (remote / "raw" / datetime.now(timezone.utc).date().isoformat() / "today.json").exists()
    assert not (data / "raw" / (datetime.now(timezone.utc).date() - timedelta(days=7)).isoformat()).exists()
    assert (data / "raw" / datetime.now(timezone.utc).date().isoformat() / "today.json").is_file()
    status = json.loads((data / "backup_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "OK"
    assert status["covered_through"] == (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    assert "Config file" not in (data / "backup.log").read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone is required")
def test_backup_fails_when_config_file_is_missing(tmp_path):
    script, data, _remote, env = _fixture(tmp_path, with_config=False)
    result = subprocess.run(
        ["bash", str(script)], env=env, text=True,
        capture_output=True, check=False)
    assert result.returncode == 2
    status = json.loads((data / "backup_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "FAILED"
    assert "missing or unreadable" in (data / "backup.log").read_text(encoding="utf-8")
