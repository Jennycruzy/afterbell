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
