"""AFTERBELL dashboard.

Part IX: REFERENCE_AGE is on the screen permanently, refusals are styled as
prominently as passes, and the policy checksum and ledger head are shown so a
reader can tell which rules produced what they are looking at.

Read-only and unauthenticated, like the recorder. It serves what has been
measured; it never computes a verdict of its own.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from afterbell import baselines as bl
from afterbell.clock import (
    MarketState, evaluate as clock_at, format_age, last_rth_close,
)
from afterbell.instruments import REGISTRY, TOKEN_SYMBOLS, registry_sha256
from afterbell.ledger import head_of
from afterbell.measure import Book, Side, depth_within, half_spread_bps, walk_cost_bps
from afterbell.measure import BookProblem
from afterbell.policy import load as load_policy

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
RECEIPTS = ROOT / "data" / "receipts.jsonl"

_cache: dict = {"ts": 0.0, "data": None}
_lock = threading.Lock()


def _latest_records() -> dict[str, dict]:
    """Most recent recorded book per symbol."""
    out: dict[str, dict] = {}
    days = sorted(RAW.glob("*/token.jsonl"))
    for path in days[-2:]:
        with path.open() as fh:
            for line in fh:
                if line.strip():
                    r = json.loads(line)
                    out[r["symbol"]] = r
    return out


def _receipts(limit: int = 40) -> list[dict]:
    if not RECEIPTS.exists():
        return []
    rows = [json.loads(l) for l in RECEIPTS.read_text().splitlines() if l.strip()]
    return rows[-limit:][::-1]


def build_state() -> dict:
    pol = load_policy()
    clock = clock_at()
    baselines = bl.build(min_samples=pol.min_rth_samples,
                         band_pct=pol.depth_band_pct)
    latest = _latest_records()

    symbols = []
    for sym in TOKEN_SYMBOLS:
        inst = REGISTRY[sym]
        rec = latest.get(sym)
        book = Book.from_record(rec) if rec else None
        base = baselines.get(sym)
        row = {
            "symbol": sym, "asset": inst.token_asset,
            "underlying": inst.underlying, "name": inst.underlying_name,
            "issuer": inst.issuer, "contract": inst.contract,
            "status": rec.get("status") if rec else None,
            "observed_at": rec.get("ts") if rec else None,
            "mid": None, "half_spread_bps": None, "depth_1pct": None,
            "walk_5k_bps": None, "spread_ratio": None, "liquidity_ratio": None,
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
            w = walk_cost_bps(book, 5000.0, Side.BUY)
            row["walk_5k_bps"] = (None if isinstance(w, BookProblem)
                                  else w.cost_bps)
            if base and base.is_calibrated and hs is not None and dp is not None:
                row["spread_ratio"] = base.spread_ratio(hs)
                row["liquidity_ratio"] = base.liquidity_ratio(dp)
        symbols.append(row)

    # Law 8: REFERENCE_AGE is never absent from a surface. Until a reference
    # price is available it is derived from the exchange calendar - the age of
    # the last regular session's close - and labelled with that source. The
    # calendar knows when the session ended even when no price feed is
    # configured; what it cannot give is the price, so the basis stays blank
    # rather than being invented.
    now = datetime.now(timezone.utc)
    if clock.state is MarketState.RTH_OPEN:
        ref_age_s, ref_source = 0.0, "live_session"
    else:
        ref_age_s = (now - last_rth_close(now)).total_seconds()
        ref_source = "exchange_calendar"

    return {
        "generated_at": now.isoformat(),
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
                   "min_rth_samples": pol.min_rth_samples},
        "registry_sha256": registry_sha256(),
        "ledger_head": head_of(RECEIPTS),
        "symbols": symbols,
        "receipts": _receipts(),
    }


def cached_state(max_age_s: float = 5.0) -> dict:
    import time
    with _lock:
        if _cache["data"] is None or time.time() - _cache["ts"] > max_age_s:
            _cache["data"] = build_state()
            _cache["ts"] = time.time()
        return _cache["data"]


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AFTERBELL</title>
<style>
:root{--bg:#0b0d10;--panel:#13171c;--line:#232a33;--fg:#e6edf3;--dim:#8b98a5;
--pass:#3fb950;--warn:#d29922;--reduce:#e3823a;--block:#f85149;--acc:#58a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.wrap{max-width:1180px;margin:0 auto;padding:24px 18px 60px}
h1{font-size:15px;letter-spacing:.28em;margin:0;font-weight:600}
.sub{color:var(--dim);font-size:12px;margin:4px 0 22px}
.hero{background:var(--panel);border:1px solid var(--line);border-radius:10px;
padding:20px 22px;margin-bottom:18px}
.hrow{display:flex;flex-wrap:wrap;gap:34px;align-items:flex-start}
.k{color:var(--dim);font-size:11px;letter-spacing:.14em;margin-bottom:5px}
.v{font-size:19px;font-weight:600}
.age{font-size:34px;font-weight:700;letter-spacing:.02em;font-variant-numeric:tabular-nums}
.open{color:var(--pass)}.closed{color:var(--block)}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--dim);font-weight:500;font-size:11px;
letter-spacing:.1em;padding:8px 10px;border-bottom:1px solid var(--line)}
td{padding:9px 10px;border-bottom:1px solid var(--line);
font-variant-numeric:tabular-nums}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;
overflow:hidden;margin-bottom:18px}
.ph{padding:13px 16px;border-bottom:1px solid var(--line);font-size:11px;
letter-spacing:.16em;color:var(--dim)}
.scroll{overflow-x:auto}
.tag{display:inline-block;padding:2px 7px;border-radius:4px;font-size:11px;
font-weight:600;letter-spacing:.04em}
.PASS{background:rgba(63,185,80,.14);color:var(--pass)}
.WARN{background:rgba(210,153,34,.16);color:var(--warn)}
.REDUCE{background:rgba(227,130,58,.16);color:var(--reduce)}
.BLOCK{background:rgba(248,81,73,.16);color:var(--block)}
.UNCALIBRATED{background:rgba(139,152,165,.14);color:var(--dim)}
.CALIBRATED{background:rgba(63,185,80,.14);color:var(--pass)}
.rc{padding:14px 16px;border-bottom:1px solid var(--line)}
.rc.blocked{border-left:3px solid var(--block)}
.rc.reduced{border-left:3px solid var(--reduce)}
.rc.passed{border-left:3px solid var(--pass)}
.rt{color:var(--dim);font-size:11px;margin-bottom:6px}
.rr{color:var(--fg);font-size:12.5px;margin-top:7px;line-height:1.6}
.gates{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.g{font-size:10.5px;padding:2px 6px;border-radius:3px}
.foot{color:var(--dim);font-size:11px;margin-top:26px;line-height:1.9;
word-break:break-all}
.mono{color:var(--acc)}
.empty{padding:22px 16px;color:var(--dim);font-size:12.5px}
</style></head><body><div class="wrap">
<h1>A F T E R B E L L</h1>
<div class="sub">The stock sleeps. The token doesn't. &mdash; calendar-aware risk boundary for tokenized equities</div>
<div id="app"></div>
<div class="foot" id="foot"></div>
</div>
<script>
const f=(n,d=2)=>n===null||n===undefined?'&mdash;':Number(n).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d});
const age=s=>{if(s===null||s===undefined)return'&mdash;';s=Math.floor(s);
return String(Math.floor(s/3600)).padStart(2,'0')+':'+String(Math.floor(s%3600/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');};
let refAge=null,lastSync=0;
function hero(d){
 const c=d.clock,open=c.state==='RTH_OPEN';
 return `<div class="hero"><div class="hrow">
 <div><div class="k">TOKEN MARKET</div><div class="v open">OPEN &middot; 24/7</div></div>
 <div><div class="k">REFERENCE MARKET</div><div class="v ${open?'open':'closed'}">${c.state}</div></div>
 <div><div class="k">REFERENCE_AGE</div><div class="age" id="age">&mdash;</div>
 <div style="color:var(--dim);font-size:10px;margin-top:3px">source: ${d.reference_age_source}</div></div>
 <div><div class="k">NEXT REGULAR PRINT</div><div class="v">${f(c.hours_to_next_open,2)}h</div></div>
 ${c.holiday?`<div><div class="k">HOLIDAY</div><div class="v closed">${c.holiday}</div></div>`:''}
 <div><div class="k">POLICY</div><div class="v"><span class="tag ${d.policy.status==='CALIBRATED'?'CALIBRATED':'UNCALIBRATED'}">${d.policy.status}</span></div></div>
 </div></div>`;}
function symbols(d){
 const r=d.symbols.map(s=>`<tr>
 <td><b>${s.asset}</b><div style="color:var(--dim);font-size:11px">${s.name}</div></td>
 <td>${s.status?`<span class="tag ${s.status==='TRADING'?'PASS':'BLOCK'}">${s.status}</span>`:'&mdash;'}</td>
 <td>${f(s.mid)}</td><td>${f(s.half_spread_bps,3)}</td>
 <td>${s.depth_1pct===null?'&mdash;':'$'+Math.round(s.depth_1pct).toLocaleString()}</td>
 <td>${f(s.walk_5k_bps,1)}</td>
 <td>${s.spread_ratio===null?'&mdash;':f(s.spread_ratio,2)+'&times;'}</td>
 <td>${s.liquidity_ratio===null?'&mdash;':Math.round(s.liquidity_ratio*100)+'%'}</td>
 <td><span class="tag ${s.baseline_status}">${s.baseline_status}</span>
 <div style="color:var(--dim);font-size:11px">${s.n_rth} RTH samples</div></td></tr>`).join('');
 return `<div class="panel"><div class="ph">MEASURED NOW &mdash; ratios appear once a symbol has ${d.policy.min_rth_samples} regular-session samples</div>
 <div class="scroll"><table><thead><tr><th>INSTRUMENT</th><th>PAIR</th><th>MID</th>
 <th>HALF-SPREAD bps</th><th>DEPTH &plusmn;1%</th><th>WALK $5k bps</th>
 <th>SPREAD RATIO</th><th>DEPTH vs RTH</th><th>BASELINE</th></tr></thead>
 <tbody>${r}</tbody></table></div></div>`;}
function receipts(d){
 if(!d.receipts.length)return `<div class="panel"><div class="ph">RECEIPT LEDGER</div>
 <div class="empty">No decisions recorded yet. Every evaluation &mdash; including every refusal &mdash; is appended here as a hash-chained receipt.</div></div>`;
 const rows=d.receipts.map(r=>{
  const cls=r.decision==='BLOCK'?'blocked':(r.decision==='REDUCE'?'reduced':'passed');
  const g=Object.entries(r.gates).map(([k,v])=>`<span class="g ${v}">${k} ${v}</span>`).join('');
  return `<div class="rc ${cls}"><div class="rt">#${r.seq} &middot; ${r.ts} &middot; ${r.symbol} &middot; ${r.market_state} &middot; REFERENCE_AGE ${r.reference_age||'none'}</div>
  <span class="tag ${r.decision}">${r.decision}</span>
  &nbsp;requested $${Number(r.requested.notional).toLocaleString()} &rarr; allowed $${Number(r.allowed_notional).toLocaleString()}
  ${r.binding_constraint!=='none'?`&nbsp;&middot;&nbsp;bound by ${r.binding_constraint}`:''}
  <div class="gates">${g}</div><div class="rr">${r.rationale}</div></div>`;}).join('');
 return `<div class="panel"><div class="ph">RECEIPT LEDGER &mdash; refusals shown as prominently as passes</div>${rows}</div>`;}
async function tick(){
 try{const d=await (await fetch('/api/state')).json();
  document.getElementById('app').innerHTML=hero(d)+symbols(d)+receipts(d);
  document.getElementById('foot').innerHTML=
   `policy sha256 <span class="mono">${d.policy.sha256}</span><br>`+
   `registry sha256 <span class="mono">${d.registry_sha256}</span><br>`+
   `ledger head <span class="mono">${d.ledger_head||'(no receipts yet)'}</span><br>`+
   `generated ${d.generated_at}`;
  refAge=d.reference_age_s??null;lastSync=Date.now();
  paint(d);
 }catch(e){}}
function paint(d){const el=document.getElementById('age');if(!el)return;
 el.innerHTML=d.reference_age_s===null||d.reference_age_s===undefined?'no reference':age(d.reference_age_s+(Date.now()-lastSync)/1000);}
tick();setInterval(tick,10000);
setInterval(()=>{const el=document.getElementById('age');
 if(el&&refAge!==null)el.innerHTML=age(refAge+(Date.now()-lastSync)/1000);},1000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        try:
            if self.path.startswith("/api/state"):
                body = json.dumps(cached_state(), default=str).encode()
                return self._send(200, body, "application/json")
            if self.path in ("/", "/index.html"):
                return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            if self.path == "/healthz":
                return self._send(200, b"ok", "text/plain")
            self._send(404, b"not found", "text/plain")
        except Exception as exc:                      # never serve a lie
            self._send(500, json.dumps({"error": str(exc)}).encode(),
                       "application/json")

    def log_message(self, *a) -> None:
        pass


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    print(f"AFTERBELL dashboard on http://{a.host}:{a.port}", flush=True)
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
