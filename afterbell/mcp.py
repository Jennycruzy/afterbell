"""Minimal session-aware MCP Streamable HTTP client.

Agent OS is MCP over Streamable HTTP. A session id returned by ``initialize``
must accompany later requests; treating each request as an unrelated POST can
make an OAuth token look invalid when the real problem is a missing session.
This client never logs the bearer token and parses both JSON and SSE responses.
"""
from __future__ import annotations

import json
from typing import Any

import httpx


class MCPError(RuntimeError):
    """An authenticated MCP request failed or returned a JSON-RPC error."""


class MCPClient:
    def __init__(self, token: str, *, url: str,
                 timeout: float = 45.0,
                 client: httpx.Client | None = None) -> None:
        if not token.strip():
            raise ValueError("MCP bearer token must not be empty")
        self._token = token
        self.url = url
        self.client = client if client is not None else httpx.Client(timeout=timeout)
        self.session_id: str | None = None
        self._initialized = False
        self._next_id = 1

    def close(self) -> None:
        self.client.close()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    @staticmethod
    def _body(response: httpx.Response) -> dict[str, Any]:
        if response.status_code not in (200, 202):
            raise MCPError(
                f"MCP HTTP {response.status_code}: {response.text[:400]}")
        text = response.text.strip()
        if not text:
            return {}
        if "text/event-stream" in response.headers.get("content-type", "") \
                or text.startswith("event:") or "\ndata:" in text:
            for line in text.splitlines():
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload:
                        parsed = json.loads(payload)
                        if not isinstance(parsed, dict):
                            raise MCPError("MCP SSE payload is not an object")
                        return parsed
            raise MCPError("MCP returned an SSE stream with no data event")
        parsed = response.json()
        if not isinstance(parsed, dict):
            raise MCPError("MCP JSON response is not an object")
        return parsed

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.client.post(self.url, json=body,
                                        headers=self._headers())
            session = response.headers.get("Mcp-Session-Id")
            if session:
                self.session_id = session
            return self._body(response)
        except MCPError:
            raise
        except Exception as exc:
            raise MCPError(f"MCP request failed: {type(exc).__name__}: {exc}") from exc

    def initialize(self) -> dict[str, Any]:
        if self._initialized:
            return {"jsonrpc": "2.0", "result": {"session": self.session_id}}
        result = self._post({
            "jsonrpc": "2.0", "id": self._next_id, "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "afterbell", "version": "0.1.0"},
            },
        })
        self._next_id += 1
        if "error" in result:
            raise MCPError(f"MCP initialize error: {result['error']}")
        # MCP clients acknowledge initialization before using tools. It is a
        # notification, so an empty 202 response is valid.
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._initialized = True
        return result

    def request(self, method: str, params: dict[str, Any] | None = None
                ) -> dict[str, Any]:
        if method != "initialize" and not self._initialized:
            self.initialize()
        body: dict[str, Any] = {
            "jsonrpc": "2.0", "id": self._next_id, "method": method,
            "params": params or {},
        }
        result = self._post(body)
        self._next_id += 1
        if "error" in result:
            raise MCPError(f"MCP {method} error: {result['error']}")
        return result

    def tools_list(self) -> dict[str, Any]:
        return self.request("tools/list")

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})
