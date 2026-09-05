"""AFTERBELL as an MCP server: a peer on the protocol, not an adapter.

Consuming Agent OS makes AFTERBELL a client of Binance. Serving MCP makes it
something else: any agent, in any client, can connect to Binance's MCP server
and this one at the same time, and has to ask permission before it acts. The
guard stops being a component of one project and becomes a boundary anyone can
put in front of their own.

Two tools, both read-only:

    evaluate_order(symbol, side, notional, query)  -> the full decision
    get_market_state(symbol)                       -> state, REFERENCE_AGE,
                                                      basis, liquidity ratio

No authentication and no credential, which is the point and is also consistent
with the central claim of this repository: nothing in it can trade. The worst a
caller can do here is learn that their order would be refused.

Law 4 still applies. Evaluations served over MCP are receipted like every
other evaluation, tagged with their source, so a decision a judge triggers from
their own client appears in the same hash-chained ledger as the rest.

Transport is Streamable HTTP: a single POST endpoint speaking JSON-RPC 2.0,
answering with plain JSON rather than an SSE stream. That is the simplest
conformant shape, it needs no dependency outside the standard library, and it
sits behind the nginx that already terminates TLS for the dashboard.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from afterbell.clock import format_age
from afterbell.engine import Guard
from afterbell.guard import OrderRequest
from afterbell.measure import Side
from afterbell.policy import load as load_policy

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "afterbell", "version": "0.1.0"}
MAX_BODY = 64 * 1024

# JSON-RPC codes. -32000 is the generic server error the spec reserves for
# implementation-defined failures.
PARSE_ERROR, INVALID_REQUEST = -32700, -32600
METHOD_NOT_FOUND, INVALID_PARAMS, SERVER_ERROR = -32601, -32602, -32000

TOOLS = [
    {
        "name": "evaluate_order",
        "description": (
            "Ask AFTERBELL whether an order against a Binance bStock is "
            "acceptable right now, given where the underlying US equity "
            "market is in its calendar. Returns PASS, WARN, REDUCE or BLOCK "
            "with the permitted size, the binding constraint, and every "
            "measurement behind it. This never places an order and cannot: "
            "the server holds no credential of any kind."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string",
                           "description": "Binance pair, e.g. NVDABUSDT"},
                "side": {"type": "string", "enum": ["BUY", "SELL"]},
                "notional": {"type": "number",
                             "description": "Requested size in USDT"},
                "query": {"type": "string",
                          "description": "The request in the words the user "
                                         "actually used, e.g. 'buy Nvidia'"},
            },
            "required": ["symbol", "notional"],
        },
    },
    {
        "name": "get_market_state",
        "description": (
            "Where the reference market is in its calendar right now, how old "
            "the last regular-session print is, and how the token is trading "
            "against it. Read-only."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "default": "NVDABUSDT"},
            },
        },
    },
]


class ToolError(RuntimeError):
    """A bad request from the caller, reported as a tool error not a crash."""


# Baselines are medians over a rolling window of every recorded book, and
# building them scans the whole raw archive. Measured at 32.8s per call on this
# box, which is slower than a judge's client will wait, so one Guard is held and
# its baselines are rebuilt on a timer instead of on every request.
#
# The policy is still re-read and re-checksummed on every call, because that is
# cheap and because a server up for days must not be running yesterday's
# limits. A changed checksum rebuilds the Guard immediately.
BASELINE_TTL_S = 900
_GUARD: Guard | None = None
_GUARD_BUILT_AT = 0.0
_GUARD_LOCK = threading.Lock()


def _guard() -> Guard:
    global _GUARD, _GUARD_BUILT_AT
    pol = load_policy()
    now = time.monotonic()
    with _GUARD_LOCK:
        stale = (_GUARD is None
                 or _GUARD.policy.sha256 != pol.sha256
                 or now - _GUARD_BUILT_AT > BASELINE_TTL_S)
        if stale:
            _GUARD = Guard(pol)
            _GUARD_BUILT_AT = now
        return _GUARD


def evaluate_order(args: dict[str, Any]) -> dict[str, Any]:
    symbol = str(args.get("symbol") or "").upper().strip()
    if not symbol:
        raise ToolError("symbol is required")
    try:
        notional = float(args["notional"])
    except (KeyError, TypeError, ValueError):
        raise ToolError("notional must be a number in USDT") from None
    if notional <= 0:
        raise ToolError("notional must be positive")
    side = str(args.get("side") or "BUY").upper()
    if side not in ("BUY", "SELL"):
        raise ToolError("side must be BUY or SELL")

    guard = _guard()
    req = OrderRequest(symbol, Side(side), notional,
                       query=str(args.get("query") or symbol),
                       evaluation_source="mcp_server")
    d = guard.evaluate(req)
    ctx = d.context
    return {
        "verdict": d.verdict.value,
        "requested_notional": d.requested_notional,
        "permitted_notional": d.allowed_notional,
        "binding_constraint": d.binding_constraint,
        "rationale": d.rationale,
        "market_state": ctx.clock.state.value,
        "reference_age": (None if ctx.reference_age_s is None
                          else format_age(ctx.reference_age_s)),
        "reference_age_s": ctx.reference_age_s,
        "checks": {g.name: {"verdict": g.verdict.value, "detail": g.detail}
                   for g in d.gates},
        "policy_sha256": d.policy_sha256,
        "receipt_seq": (guard.last_receipt or {}).get("seq"),
        "receipt_hash": (guard.last_receipt or {}).get("hash"),
        "disclaimer": ("AFTERBELL evaluates; it never places an order. This "
                       "is a technical demonstration, not investment advice."),
    }


def get_market_state(args: dict[str, Any]) -> dict[str, Any]:
    symbol = str(args.get("symbol") or "NVDABUSDT").upper().strip()
    guard = _guard()
    # A nominal size, because the context is what is being asked for; the
    # decision it would produce is what evaluate_order is for.
    req = OrderRequest(symbol, Side.BUY, 1.0, query=symbol,
                       evaluation_source="mcp_server")
    ctx = guard.build_context(req)
    from afterbell.measure import basis_bps, depth_within, half_spread_bps
    book = ctx.book
    bl = ctx.baseline
    calibrated = bool(bl and bl.is_calibrated)
    return {
        "symbol": symbol,
        "market_state": ctx.clock.state.value,
        "seconds_to_next_open": ctx.clock.seconds_to_next_open,
        "extended_closure_ahead": ctx.clock.extended_closure_ahead,
        "reference_price": ctx.reference_price,
        "reference_age": (None if ctx.reference_age_s is None
                          else format_age(ctx.reference_age_s)),
        "reference_age_s": ctx.reference_age_s,
        "token_price": book.mid if book else None,
        "basis_bps": (basis_bps(book.mid, ctx.reference_price)
                      if book and ctx.reference_price else None),
        "half_spread_bps": half_spread_bps(book) if book else None,
        # Both ratios are against this symbol's own RTH median, so 1.0 means
        # "as usual for this book". They are null, never a default, when the
        # baseline has not reached its sample minimum: an uncalibrated ratio
        # would be a number with nothing behind it.
        "spread_ratio": (bl.spread_ratio(half_spread_bps(book))
                         if calibrated and book else None),
        "liquidity_ratio": (
            bl.liquidity_ratio(depth_within(book, 1.0))
            if calibrated and book else None),
        "baseline_status": bl.status if bl else "UNAVAILABLE",
        "exchange_status": ctx.exchange_status,
    }


HANDLERS = {"evaluate_order": evaluate_order,
            "get_market_state": get_market_state}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    """One JSON-RPC message in, one response out. None means a notification."""
    if message.get("jsonrpc") != "2.0":
        return _error(message.get("id"), INVALID_REQUEST,
                      "jsonrpc must be '2.0'")
    method = message.get("method")
    mid = message.get("id")
    if mid is None:
        return None                      # a notification: acknowledged, silent

    if method == "initialize":
        return _ok(mid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": (
                "AFTERBELL is a read-only calendar-aware risk boundary for "
                "Binance bStocks. Call evaluate_order before acting on a "
                "bStock; it returns the size that is acceptable given where "
                "the underlying US market is in its calendar. It cannot place "
                "orders and holds no credential."),
        })
    if method == "ping":
        return _ok(mid, {})
    if method == "tools/list":
        return _ok(mid, {"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        fn = HANDLERS.get(name)
        if fn is None:
            return _error(mid, INVALID_PARAMS, f"unknown tool: {name}")
        try:
            result = fn(params.get("arguments") or {})
        except ToolError as exc:
            return _ok(mid, _tool_result(str(exc), is_error=True))
        except Exception as exc:                     # never serve a lie
            logging.getLogger("afterbell.mcp_server").exception("tool failed")
            return _ok(mid, _tool_result(
                f"{type(exc).__name__}: {exc}", is_error=True))
        return _ok(mid, _tool_result(
            json.dumps(result, indent=2, default=str), structured=result))
    return _error(mid, METHOD_NOT_FOUND, f"unknown method: {method}")


def _tool_result(text: str, *, structured: dict | None = None,
                 is_error: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {"content": [{"type": "text", "text": text}],
                           "isError": is_error}
    if structured is not None:
        out["structuredContent"] = structured
    return out


def _ok(mid: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code,
                                                   "message": message}}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, body: bytes,
              ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            return self._send(200, b"ok", "text/plain")
        # No server-initiated stream: everything this server says is a reply.
        self._send(405, json.dumps({"error": "POST JSON-RPC to this endpoint"}
                                   ).encode())

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._send(400, json.dumps(
                _error(None, PARSE_ERROR, "bad Content-Length")).encode())
        if length > MAX_BODY:
            return self._send(413, json.dumps(
                _error(None, INVALID_REQUEST, "request too large")).encode())
        raw = self.rfile.read(length)
        try:
            message = json.loads(raw or b"{}")
        except json.JSONDecodeError as exc:
            return self._send(400, json.dumps(
                _error(None, PARSE_ERROR, str(exc))).encode())

        if isinstance(message, list):        # a batch
            replies = [r for r in (handle(m) for m in message) if r is not None]
            if not replies:
                return self._send(202, b"")
            return self._send(200, json.dumps(replies, default=str).encode())

        if not isinstance(message, dict):
            return self._send(400, json.dumps(
                _error(None, INVALID_REQUEST, "message must be an object")
            ).encode())

        reply = handle(message)
        if reply is None:
            return self._send(202, b"")      # notification: accepted, no body
        self._send(200, json.dumps(reply, default=str).encode())

    def log_message(self, fmt, *args) -> None:
        logging.getLogger("afterbell.mcp_server").info(fmt, *args)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="AFTERBELL read-only MCP server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8200)
    a = ap.parse_args()
    # Build the baselines before the socket opens. Otherwise the first caller
    # after a restart pays the whole archive scan and times out, which would
    # most likely be a judge trying the URL for the first time.
    # Warm in the background rather than before binding. Building the
    # baselines scans the whole raw archive and takes ~35s from a cold page
    # cache; doing that before the socket opens meant every request in that
    # window got a 502 from nginx. Serving first means an early caller waits on
    # the same lock the warmup holds and gets a real answer instead.
    #
    # get_market_state rather than an evaluation, so starting the server does
    # not write a receipt for an order nobody asked about. It also warms DNS,
    # the TLS handshakes and the depth fetch, which together were the larger
    # half of a 39s first call over HTTPS.
    def warm() -> None:
        started = time.monotonic()
        try:
            get_market_state({"symbol": "NVDABUSDT"})
            print(f"warm in {time.monotonic() - started:.1f}s", flush=True)
        except Exception as exc:              # a cold start is not a crash
            print(f"warmup incomplete after {time.monotonic() - started:.1f}s:"
                  f" {type(exc).__name__}: {exc}", flush=True)

    threading.Thread(target=warm, name="warmup", daemon=True).start()
    print(f"AFTERBELL MCP server on http://{a.host}:{a.port}", flush=True)
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
