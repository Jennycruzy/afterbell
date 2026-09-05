"""AFTERBELL market-data recorder.

Law 10: this process holds no credential for Binance, needs no account, and is
structurally incapable of dying from OAuth expiry. It is deliberately separate
from anything that authenticates.

Law 3: a failed fetch never becomes a fabricated value. Every hole in the data
is annotated with a gap marker carrying the reason, so a gap is visible rather
than invisible.

Law 2: no synthetic data of any kind. Every field written here came off the
wire from a live public endpoint.

Writes, per UTC day, under data/raw/YYYY-MM-DD/:
    token.jsonl      one record per symbol per cycle: book, depth, trades
    reference.jsonl  one record per cycle: provider snapshots + derived
                      regular-session references
    gaps.jsonl       one record per failure, with reason and endpoint
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx

from afterbell.instruments import TOKEN_SYMBOLS, UNDERLYINGS, registry_sha256
from afterbell.reference import (
    ReferenceUnavailable, from_snapshot, from_yahoo,
)

BINANCE = "https://api.binance.com"
ALPACA_DATA = "https://data.alpaca.markets"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart"
ALPACA_TRADE = "https://paper-api.alpaca.markets"

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "raw"
HEARTBEAT = ROOT / "data" / "heartbeat"

INTERVAL_S = 60
# The full book, not a window onto it. At 20 levels the ladder spanned only
# ~0.10% of mid on NVDABUSDT, so depth_1pct measured our own truncation rather
# than the +/-1% band, and any walk cost above ~$10k returned INSUFFICIENT_DEPTH
# against a book that was not actually exhausted. Measured 2026-09-03: these
# books hold 261-764 levels in total, so limit=5000 returns every one of them
# (17-41KB/symbol). Weight 250/call * 5 symbols = 1250/min against a 6000 budget.
DEPTH_LEVELS = 5000
# The same mistake as the 20-level depth truncation above, in a second place,
# and it survived the first fix because only the depth call was re-examined.
# At limit=50 a batch of SNDKBUSDT trades spanned 7.2s of a 60s cycle, so ~88%
# of that minute's prints were never seen, and the ones missed were the ones in
# bursts. Measured 2026-09-05: /api/v3/trades costs weight 25 per call at ANY
# limit up to 1000 - 50, 500 and 1000 each added exactly 25 to the running
# total - so the small request bought nothing. At limit=1000 every symbol's
# batch spans longer than the cycle that fetched it (159s on the busiest,
# SNDKBUSDT), which means consecutive batches overlap and the tape is complete.
# Costs 697KB/cycle across five symbols, ~1.0GB/day, against 40GB free.
TRADE_LIMIT = 1000
TIMEOUT = httpx.Timeout(15.0, connect=10.0)

_RESTRICTED = "restricted location"
_running = True


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _log(msg: str) -> None:
    print(f"[{_iso(_now())}] {msg}", file=sys.stderr, flush=True)


def _day_dir(dt: datetime) -> Path:
    d = DATA / dt.strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _append(dt: datetime, name: str, record: dict) -> None:
    path = _day_dir(dt) / f"{name}.jsonl"
    with path.open("a") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")


def _gap(dt: datetime, cycle: int, source: str, endpoint: str,
         reason: str, symbol: str | None = None) -> None:
    """Law 3: annotate the hole. Never fill it."""
    _append(dt, "gaps", {
        "kind": "gap", "ts": _iso(dt), "cycle": cycle, "source": source,
        "endpoint": endpoint, "symbol": symbol, "reason": reason[:500],
    })
    _log(f"GAP {source} {endpoint} {symbol or ''} :: {reason[:200]}")


def _check_restricted(text: str) -> bool:
    return _RESTRICTED in text.lower()


class Recorder:
    def __init__(self) -> None:
        self.client = httpx.Client(
            timeout=TIMEOUT,
            headers={"User-Agent": "afterbell-recorder/0.1"},
        )
        key = os.environ.get("ALPACA_API_KEY", "").strip()
        sec = os.environ.get("ALPACA_SECRET_KEY", "").strip()
        self.alpaca_headers = (
            {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}
            if key and sec else None
        )
        self.provider = os.environ.get(
            "REFERENCE_PROVIDER", "yahoo").strip().lower()
        if self.provider == "alpaca" and self.alpaca_headers is None:
            _log("ALPACA CREDENTIALS ABSENT - reference side will write gap "
                 "markers every cycle until they are supplied. Token side is "
                 "unaffected and records normally (Law 10).")
        elif self.provider != "alpaca":
            _log(f"reference provider: {self.provider} - no credential held "
                 "on either side of this recorder.")
        self.cycle = 0

    # ---------------- Binance: no credential, ever (Law 10) ----------------

    def _get_binance(self, path: str, params: dict, dt: datetime,
                     symbol: str | None = None):
        url = f"{BINANCE}{path}"
        try:
            r = self.client.get(url, params=params)
        except Exception as exc:
            _gap(dt, self.cycle, "binance", path, f"{type(exc).__name__}: {exc}", symbol)
            return None
        if _check_restricted(r.text):
            _gap(dt, self.cycle, "binance", path,
                 f"GEOBLOCK: {r.text[:300]}", symbol)
            return None
        if r.status_code != 200:
            _gap(dt, self.cycle, "binance", path,
                 f"HTTP {r.status_code}: {r.text[:300]}", symbol)
            return None
        try:
            return r.json()
        except Exception as exc:
            _gap(dt, self.cycle, "binance", path, f"bad json: {exc}", symbol)
            return None

    def exchange_status(self, dt: datetime) -> dict[str, str]:
        """Corporate-action source: authoritative trading status per pair."""
        # httpx URL-encodes params; pre-quoting here double-encodes and
        # Binance rejects it with -1100.
        syms = json.dumps(TOKEN_SYMBOLS, separators=(",", ":"))
        data = self._get_binance("/api/v3/exchangeInfo", {"symbols": syms}, dt)
        if not data or "symbols" not in data:
            return {}
        return {s["symbol"]: s["status"] for s in data["symbols"]}

    def record_token(self, dt: datetime, statuses: dict[str, str]) -> int:
        written = 0
        for sym in TOKEN_SYMBOLS:
            book = self._get_binance("/api/v3/ticker/bookTicker", {"symbol": sym}, dt, sym)
            depth = self._get_binance(
                "/api/v3/depth", {"symbol": sym, "limit": DEPTH_LEVELS}, dt, sym)
            trades = self._get_binance(
                "/api/v3/trades", {"symbol": sym, "limit": TRADE_LIMIT}, dt, sym)

            # Law 3: the book and the depth are the whole point. Without them
            # there is no measurement, so there is no record - only a gap.
            if book is None or depth is None:
                _gap(dt, self.cycle, "binance", "record_token",
                     "missing book or depth; no token record written", sym)
                continue
            if not depth.get("bids") or not depth.get("asks"):
                _gap(dt, self.cycle, "binance", "/api/v3/depth",
                     "empty book side", sym)
                continue

            _append(dt, "token", {
                "kind": "token", "ts": _iso(dt), "cycle": self.cycle,
                "symbol": sym,
                "status": statuses.get(sym),
                "bid": book.get("bidPrice"), "bid_qty": book.get("bidQty"),
                "ask": book.get("askPrice"), "ask_qty": book.get("askQty"),
                "depth_limit": DEPTH_LEVELS,
                "last_update_id": depth.get("lastUpdateId"),
                "bids": depth["bids"], "asks": depth["asks"],
                "trades": trades,
                "trades_ok": trades is not None,
            })
            written += 1
        return written

    # ---------------- Alpaca: reference side, read-only ----------------

    def _get_alpaca(self, base: str, path: str, params: dict, dt: datetime):
        if self.alpaca_headers is None:
            _gap(dt, self.cycle, "alpaca", path, "no credentials configured")
            return None
        try:
            r = self.client.get(f"{base}{path}", params=params,
                                headers=self.alpaca_headers)
        except Exception as exc:
            _gap(dt, self.cycle, "alpaca", path, f"{type(exc).__name__}: {exc}")
            return None
        if r.status_code != 200:
            _gap(dt, self.cycle, "alpaca", path,
                 f"HTTP {r.status_code}: {r.text[:300]}")
            return None
        try:
            return r.json()
        except Exception as exc:
            _gap(dt, self.cycle, "alpaca", path, f"bad json: {exc}")
            return None

    # ---------------- Yahoo: reference side, no credential ----------------

    def _get_yahoo(self, symbol: str, dt: datetime):
        try:
            r = self.client.get(f"{YAHOO_CHART}/{symbol}",
                                params={"range": "1d", "interval": "1d"})
        except Exception as exc:
            _gap(dt, self.cycle, "yahoo", symbol, f"{type(exc).__name__}: {exc}")
            return None
        if r.status_code != 200:
            _gap(dt, self.cycle, "yahoo", symbol,
                 f"HTTP {r.status_code}: {r.text[:300]}")
            return None
        try:
            return r.json()["chart"]["result"][0]["meta"]
        except Exception as exc:
            _gap(dt, self.cycle, "yahoo", symbol, f"bad json: {exc}")
            return None

    def record_reference_yahoo(self, dt: datetime) -> bool:
        """One record per cycle, five symbols, no credential.

        The raw `meta` block is stored alongside the derived price so a later
        reader can re-derive the reference without trusting this code, and can
        see a provider disagreeing with the calendar if it ever does.
        """
        metas, derived = {}, {}
        for sym in UNDERLYINGS:
            meta = self._get_yahoo(sym, dt)
            if meta is None:
                continue
            metas[sym] = meta
            try:
                # `dt` is the cycle start. Yahoo can publish a new regular
                # print while the five-symbol request is in flight, so validate
                # against the wall clock at this response rather than calling
                # a perfectly current print "future" by a few seconds.
                captured_at = datetime.now(timezone.utc)
                ref = from_yahoo(sym, meta, captured_at)
            except ReferenceUnavailable as exc:
                _gap(dt, self.cycle, "yahoo", sym, str(exc))
                continue
            derived[sym] = {"price": ref.price, "ts": _iso(ref.ts),
                            "source": ref.source, "provider": ref.provider,
                            "age_s": (captured_at - ref.ts).total_seconds()}
        if not metas:
            return False
        _append(dt, "reference", {
            "kind": "reference", "ts": _iso(dt), "cycle": self.cycle,
            "provider": "yahoo", "meta": metas, "derived": derived,
            "snapshots_ok": bool(metas),
            "derived_ok": len(derived) == len(UNDERLYINGS),
        })
        return True

    def record_reference(self, dt: datetime) -> bool:
        if self.provider != "alpaca":
            return self.record_reference_yahoo(dt)
        snap = self._get_alpaca(ALPACA_DATA, "/v2/stocks/snapshots",
                                {"symbols": ",".join(UNDERLYINGS)}, dt)
        clock = self._get_alpaca(ALPACA_TRADE, "/v2/clock", {}, dt)
        if snap is None and clock is None:
            return False
        derived = {}
        if isinstance(snap, dict):
            for sym in UNDERLYINGS:
                item = snap.get(sym)
                if not isinstance(item, dict):
                    _gap(dt, self.cycle, "alpaca", "/v2/stocks/snapshots",
                         f"no snapshot for {sym}", sym)
                    continue
                try:
                    # The response arrives after the cycle starts; a current
                    # latest trade must not be rejected as future by seconds.
                    captured_at = datetime.now(timezone.utc)
                    ref = from_snapshot(sym, item, captured_at)
                except ReferenceUnavailable as exc:
                    _gap(dt, self.cycle, "alpaca", "/v2/stocks/snapshots",
                         str(exc), sym)
                    continue
                derived[sym] = {"price": ref.price, "ts": _iso(ref.ts),
                                "source": ref.source,
                                "provider": ref.provider,
                                "age_s": (captured_at - ref.ts).total_seconds()}
        elif snap is not None:
            _gap(dt, self.cycle, "alpaca", "/v2/stocks/snapshots",
                 "snapshot response was not an object")
        _append(dt, "reference", {
            "kind": "reference", "ts": _iso(dt), "cycle": self.cycle,
            "provider": "alpaca", "snapshots": snap, "clock": clock,
            "derived": derived,
            "snapshots_ok": snap is not None, "derived_ok":
                len(derived) == len(UNDERLYINGS),
            "clock_ok": clock is not None,
        })
        return True

    # ---------------- loop ----------------

    def cycle_once(self) -> None:
        dt = _now()
        self.cycle += 1
        statuses = self.exchange_status(dt)
        if not statuses:
            _gap(dt, self.cycle, "binance", "/api/v3/exchangeInfo",
                 "no statuses; token records written with status=null")
        n = self.record_token(dt, statuses)
        ref_ok = self.record_reference(dt)
        HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT.write_text(json.dumps({
            "ts": _iso(dt), "cycle": self.cycle,
            "token_records": n, "reference_ok": ref_ok,
            "registry_sha256": registry_sha256(),
        }) + "\n")
        _log(f"cycle {self.cycle} token={n}/{len(TOKEN_SYMBOLS)} ref={'ok' if ref_ok else 'GAP'}")

    def run(self) -> None:
        _log(f"AFTERBELL recorder starting - {len(TOKEN_SYMBOLS)} symbols, "
             f"{INTERVAL_S}s cadence, registry {registry_sha256()[:12]}")
        while _running:
            started = time.time()
            try:
                self.cycle_once()
            except Exception as exc:  # never die silently; never die at all
                _gap(_now(), self.cycle, "recorder", "cycle",
                     f"UNCAUGHT {type(exc).__name__}: {exc}")
            sleep_for = INTERVAL_S - (time.time() - started) % INTERVAL_S
            deadline = time.time() + sleep_for
            while _running and time.time() < deadline:
                time.sleep(min(1.0, deadline - time.time()))
        _log("recorder stopped")


def _stop(signum, frame):
    global _running
    _running = False


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    Recorder().run()


if __name__ == "__main__":
    main()
