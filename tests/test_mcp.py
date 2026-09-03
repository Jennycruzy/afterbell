import json

import httpx

from afterbell.mcp import MCPClient


def test_streamable_client_keeps_session_and_initializes_once():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append((body, request.headers.get("Mcp-Session-Id")))
        method = body.get("method")
        if method == "initialize":
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": body["id"],
                           "result": {"protocolVersion": "2025-06-18"}},
                headers={"Mcp-Session-Id": "test-session"}, request=request)
        if method == "notifications/initialized":
            return httpx.Response(202, request=request)
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": body["id"],
                       "result": {"tools": []}}, request=request)

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    client = MCPClient("test-token", url="https://agent.test/mcp", client=http)
    try:
        first = client.tools_list()
        second = client.tools_list()
    finally:
        client.close()

    assert first["result"] == {"tools": []}
    assert second["result"] == {"tools": []}
    assert [c[0]["method"] for c in calls] == [
        "initialize", "notifications/initialized", "tools/list", "tools/list",
    ]
    assert calls[0][1] is None
    assert all(c[1] == "test-session" for c in calls[1:])
