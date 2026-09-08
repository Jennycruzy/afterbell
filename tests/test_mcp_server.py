"""MCP server tests.

The server is the surface a judge points their own client at, so the protocol
shape is asserted, not assumed — and so is the claim that it cannot trade.
"""
import json
from pathlib import Path

import pytest

from afterbell.mcp_server import (
    HANDLERS, PROTOCOL_VERSION, TOOLS, ToolError, evaluate_order, handle,
)


def call(method, params=None, mid=1):
    msg = {"jsonrpc": "2.0", "id": mid, "method": method}
    if params is not None:
        msg["params"] = params
    return handle(msg)


# ---------------- protocol ----------------

def test_initialize_advertises_tools():
    r = call("initialize")["result"]
    assert r["protocolVersion"] == PROTOCOL_VERSION
    assert r["capabilities"]["tools"] is not None
    assert r["serverInfo"]["name"] == "afterbell"
    assert "cannot place orders" in r["instructions"]


def test_tools_list_matches_the_handlers():
    names = [t["name"] for t in call("tools/list")["result"]["tools"]]
    assert names == list(HANDLERS)


def test_every_tool_declares_a_schema():
    for tool in TOOLS:
        assert tool["inputSchema"]["type"] == "object"
        assert tool["description"]


def test_ping_answers():
    assert call("ping")["result"] == {}


def test_a_notification_gets_no_reply():
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_an_unknown_method_is_an_error_not_a_crash():
    assert call("tools/frobnicate")["error"]["code"] == -32601


def test_a_wrong_protocol_version_is_refused():
    r = handle({"jsonrpc": "1.0", "id": 1, "method": "ping"})
    assert r["error"]["code"] == -32600


def test_an_unknown_tool_is_reported_as_invalid_params():
    r = call("tools/call", {"name": "place_order", "arguments": {}})
    assert r["error"]["code"] == -32602


# ---------------- the tools refuse bad input as tool errors ----------------

@pytest.mark.parametrize("args,expected", [
    ({}, "symbol is required"),
    ({"symbol": "NVDABUSDT"}, "notional must be a number"),
    ({"symbol": "NVDABUSDT", "notional": -5}, "notional must be positive"),
    ({"symbol": "NVDABUSDT", "notional": 0}, "notional must be positive"),
    ({"symbol": "NVDABUSDT", "notional": "lots"}, "notional must be a number"),
    ({"symbol": "NVDABUSDT", "notional": 10, "side": "HODL"},
     "side must be BUY or SELL"),
])
def test_bad_arguments_are_tool_errors(args, expected):
    """A malformed call must not take the server down or return a decision."""
    with pytest.raises(ToolError, match=expected):
        evaluate_order(args)


def test_a_tool_error_is_reported_in_band():
    """isError true, so the calling agent sees a failure rather than a verdict."""
    r = call("tools/call", {"name": "evaluate_order", "arguments": {}})
    assert r["result"]["isError"] is True
    assert "symbol is required" in r["result"]["content"][0]["text"]


# ---------------- it cannot trade ----------------

def test_no_tool_can_place_an_order():
    """The whole surface is read-only tools, and this asserts it stays so.

    The set is pinned rather than counted, so adding a tool is a deliberate
    edit here and a write tool cannot arrive unnoticed.
    """
    for tool in TOOLS:
        blob = json.dumps(tool).lower()
        assert "place" not in blob.replace("places an order", "")
    assert set(HANDLERS) == {"evaluate_order", "get_market_state",
                             "get_safety_posture"}


def test_the_posture_tool_authorises_nothing():
    """It reports what was noticed. Permission comes only from evaluate_order."""
    from afterbell.mcp_server import get_safety_posture, ToolError
    try:
        out = get_safety_posture({})
    except ToolError:
        return                             # nothing recorded yet is a fine state
    assert out["authorizes"] is None
    assert "permitted_notional" not in out
    assert "signature" not in out


def test_the_server_reaches_nothing_that_can_trade():
    """The one claim the whole surface rests on, asserted against the source."""
    import afterbell.mcp_server as mod
    src = Path(mod.__file__).read_text()
    body = src.split('"""', 2)[2]          # past the module docstring
    for forbidden in ("executor", "_mcp_place_order", "Authorization",
                      "bearer", "os.environ"):
        assert forbidden not in body, f"{forbidden} reachable from the server"
