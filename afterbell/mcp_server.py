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

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from afterbell.clock import format_age
from afterbell.engine import Guard
from afterbell.guard import CHECK_NAMES, OrderRequest
from afterbell.positions import PositionSnapshotError, parse as parse_position_snapshot
from afterbell.measure import Side
from afterbell.policy import Policy, load as load_policy

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "afterbell", "version": "0.1.0"}
MAX_BODY = 64 * 1024
MAX_BATCH_MESSAGES = 20

# The reverse proxy applies the first rate limit by public source address. The
# application repeats the bound because this service can also be reached by a
# local client, and because a batch must pay for every message it contains.
# The daily counter is persisted so a service restart cannot reset the bound
# on MCP-originated receipt growth. The monitor's own receipts are not subject
# to this quota; its fixed service cadence is a separate operational concern.
MCP_RATE_WINDOW_S = 60
MCP_MAX_RATE_UNITS = 30
MCP_DAILY_EVALUATION_LIMIT = 1000
MCP_QUOTA_PATH = (Path(__file__).resolve().parent.parent
                  / "data" / "mcp-quota.json")

# JSON-RPC codes. -32000 is the generic server error the spec reserves for
# implementation-defined failures.
PARSE_ERROR, INVALID_REQUEST = -32700, -32600
METHOD_NOT_FOUND, INVALID_PARAMS, SERVER_ERROR = -32601, -32602, -32000
QUOTA_EXCEEDED = -32029

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
                "position_snapshot": {
                    "type": "object",
                    "description": (
                        "Signed supported-client account positions in USDT; "
                        "required when the policy requires D5 evidence."),
                    "properties": {
                        "as_of": {"type": "string"},
                        "positions": {"type": "object"},
                        "source": {"type": "string"},
                        "signature": {"type": "string"},
                    },
                    "required": ["as_of", "positions", "source", "signature"],
                },
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


@dataclass(frozen=True)
class QuotaDecision:
    """The result of reserving bounded MCP work."""

    allowed: bool
    reason: str = ""
    retry_after_s: int = 0


class QuotaStoreError(RuntimeError):
    """The persistent quota state is unavailable or invalid."""


class MCPQuota:
    """Bound MCP work without putting limits into the safety policy.

    request_units limits expensive protocol work in a short window;
    evaluations reserves the durable daily budget for calls that will write
    a decision receipt. The quota is reserved before a handler runs, so a
    caller cannot spend the budget by sending a large batch or by repeatedly
    provoking an evaluation failure.

    Only the global daily count is persisted. Per-client rate state is bounded
    in memory and the public nginx layer supplies the source-address limit;
    this keeps the quota file small even if many distinct clients connect.
    """

    def __init__(self, path: str | Path = MCP_QUOTA_PATH, *,
                 rate_window_s: int = MCP_RATE_WINDOW_S,
                 max_rate_units: int = MCP_MAX_RATE_UNITS,
                 daily_evaluation_limit: int = MCP_DAILY_EVALUATION_LIMIT,
                 max_clients: int = 4096) -> None:
        if rate_window_s <= 0 or max_rate_units <= 0:
            raise ValueError("MCP rate limits must be positive")
        if daily_evaluation_limit < 0 or max_clients <= 0:
            raise ValueError("MCP quota limits are invalid")
        self.path = Path(path)
        self.rate_window_s = int(rate_window_s)
        self.max_rate_units = int(max_rate_units)
        self.daily_evaluation_limit = int(daily_evaluation_limit)
        self.max_clients = int(max_clients)
        self._lock = threading.Lock()
        # fingerprint -> (window_start, used_units), kept bounded below.
        self._clients: OrderedDict[str, tuple[int, int]] = OrderedDict()

    @staticmethod
    def _fingerprint(client_key: str) -> str:
        # The quota artifact does not need to retain caller IP addresses.
        return hashlib.sha256(client_key.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _day(now: float) -> str:
        return datetime.fromtimestamp(now, timezone.utc).date().isoformat()

    def _retry_after_window(self, now: float) -> int:
        end = (int(now // self.rate_window_s) + 1) * self.rate_window_s
        return max(1, int(end - now + 0.999999))

    @staticmethod
    def _retry_after_day(now: float) -> int:
        current = datetime.fromtimestamp(now, timezone.utc)
        tomorrow = datetime.combine(
            current.date() + timedelta(days=1), datetime.min.time(),
            tzinfo=timezone.utc)
        return max(1, int(tomorrow.timestamp() - now + 0.999999))

    def _read_daily_count(self, day: str) -> int:
        if not self.path.exists():
            return 0
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise QuotaStoreError(
                f"MCP quota state could not be read: {exc}") from exc
        if (not isinstance(raw, dict)
                or set(raw) != {"day", "evaluations"}
                or not isinstance(raw.get("day"), str)
                or type(raw.get("evaluations")) is not int
                or raw["evaluations"] < 0):
            raise QuotaStoreError("MCP quota state is malformed")
        if raw["day"] != day:
            return 0
        return raw["evaluations"]

    def _write_daily_count(self, day: str, count: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as fh:
                json.dump({"day": day, "evaluations": count}, fh,
                          sort_keys=True)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise QuotaStoreError(
                f"MCP quota state could not be written: {exc}") from exc

    def _reserve_rate(self, client_key: str, units: int,
                      now: float) -> tuple[bool, int]:
        fingerprint = self._fingerprint(client_key)
        window = int(now // self.rate_window_s)
        previous = self._clients.get(fingerprint)
        used = previous[1] if previous and previous[0] == window else 0
        if used + units > self.max_rate_units:
            return False, self._retry_after_window(now)
        self._clients[fingerprint] = (window, used + units)
        self._clients.move_to_end(fingerprint)
        while len(self._clients) > self.max_clients:
            self._clients.popitem(last=False)
        return True, 0

    def admit(self, client_key: str, *, request_units: int,
              evaluations: int, now: float | None = None) -> QuotaDecision:
        """Reserve one HTTP request before dispatching it.

        evaluations is deliberately separate from request_units:
        get_market_state consumes rate budget but does not grow the
        receipt ledger, while one batch may consume many daily evaluations.
        """
        if request_units <= 0 or evaluations < 0:
            raise ValueError("MCP quota reservation values are invalid")
        now = time.time() if now is None else float(now)
        with self._lock:
            allowed, retry = self._reserve_rate(
                str(client_key or "unknown"), int(request_units), now)
            if not allowed:
                return QuotaDecision(
                    False,
                    "MCP request rate exceeded; try again later",
                    retry)

            if evaluations:
                day = self._day(now)
                used = self._read_daily_count(day)
                if used + evaluations > self.daily_evaluation_limit:
                    return QuotaDecision(
                        False,
                        "daily MCP evaluation quota exhausted; try after "
                        "the next UTC midnight",
                        self._retry_after_day(now))
                # Reserve before dispatch. A failed evaluation therefore
                # cannot be retried indefinitely without consuming quota.
                self._write_daily_count(day, used + evaluations)
            return QuotaDecision(True)


def _tool_name(message: Any) -> str | None:
    if not isinstance(message, dict) or message.get("method") != "tools/call":
        return None
    params = message.get("params")
    return params.get("name") if isinstance(params, dict) else None


def _evaluation_count(message: Any) -> int:
    """Count receipt-writing calls in a single message or batch."""
    messages = message if isinstance(message, list) else [message]
    return sum(1 for item in messages
               if isinstance(item, dict)
               and item.get("id") is not None
               and _tool_name(item) == "evaluate_order")


def _request_units(message: Any) -> int:
    """Charge at least one unit, and charge every item in a batch."""
    return max(1, len(message)) if isinstance(message, list) else 1


_QUOTA = MCPQuota()


# Baselines are medians over a rolling window of every recorded book, and
# building them scans the whole raw archive. That scan is not a constant: it
# was 32.8s per call when this server was written and 301.6s once the recorder
# moved to full-depth books, because the cost grows with the archive. Any
# design that makes a caller wait for it therefore fails eventually rather than
# immediately, and it failed here as a 504 from nginx on every tool call.
#
# So a rebuild never happens on the request path. One Guard is held and served;
# when it ages out, the caller that notices starts a background rebuild and is
# answered from the Guard already in hand. Requests stay fast whatever the
# archive costs to scan.
#
# The policy is still re-read and re-checksummed on every call, because that is
# cheap and because a server up for days must not be running yesterday's
# limits. A changed checksum cannot be served from the old Guard, so that case
# refuses and rebuilds rather than answering under limits nobody chose (Law 3).
BASELINE_TTL_S = 3600
_GUARD: Guard | None = None
_GUARD_BUILT_AT = 0.0
_GUARD_LOCK = threading.Lock()          # guards the reference, never a build
_REFRESHING = False


def _refresh(pol: Policy) -> Guard:
    """Build a Guard and publish it. Slow; never call holding _GUARD_LOCK."""
    global _GUARD, _GUARD_BUILT_AT, _REFRESHING
    try:
        guard = Guard(pol)
        with _GUARD_LOCK:
            _GUARD, _GUARD_BUILT_AT = guard, time.monotonic()
        return guard
    finally:
        with _GUARD_LOCK:
            _REFRESHING = False


def _guard() -> Guard:
    """The current Guard, without ever waiting for an archive scan."""
    global _REFRESHING
    pol = load_policy()
    with _GUARD_LOCK:
        current, built = _GUARD, _GUARD_BUILT_AT
        changed = current is not None and current.policy.sha256 != pol.sha256
        expired = current is not None and time.monotonic() - built > BASELINE_TTL_S
        start = (current is None or changed or expired) and not _REFRESHING
        if start:
            _REFRESHING = True

    if current is None:
        # Cold start: there is nothing to serve. The first caller builds; any
        # caller arriving during that build is told to retry rather than left
        # to hang on the lock until nginx gives up on it.
        if start:
            return _refresh(pol)
        raise ToolError("baselines are still being built from the recorded "
                        "archive; retry in a moment")

    if start:
        threading.Thread(target=_refresh, args=(pol,), daemon=True,
                         name="baseline-refresh").start()
    if changed:
        raise ToolError("the safety settings changed and the baselines are "
                        "being rebuilt under them; retry in a moment")
    return current


def evaluate_order(args: dict[str, Any]) -> dict[str, Any]:
    symbol = str(args.get("symbol") or "").upper().strip()
    if not symbol:
        raise ToolError("symbol is required")
    position_snapshot = None
    if args.get("position_snapshot") is not None:
        try:
            position_snapshot = parse_position_snapshot(args["position_snapshot"])
        except PositionSnapshotError as exc:
            raise ToolError(f"invalid position_snapshot: {exc}") from exc
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
    d = guard.evaluate(req, position_snapshot=position_snapshot)
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
        "binding_check": (None if not d.binding_constraint else
                          ", ".join(CHECK_NAMES.get(c, c) for c
                                    in d.binding_constraint.split(","))),
        "checks": {CHECK_NAMES.get(g.name, g.name): {
            "verdict": g.verdict.value, "detail": g.detail} for g in d.gates},
        "policy_sha256": d.policy_sha256,
        "receipt_seq": (guard.last_receipt or {}).get("seq"),
        "receipt_hash": (guard.last_receipt or {}).get("hash"),
        "policy_status": d.policy_status,
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


def handle(message: Any) -> dict[str, Any] | None:
    """One JSON-RPC message in, one response out. None means a notification."""
    if not isinstance(message, dict):
        return _error(None, INVALID_REQUEST, "message must be an object")
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
              ctype: str = "application/json",
              headers: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _client_key(self) -> str:
        # nginx overwrites X-Real-IP before proxying. The service is loopback
        # only, so a direct local caller cannot turn this into a public trust
        # boundary; the persisted global quota remains the hard bound.
        return (self.headers.get("X-Real-IP")
                or self.client_address[0]
                or "unknown").strip()

    def _quota_failure(self, message: Any, decision: QuotaDecision) -> None:
        error = lambda mid: _error(mid, QUOTA_EXCEEDED, decision.reason)
        if isinstance(message, list):
            replies = [error(item.get("id"))
                       for item in message
                       if isinstance(item, dict) and item.get("id") is not None]
            body = json.dumps(replies or [error(None)]).encode()
        else:
            mid = message.get("id") if isinstance(message, dict) else None
            body = json.dumps(error(mid)).encode()
        self._send(429, body, headers={
            "Retry-After": str(decision.retry_after_s)})

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
        if length < 0 or length > MAX_BODY:
            return self._send(413, json.dumps(
                _error(None, INVALID_REQUEST, "request too large")).encode())
        raw = self.rfile.read(length)
        try:
            message = json.loads(raw or b"{}")
        except json.JSONDecodeError as exc:
            return self._send(400, json.dumps(
                _error(None, PARSE_ERROR, str(exc))).encode())

        if isinstance(message, list) and len(message) > MAX_BATCH_MESSAGES:
            return self._send(413, json.dumps(_error(
                None, INVALID_REQUEST,
                f"batch exceeds {MAX_BATCH_MESSAGES} messages")).encode())
        if not isinstance(message, (dict, list)):
            return self._send(400, json.dumps(
                _error(None, INVALID_REQUEST, "message must be an object")
            ).encode())

        try:
            quota = _QUOTA.admit(
                self._client_key(),
                request_units=_request_units(message),
                evaluations=_evaluation_count(message))
        except QuotaStoreError:
            logging.getLogger("afterbell.mcp_server").exception(
                "MCP quota store unavailable")
            return self._send(503, json.dumps(_error(
                None, SERVER_ERROR,
                "MCP quota is unavailable; request refused")).encode())
        if not quota.allowed:
            return self._quota_failure(message, quota)

        if isinstance(message, list):        # a batch
            replies = [r for r in (handle(m) for m in message) if r is not None]
            if not replies:
                return self._send(202, b"")
            return self._send(200, json.dumps(replies, default=str).encode())

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
