"""AFTERBELL dashboard.

Part IX: REFERENCE_AGE is on the screen permanently, refusals are styled as
prominently as passes, and the policy checksum and ledger head are shown so a
reader can tell which rules produced what they are looking at.

Read-only and unauthenticated, like the recorder. It serves what has been
measured; it never computes a verdict of its own.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from afterbell import baselines as bl
from afterbell.clock import (
    MarketState, evaluate as clock_at, format_age, last_rth_close,
)
from afterbell.instruments import REGISTRY, TOKEN_SYMBOLS, registry_sha256
from afterbell.ledger import head_of
from afterbell.measure import (Book, Side, basis_bps, depth_within,
                               half_spread_bps, walk_cost_bps)
from afterbell.measure import BookProblem
from afterbell.policy import load as load_policy
from afterbell.dashboard_console import PAGE as CONSOLE_PAGE

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
RECEIPTS = ROOT / "data" / "receipts.jsonl"
GUARD_STATE = ROOT / "data" / "guard_state.json"
CALIBRATION = ROOT / "docs" / "calibration.md"
EVALUATION = ROOT / "docs" / "evaluation.md"
BACKUP_STATUS = ROOT / "data" / "backup_status.json"

STATE_CACHE_TTL_S = 300.0
_cache: dict = {"ts": 0.0, "data": None, "building": False}
_lock = threading.Lock()


def _tail_records(path: Path, limit: int) -> list[dict]:
    """Read complete JSONL records from the end without scanning a hot archive."""
    if limit <= 0:
        return []
    block = 1024 * 1024
    with path.open("rb") as fh:
        fh.seek(0, 2)
        pos = fh.tell()
        chunks = []
        newline_count = 0
        while pos > 0 and newline_count <= limit:
            size = min(block, pos)
            pos -= size
            fh.seek(pos)
            chunk = fh.read(size)
            chunks.append(chunk)
            newline_count += chunk.count(b"\n")
        data = b"".join(reversed(chunks))
    lines = data.splitlines()
    if pos > 0 and lines:
        lines = lines[1:]
    rows = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _latest_records() -> dict[str, dict]:
    """Most recent recorded book per symbol."""
    out: dict[str, dict] = {}
    for path in sorted(RAW.glob("*/token.jsonl"))[-2:]:
        for row in _tail_records(path, 100):
            if isinstance(row.get("symbol"), str):
                out[row["symbol"]] = row
    return out


def _latest_references() -> dict[str, dict]:
    """Most recent valid derived reference per underlying."""
    out: dict[str, dict] = {}
    for path in sorted(RAW.glob("*/reference.jsonl"))[-3:]:
        for row in _tail_records(path, 200):
            derived = row.get("derived")
            if not isinstance(derived, dict):
                continue
            for underlying, value in derived.items():
                if not isinstance(value, dict):
                    continue
                if not isinstance(value.get("price"), (int, float)) \
                        or not isinstance(value.get("ts"), str):
                    continue
                out[underlying] = {
                    "price": float(value["price"]), "ts": value["ts"],
                    "provider": value.get("provider"),
                    "source": value.get("source"),
                }
    return out


def _history(symbol: str, underlying: str, limit: int = 240) -> list[dict]:
    """Build the chart from receipted measurements, not full-depth raw books."""
    del underlying  # retained in the call signature for compatibility
    points: list[dict] = []
    for row in _tail_records(RECEIPTS, max(limit * 6, limit)):
        if row.get("symbol") != symbol:
            continue
        measured = row.get("measurements")
        if not isinstance(measured, dict):
            continue
        basis = measured.get("basis_bps")
        reference_age = measured.get("reference_age_s")
        if not isinstance(basis, (int, float)) \
                or not isinstance(reference_age, (int, float)):
            continue
        if not isinstance(row.get("ts"), str):
            continue
        points.append({
            "ts": row["ts"],
            "basis_bps": float(basis),
            "reference_age_s": float(reference_age),
        })
    points.sort(key=lambda point: point["ts"])
    if len(points) <= limit:
        return points
    stride = (len(points) - 1) / (limit - 1)
    return [points[round(i * stride)] for i in range(limit)]


def _load_guard_state() -> dict:
    if not GUARD_STATE.exists():
        return {"status": "STARTING", "allowed_notional": None,
                "note": "guard evaluator has not written a state yet"}
    try:
        state = json.loads(GUARD_STATE.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "UNKNOWN", "allowed_notional": None,
                "note": f"guard state unreadable: {type(exc).__name__}: {exc}"}
    if not isinstance(state, dict):
        return {"status": "UNKNOWN", "allowed_notional": None,
                "note": "guard state is not an object"}
    return state


def _calibration_text() -> str:
    if not CALIBRATION.exists():
        return "Calibration has not been generated yet."
    try:
        return CALIBRATION.read_text()
    except OSError as exc:
        return f"Calibration unavailable: {type(exc).__name__}: {exc}"


def _evaluation_metrics() -> dict[str, str]:
    """Read the generated evidence table without recomputing its claims."""
    if not EVALUATION.exists():
        return {}
    try:
        lines = EVALUATION.read_text().splitlines()
    except OSError:
        return {}
    metrics: dict[str, str] = {}
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [
            cell.strip().replace("**", "")
            for cell in line.split("|")[1:-1]
        ]
        if len(cells) != 2 or cells[0] in {"Metric", "---"}:
            continue
        metrics[cells[0]] = cells[1]
    return metrics


def _backup_state() -> dict:
    """Expose only the non-secret backup status receipt."""
    unknown = {"status": "UNKNOWN", "ts": None, "covered_through": None}
    if not BACKUP_STATUS.exists():
        return unknown
    try:
        state = json.loads(BACKUP_STATUS.read_text())
    except (OSError, json.JSONDecodeError):
        return unknown
    return state if isinstance(state, dict) else unknown


def _receipts(limit: int = 40) -> list[dict]:
    if not RECEIPTS.exists():
        return []
    return _tail_records(RECEIPTS, limit)[::-1]



_PUBLIC_CHECK_NAMES = (
    "Market timing", "Liquidity", "Price agreement", "Corporate actions",
    "Instrument identity", "Contract address", "Account exposure",
)
_PUBLIC_DECISIONS = {
    "PASS": "Clear", "WARN": "Caution", "REDUCE": "Smaller size",
    "BLOCK": "Blocked", "OK": "Healthy", "FAILED": "Failed",
    "STALE": "Stale", "PENDING": "Not ready", "TRADING": "Trading",
    "HALT": "Paused", "FILLED": "Filled", "UNKNOWN": "Unknown",
    "OPERATOR_FREEZE": "Operator freeze",
}
_PUBLIC_STATES = {
    "RTH_OPEN": "Open", "RTH_PRE": "Before open", "RTH_POST": "After close",
    "CLOSED_OVERNIGHT": "Overnight closure", "CLOSED_WEEKEND": "Weekend closure",
    "CLOSED_HOLIDAY": "Market holiday", "HALTED": "Trading paused",
    "UNKNOWN": "Unknown",
}
_PUBLIC_WORDS = {
    "UNCALIBRATED": "not yet approved", "CALIBRATED": "data complete",
    "REQUIRED_BUT_MISSING": "required account report missing",
    "NOT_SUPPLIED": "not provided", "NOT_APPLICABLE": "not applicable",
    "RTH_OPEN": "regular trading hours", "RTH_PRE": "before the regular open",
    "RTH_POST": "after the regular close", "CLOSED_WEEKEND": "weekend closure",
    "CLOSED_HOLIDAY": "market holiday", "CLOSED_OVERNIGHT": "overnight closure",
    "OPERATOR_FREEZE": "operator freeze", "TRADING": "trading",
    "VERIFIED": "verified", "DEGRADED": "elevated", "BROKEN": "blocked",
    "WATCH": "caution", "NOMINAL": "normal",
}


def _public_word(value: object, checks: list[str] | None = None) -> object:
    if not isinstance(value, str):
        return value
    text = value
    if checks and len(checks) == len(_PUBLIC_CHECK_NAMES):
        for key, label in zip(checks, _PUBLIC_CHECK_NAMES):
            text = text.replace(key, label)
    for old, new in _PUBLIC_WORDS.items():
        text = text.replace(old, new)
    for old, new in _PUBLIC_DECISIONS.items():
        text = text.replace(old, new)
    return text


def _public_state(data: dict) -> dict:
    """Remove machine labels at the public dashboard/API boundary."""
    public = dict(data)
    raw_guard = dict(data.get("guard") or {})
    raw_checks = dict(raw_guard.get("gates") or {})
    raw_details = dict(raw_guard.get("gate_detail") or {})
    check_keys = list(raw_checks)
    guard = dict(raw_guard)
    guard.pop("gates", None)
    guard.pop("gate_detail", None)
    guard.pop("binding_constraint", None)
    guard["status"] = _PUBLIC_DECISIONS.get(raw_guard.get("status"), "Unknown")
    guard["main_reason"] = _public_word(raw_guard.get("binding_constraint"), check_keys)
    guard["rationale"] = _public_word(raw_guard.get("rationale"), check_keys)
    guard["note"] = _public_word(raw_guard.get("note"), check_keys)
    guard["market_state"] = _PUBLIC_STATES.get(
        raw_guard.get("market_state"), "Unknown")
    guard["checks"] = [
        {"name": (_PUBLIC_CHECK_NAMES[i] if i < len(_PUBLIC_CHECK_NAMES)
                   else "Safety check"),
         "status": _PUBLIC_DECISIONS.get(status, "Unknown"),
         "detail": _public_word(raw_details.get(key, "No recorded detail"),
                                check_keys)}
        for i, (key, status) in enumerate(raw_checks.items())
    ]
    measurements = dict(guard.get("measurements") or {})
    for key, value in list(measurements.items()):
        measurements[key] = _public_word(value, check_keys)
    guard["measurements"] = measurements
    public["guard"] = guard

    raw_policy = dict(data.get("policy") or {})
    policy = dict(raw_policy)
    policy["safety_limits_ready"] = raw_policy.get("status") == "CALIBRATED"
    policy.pop("status", None)
    public["policy"] = policy

    symbols = []
    for row in data.get("symbols") or []:
        item = dict(row)
        item["status"] = _PUBLIC_DECISIONS.get(item.get("status"), "Unknown")
        item["baseline_ready"] = item.pop("baseline_status", "") == "CALIBRATED"
        by_state = item.pop("n_by_state", {}) or {}
        item["holiday_samples"] = by_state.get("CLOSED_HOLIDAY", 0)
        symbols.append(item)
    public["symbols"] = symbols

    receipts = []
    for row in data.get("receipts") or []:
        item = dict(row)
        item["decision"] = _PUBLIC_DECISIONS.get(item.get("decision"), "Unknown")
        item["rationale"] = _public_word(item.get("rationale"), check_keys)
        raw_factors = item.pop("gate_factors", {}) or {}
        item.pop("gate_detail", None)
        item.pop("binding_constraint", None)
        item["check_factors"] = [
            {"name": (_PUBLIC_CHECK_NAMES[i] if i < len(_PUBLIC_CHECK_NAMES)
                       else "Safety check"), "factor": factor}
            for i, factor in enumerate(raw_factors.values())
        ]
        receipts.append(item)
    public["receipts"] = receipts
    public["calibration_markdown"] = _public_word(
        data.get("calibration_markdown", ""), check_keys)

    clock = dict(data.get("clock") or {})
    clock["state"] = _PUBLIC_STATES.get(clock.get("state"), "Unknown")
    public["clock"] = clock
    public["build_status"] = ("Loading" if data.get("build_status") == "WARMING"
                               else "Ready")
    backup = dict(data.get("backup") or {})
    backup["status"] = _PUBLIC_DECISIONS.get(backup.get("status"), "Unknown")
    public["backup"] = backup
    acceptance = dict(data.get("acceptance") or {})
    acceptance["status"] = _PUBLIC_DECISIONS.get(
        acceptance.get("status"), acceptance.get("status", "Unknown"))
    public["acceptance"] = acceptance
    public.pop("reference_age_source", None)
    return public

def _published_baselines(min_samples: int) -> dict[str, bl.Baseline]:
    """Load the generated calibration table used by the public dashboard."""
    by_symbol: dict[str, dict] = {}
    try:
        lines = CALIBRATION.read_text().splitlines()
    except OSError:
        return {}
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [cell.strip().replace(",", "")
                 for cell in line.split("|")[1:-1]]
        if len(cells) < 5 or cells[0] not in TOKEN_SYMBOLS:
            continue
        symbol, state = cells[0], cells[1]
        try:
            count = int(cells[2])
            spread = float(cells[3])
            depth = float(cells[4])
        except ValueError:
            continue
        acc = by_symbol.setdefault(symbol, {"n_by_state": {}})
        acc["n_by_state"][state] = count
        if state == MarketState.RTH_OPEN.value:
            acc.update(n_rth=count, spread=spread, depth=depth)
    return {
        symbol: bl.Baseline(
            symbol=symbol,
            n_rth=int(values.get("n_rth", 0)),
            median_half_spread_bps=values.get("spread"),
            median_depth_1pct=values.get("depth"),
            n_by_state=values["n_by_state"],
            min_samples=min_samples,
        )
        for symbol, values in by_symbol.items()
    }


def build_state() -> dict:
    pol = load_policy()
    clock = clock_at()
    baselines = _published_baselines(pol.min_rth_samples)
    latest = _latest_records()
    references = _latest_references()

    symbols = []
    for sym in TOKEN_SYMBOLS:
        inst = REGISTRY[sym]
        rec = latest.get(sym)
        book = Book.from_record(rec) if rec else None
        base = baselines.get(sym)
        reference = references.get(inst.underlying)
        reference_age_s = None
        if reference is not None:
            try:
                ref_ts = datetime.fromisoformat(reference["ts"].replace("Z", "+00:00"))
                reference_age_s = (datetime.now(timezone.utc) -
                                   ref_ts.astimezone(timezone.utc)).total_seconds()
                if reference_age_s < 0:
                    reference_age_s = None
            except (KeyError, TypeError, ValueError):
                reference_age_s = None
        row = {
            "symbol": sym, "asset": inst.token_asset,
            "underlying": inst.underlying, "name": inst.underlying_name,
            "issuer": inst.issuer, "contract": inst.contract,
            "status": rec.get("status") if rec else None,
            "observed_at": rec.get("ts") if rec else None,
            "mid": None, "half_spread_bps": None, "depth_1pct": None,
            "walk_5k_bps": None, "spread_ratio": None, "liquidity_ratio": None,
            "reference_price": reference.get("price") if reference else None,
            "reference_ts": reference.get("ts") if reference else None,
            "reference_age_s": reference_age_s,
            "basis_bps": None,
            "baseline_status": base.status if base else "NO_DATA",
            "n_rth": base.n_rth if base else 0,
            "n_by_state": base.n_by_state if base else {},
        }
        if book is not None:
            hs = half_spread_bps(book)
            dp = depth_within(book, pol.depth_band_pct)
            row["mid"] = book.mid
            row["half_spread_bps"] = hs
            row["depth_1pct"] = dp
            if row["reference_price"] is not None:
                row["basis_bps"] = basis_bps(book.mid, row["reference_price"])
            w = walk_cost_bps(book, 5000.0, Side.BUY)
            row["walk_5k_bps"] = (None if isinstance(w, BookProblem)
                                  else w.cost_bps)
            if base and base.is_calibrated and hs is not None and dp is not None:
                row["spread_ratio"] = base.spread_ratio(hs)
                row["liquidity_ratio"] = base.liquidity_ratio(dp)
        symbols.append(row)

    # Law 8: show the age of the actual recorded regular-session reference.
    # The calendar is still exposed separately in `clock`; it never becomes a
    # substitute for a missing price feed.
    now = datetime.now(timezone.utc)
    primary = next((s for s in symbols if s["underlying"] == "NVDA"), None)
    ref_age_s = primary["reference_age_s"] if primary else None
    ref_source = ("recorded_reference" if ref_age_s is not None
                  else "missing_reference")

    return {
        "generated_at": now.isoformat(),
        "build_status": "READY",
        "reference_age_s": ref_age_s,
        "reference_age": format_age(ref_age_s),
        "reference_age_source": ref_source,
        "clock": {
            "state": clock.state.value,
            "seconds_to_next_open": clock.seconds_to_next_open,
            "hours_to_next_open": clock.hours_to_next_open,
            "next_open_utc": clock.next_open_utc.isoformat(),
            "holiday": clock.holiday,
            "extended_closure_ahead": clock.extended_closure_ahead,
            "seconds_to_close": clock.seconds_to_close,
        },
        "policy": {"sha256": pol.sha256, "status": pol.status,
                   "base_notional": pol.base_notional,
                   "min_rth_samples": pol.min_rth_samples,
                   "executor_enabled": pol.executor_enabled,
                   "require_snapshot": pol.exposure_requires_snapshot,
                   "max_gross_usdt": pol.exposure_max_gross_usdt},
        "registry_sha256": registry_sha256(),
        "ledger_head": head_of(RECEIPTS),
        "guard": _load_guard_state(),
        "history": _history("NVDABUSDT", "NVDA"),
        "calibration_markdown": _calibration_text(),
        "evaluation": _evaluation_metrics(),
        "backup": _backup_state(),
        "acceptance": {
            "status": "FILLED", "order_id": "54422149",
            "quantity": "0.021 NVDAB", "notional": "4.86192000 USDT",
            "boundary": "Codex MCP OAuth; no venue credential in Python",
        },
        "symbols": symbols,
        "receipts": _receipts(),
    }


def _starting_state() -> dict:
    """Return a truthful lightweight response while the archive is indexed."""
    now = datetime.now(timezone.utc)
    note = ("Dashboard is warming: the full recorded history is being indexed.")
    try:
        pol = load_policy()
        policy = {
            "sha256": pol.sha256,
            "status": pol.status,
            "base_notional": pol.base_notional,
            "min_rth_samples": pol.min_rth_samples,
            "executor_enabled": pol.executor_enabled,
            "require_snapshot": pol.exposure_requires_snapshot,
            "max_gross_usdt": pol.exposure_max_gross_usdt,
        }
    except Exception as exc:
        policy = {
            "sha256": None,
            "status": "UNKNOWN",
            "base_notional": None,
            "min_rth_samples": None,
        }
        note = f"Dashboard warming; policy unavailable: {type(exc).__name__}: {exc}"
    clock = clock_at()
    return {
        "generated_at": now.isoformat(),
        "build_status": "WARMING",
        "build_note": note,
        "reference_age_s": None,
        "reference_age": None,
        "reference_age_source": "warming",
        "clock": {
            "state": clock.state.value,
            "seconds_to_next_open": clock.seconds_to_next_open,
            "hours_to_next_open": clock.hours_to_next_open,
            "next_open_utc": clock.next_open_utc.isoformat(),
            "holiday": clock.holiday,
            "extended_closure_ahead": clock.extended_closure_ahead,
            "seconds_to_close": clock.seconds_to_close,
        },
        "policy": policy,
        "registry_sha256": registry_sha256(),
        "ledger_head": None,
        "guard": _load_guard_state(),
        "history": [],
        "calibration_markdown": _calibration_text(),
        "evaluation": _evaluation_metrics(),
        "backup": _backup_state(),
        "acceptance": {
            "status": "RECORDED", "order_id": "54422149",
            "quantity": "0.021 NVDAB", "notional": "4.86192000 USDT",
            "boundary": "Codex MCP OAuth; no venue credential in Python",
        },
        "symbols": [],
        "receipts": _receipts(),
    }


def _refresh_state() -> None:
    """Build one full state snapshot outside the HTTP request thread."""
    try:
        data = build_state()
    except Exception:
        logging.getLogger("afterbell.dashboard").exception(
            "dashboard state build failed")
        with _lock:
            _cache["building"] = False
        return
    with _lock:
        _cache["data"] = data
        _cache["ts"] = time.time()
        _cache["building"] = False


def _start_refresh() -> None:
    with _lock:
        if _cache["building"]:
            return
        _cache["building"] = True
    threading.Thread(target=_refresh_state, name="dashboard-refresh",
                     daemon=True).start()


def cached_state(max_age_s: float = STATE_CACHE_TTL_S) -> dict:
    """Serve the last good state while a slow archive refresh runs."""
    with _lock:
        data = _cache["data"]
        stale = (data is None
                 or time.time() - _cache["ts"] > max_age_s)
    if stale:
        _start_refresh()
    if data is None:
        return _starting_state()
    if "generated_at" not in data:
        return data
    return dict(data, guard=_load_guard_state(), receipts=_receipts(),
                backup=_backup_state(), ledger_head=head_of(RECEIPTS))


PAGE = CONSOLE_PAGE


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, body: bytes, ctype: str, *, write_body: bool = True) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if write_body:
            self.wfile.write(body)

    def do_HEAD(self) -> None:
        if self.path == "/healthz":
            return self._send(200, b"ok", "text/plain", write_body=False)
        if self.path in ("/", "/index.html"):
            return self._send(200, PAGE.encode(), "text/html; charset=utf-8", write_body=False)
        self._send(404, b"not found", "text/plain", write_body=False)

    def do_GET(self) -> None:
        try:
            if self.path.startswith("/api/state"):
                body = json.dumps(_public_state(cached_state()), default=str).encode()
                return self._send(200, body, "application/json")
            if self.path in ("/", "/index.html"):
                return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            if self.path == "/healthz":
                return self._send(200, b"ok", "text/plain")
            self._send(404, b"not found", "text/plain")
        except Exception as exc:                      # never serve a lie
            self._send(500, json.dumps({"error": str(exc)}).encode(),
                       "application/json")

    def log_message(self, fmt, *args) -> None:
        logging.getLogger("afterbell.dashboard").info(fmt, *args)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    _start_refresh()
    print(f"AFTERBELL dashboard on http://{a.host}:{a.port}", flush=True)
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
