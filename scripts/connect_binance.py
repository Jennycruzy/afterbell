"""Connect AFTERBELL to Binance Agent OS.

Completes the OAuth 2.1 authorization-code + PKCE flow that provisions the
Agentic sub-account, then answers the three open account questions in one run:

  1. is the sub-account authorized to trade bStocks
  2. is this jurisdiction eligible for them
  3. does binance-tokenized-securities-info resolve NVDAB, or is it Ondo-only

Run this on the machine whose browser you will log in with - the redirect
lands on 127.0.0.1. If you are on a different machine from the listener, pass
--manual and paste the redirected URL instead.

The token is written to .env (gitignored, chmod 600) and is never logged, never
printed and never written into a receipt.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
# The PKCE verifier and the state must survive between printing the URL and
# pasting the redirect back, because those are two separate commands when the
# browser is on a different machine from this one. Without this the secret dies
# with the process and the login silently cannot be completed.
PENDING = ROOT / "data" / ".oauth_pending.json"
DISCOVERY = "https://agent.binance.com/.well-known/oauth-authorization-server"
MCP_URL = "https://agent.binance.com/mcp/agentic"
CLIENT_ID = ("https://raw.githubusercontent.com/Jennycruzy/afterbell/"
             "main/oauth/client.json")
REDIRECT = "http://127.0.0.1:8765/callback"

_code: dict[str, str] = {}


class CB(BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _code.update({k: v[0] for k, v in q.items()})
        body = (b"<h2>AFTERBELL connected.</h2><p>You can close this tab.</p>"
                if "code" in q else
                b"<h2>Authorization failed.</h2><p>Check the terminal.</p>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def discover() -> dict:
    r = httpx.get(DISCOVERY, timeout=20)
    r.raise_for_status()
    return r.json()


def pkce() -> tuple[str, str]:
    v = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    c = base64.urlsafe_b64encode(
        hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
    return v, c


def save_token(tok: dict) -> None:
    """Write the token to .env without disturbing anything already there."""
    lines = []
    if ENV.exists():
        lines = [l for l in ENV.read_text().splitlines()
                 if not l.startswith(("BINANCE_ACCESS_TOKEN=",
                                      "BINANCE_REFRESH_TOKEN="))]
    lines.append(f"BINANCE_ACCESS_TOKEN={tok['access_token']}")
    if tok.get("refresh_token"):
        lines.append(f"BINANCE_REFRESH_TOKEN={tok['refresh_token']}")
    ENV.write_text("\n".join(lines) + "\n")
    ENV.chmod(0o600)


def mcp(token: str, method: str, params: dict | None = None) -> dict:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    r = httpx.post(MCP_URL, json=body, timeout=45, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"})
    if r.status_code != 200:
        return {"_http": r.status_code, "_body": r.text[:400]}
    txt = r.text
    if txt.startswith("event:") or "\ndata: " in txt:      # SSE framing
        for line in txt.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
    return r.json()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manual", action="store_true",
                    help="paste the redirected URL instead of listening")
    ap.add_argument("--url-only", action="store_true",
                    help="print the login URL and exit, keeping the PKCE "
                         "verifier on disk for --finish")
    ap.add_argument("--finish", metavar="URL", default=None,
                    help="complete a --url-only login with the URL your "
                         "browser was redirected to")
    a = ap.parse_args()

    if a.finish:
        if not PENDING.exists():
            sys.exit("no login in progress; run --url-only first")
        saved = json.loads(PENDING.read_text())
        meta, verifier, state = saved["meta"], saved["verifier"], saved["state"]
        q = urllib.parse.parse_qs(urllib.parse.urlparse(a.finish).query)
        _code.update({k: v[0] for k, v in q.items()})
        if not _code.get("code") and not _code.get("error"):
            sys.exit("that URL carries no ?code= parameter. Copy the whole "
                     "address bar after approving, even if the page failed "
                     "to load - the code is in the URL, not in the page.")
        PENDING.unlink()
        return _complete(meta, verifier, state)

    meta = discover()
    verifier, challenge = pkce()
    state = secrets.token_urlsafe(24)
    url = meta["authorization_endpoint"] + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})

    if a.url_only:
        PENDING.parent.mkdir(parents=True, exist_ok=True)
        PENDING.write_text(json.dumps(
            {"meta": meta, "verifier": verifier, "state": state}))
        PENDING.chmod(0o600)
        print("\nOpen this URL in your browser and approve access:\n")
        print("  " + url + "\n")
        print("The browser will then try to reach 127.0.0.1:8765 and will")
        print("probably show a connection error. That is expected and fine -")
        print("the part that matters is in the address bar. Copy the WHOLE")
        print("address and run:\n")
        print("  python scripts/connect_binance.py --finish '<paste it here>'\n")
        return

    print("\nOpen this URL and approve access:\n")
    print("  " + url + "\n")

    if a.manual:
        pasted = input("Paste the full URL you were redirected to: ").strip()
        q = urllib.parse.parse_qs(urllib.parse.urlparse(pasted).query)
        _code.update({k: v[0] for k, v in q.items()})
    else:
        srv = HTTPServer(("127.0.0.1", 8765), CB)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            webbrowser.open(url)
        except Exception:
            pass
        print("waiting for the redirect on 127.0.0.1:8765 ...")
        while "code" not in _code and "error" not in _code:
            pass
        srv.shutdown()

    _complete(meta, verifier, state)


def _complete(meta: dict, verifier: str, state: str) -> None:
    if "error" in _code:
        sys.exit(f"authorization failed: {_code}")
    if _code.get("state") != state:
        sys.exit("state mismatch; aborting")

    tr = httpx.post(meta["token_endpoint"], timeout=30, data={
        "grant_type": "authorization_code", "code": _code["code"],
        "redirect_uri": REDIRECT, "client_id": CLIENT_ID,
        "code_verifier": verifier})
    if tr.status_code != 200:
        sys.exit(f"token exchange failed {tr.status_code}: {tr.text[:400]}")
    tok = tr.json()
    save_token(tok)
    print("\ntoken stored in .env (gitignored, chmod 600)\n")

    token = tok["access_token"]
    print("=" * 66)
    init = mcp(token, "initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "afterbell", "version": "0.1"}})
    print("initialize:", json.dumps(init)[:300])

    tools = mcp(token, "tools/list")
    names = [t["name"] for t in tools.get("result", {}).get("tools", [])]
    print(f"\n{len(names)} tools exposed:")
    for n in names:
        print("   ", n)

    print("\n" + "=" * 66)
    print("BLOCKER 3 - does the tokenized-securities skill resolve NVDAB?")
    cand = [n for n in names if "token" in n.lower() or "securit" in n.lower()
            or "stock" in n.lower()]
    print("  candidate tools:", cand or "(none exposed)")
    for n in cand:
        for args in ({"symbol": "NVDAB"}, {"symbol": "NVDABUSDT"},
                     {"asset": "NVDAB"}):
            res = mcp(token, "tools/call", {"name": n, "arguments": args})
            body = json.dumps(res)[:300]
            print(f"  {n}{args} -> {body}")
    print("\nBLOCKER 1/2 - place a $5 NVDAB order from the Binance UI or an")
    print("  execution tool above to confirm authorization and eligibility.")


if __name__ == "__main__":
    main()
