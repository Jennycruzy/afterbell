"""Focused tests for the MCP transport and quota boundary.

These tests deliberately exercise the HTTP handler as well as the quota store:
the latter is the durable bound on receipt growth, while the former is where a
public caller can send an oversized or malformed batch.
"""

from __future__ import annotations

import http.client
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

import afterbell.mcp_server as mcp


def post(address: tuple[str, int], body: object) -> tuple[int, dict[str, str], object]:
    connection = http.client.HTTPConnection(*address, timeout=10)
    try:
        encoded = json.dumps(body).encode()
        connection.request(
            "POST", "/", body=encoded,
            headers={"Content-Type": "application/json",
                     "Content-Length": str(len(encoded))})
        response = connection.getresponse()
        raw = response.read()
        parsed = json.loads(raw) if raw else None
        return response.status, dict(response.getheaders()), parsed
    finally:
        connection.close()


@pytest.fixture
def http_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    previous = mcp._QUOTA
    quota_path = tmp_path / "mcp-quota.json"
    monkeypatch.setattr(
        mcp, "_QUOTA",
        mcp.MCPQuota(quota_path, rate_window_s=60, max_rate_units=100,
                     daily_evaluation_limit=1000))
    server = mcp.ThreadingHTTPServer(("127.0.0.1", 0), mcp.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address, quota_path
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        mcp._QUOTA = previous


def test_batch_limit_is_rejected_before_quota_or_dispatch(http_server):
    address, quota_path = http_server
    body = [
        {"jsonrpc": "2.0", "id": i, "method": "ping"}
        for i in range(mcp.MAX_BATCH_MESSAGES + 1)
    ]

    status, _, result = post(address, body)

    assert status == 413
    assert result["error"]["code"] == mcp.INVALID_REQUEST
    assert not quota_path.exists()


def test_non_object_batch_item_is_an_invalid_request(http_server):
    status, _, result = post(
        http_server[0],
        [{"jsonrpc": "2.0", "id": 1, "method": "ping"}, "not an object"],
    )

    assert status == 200
    assert result[0]["result"] == {}
    assert result[1]["error"]["code"] == mcp.INVALID_REQUEST


def test_http_rate_limit_returns_429_and_retry_after(http_server, monkeypatch):
    quota_path = http_server[1]
    monkeypatch.setattr(
        mcp, "_QUOTA",
        mcp.MCPQuota(quota_path, rate_window_s=60, max_rate_units=1,
                     daily_evaluation_limit=1000))

    first_status, _, first = post(
        http_server[0], {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    second_status, second_headers, second = post(
        http_server[0], {"jsonrpc": "2.0", "id": 2, "method": "ping"})

    assert first_status == 200
    assert first["result"] == {}
    assert second_status == 429
    assert int(second_headers["Retry-After"]) >= 1
    assert second["error"]["code"] == mcp.QUOTA_EXCEEDED


def test_daily_evaluation_quota_persists_across_store_instances(tmp_path):
    path = tmp_path / "mcp-quota.json"
    first = mcp.MCPQuota(path, rate_window_s=60, max_rate_units=100,
                         daily_evaluation_limit=2)
    now = 1_789_000_000.0
    expected_day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()

    assert first.admit("client", request_units=1, evaluations=2,
                       now=now).allowed

    second = mcp.MCPQuota(path, rate_window_s=60, max_rate_units=100,
                          daily_evaluation_limit=2)
    denied = second.admit("client", request_units=1, evaluations=1,
                          now=now)

    assert not denied.allowed
    assert "daily MCP evaluation quota" in denied.reason
    assert denied.retry_after_s >= 1
    assert json.loads(path.read_text()) == {
        "day": expected_day, "evaluations": 2,
    }


def test_batch_charges_each_message_to_the_short_window(tmp_path):
    quota = mcp.MCPQuota(tmp_path / "mcp-quota.json", rate_window_s=60,
                         max_rate_units=2, daily_evaluation_limit=1000)

    allowed = quota.admit("client", request_units=2, evaluations=0,
                          now=1_789_000_000.0)
    denied = quota.admit("client", request_units=1, evaluations=0,
                         now=1_789_000_001.0)

    assert allowed.allowed
    assert not denied.allowed
    assert denied.retry_after_s >= 1


def test_nginx_template_has_a_source_address_mcp_limiter():
    config = Path(__file__).parents[1] / "deploy" / "nginx-afterbell.conf"
    text = config.read_text()

    assert "limit_req_zone $binary_remote_addr" in text
    assert "zone=afterbell_mcp" in text
    assert "rate=30r/m" in text
    assert "limit_req zone=afterbell_mcp" in text
    assert "limit_req_status 429" in text
