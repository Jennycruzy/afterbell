"""Dashboard cache tests.

The dashboard must remain readable while its large immutable archive is being
indexed. A slow build is a state-refresh concern, not an HTTP timeout.
"""

from __future__ import annotations

import threading
import time

import afterbell.dashboard as dashboard


def test_cached_state_returns_warming_snapshot_while_building(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def slow_build():
        started.set()
        assert release.wait(5)
        return {"ready": True}

    monkeypatch.setattr(dashboard, "_cache",
                        {"ts": 0.0, "data": None, "building": False})
    monkeypatch.setattr(dashboard, "build_state", slow_build)

    warming = dashboard.cached_state(max_age_s=60)

    assert warming["build_status"] == "WARMING"
    assert started.wait(2)

    release.set()
    deadline = time.monotonic() + 3
    ready = None
    while time.monotonic() < deadline:
        ready = dashboard.cached_state(max_age_s=60)
        if ready.get("ready"):
            break
        time.sleep(0.01)

    assert ready == {"ready": True}


def test_dashboard_reads_the_labels_calibrate_actually_writes(tmp_path,
                                                              monkeypatch):
    """The published table is the seam between two modules; hold it shut.

    calibrate.py writes a reader-facing market-state label ("Open") and
    dashboard.py parses that table back. When only one side was changed the
    parse silently matched nothing, every symbol reported zero regular-hours
    samples, and the public page advertised no data coverage while the guard
    itself was correctly calibrated. Nothing failed loudly, so this test
    generates the label the way calibrate does and requires the dashboard to
    recognise it.
    """
    from afterbell.calibrate import _public_state_label

    rows = [
        "| Symbol | Market period | n | Median half-spread (bps) "
        "| Median depth ±1% (USDT) |",
        "|---|---|---:|---:|---:|",
    ]
    for state, n in (("RTH_OPEN", 781), ("CLOSED_HOLIDAY", 1_440)):
        rows.append(f"| NVDABUSDT | {_public_state_label(state)} | {n:,} "
                    f"| 1.099 | 601,868 |")
    table = tmp_path / "calibration.md"
    table.write_text("\n".join(rows), encoding="utf-8")
    monkeypatch.setattr(dashboard, "CALIBRATION", table)

    baseline = dashboard._published_baselines(300)["NVDABUSDT"]

    assert baseline.n_rth == 781
    assert baseline.is_calibrated
    assert baseline.n_by_state["CLOSED_HOLIDAY"] == 1_440


def test_dashboard_still_reads_a_table_written_before_the_labels_changed():
    """Canonical state names must keep parsing, so old reports stay readable."""
    assert dashboard._canonical_state("RTH_OPEN") == "RTH_OPEN"
    assert dashboard._canonical_state("Open") == "RTH_OPEN"
    assert dashboard._canonical_state("Market holiday") == "CLOSED_HOLIDAY"
