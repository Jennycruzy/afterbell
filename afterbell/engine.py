"""Assembles a MarketContext from live data and writes the receipt.

This is the seam a host agent uses:

    guard = Guard.from_policy("config/policy.yaml")
    decision = guard.evaluate(order)
    if decision.allowed_notional > 0:
        mcp.place_order(order.at(decision.allowed_notional))

Four lines around an existing agent, trading logic untouched.

Law 3: every input is fetched, and a fetch that fails halts the affected path
rather than substituting a default. Law 10: market data here is unauthenticated;
nothing in this module holds a Binance credential.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from afterbell import baselines as bl
from afterbell.clock import evaluate as clock_at
from afterbell.guard import (
    Decision, MarketContext, OrderRequest, evaluate as guard_evaluate,
    to_receipt,
)
from afterbell.instruments import REGISTRY
from afterbell.ledger import Ledger
from afterbell.measure import Book, Side
from afterbell.policy import Policy, load as load_policy
from afterbell.reference import (
    YAHOO_CHART, ReferenceUnavailable, from_snapshot, from_yahoo,
)
from afterbell.resolver import resolve, verify_contract

BINANCE = "https://api.binance.com"
ALPACA_DATA = "https://data.alpaca.markets"
ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = ROOT / "data" / "receipts.jsonl"
DEPTH_LEVELS = 5000


class Guard:
    """The public surface. One policy, one ledger, one evaluate()."""

    def __init__(self, policy: Policy, ledger_path: Path | str = LEDGER_PATH,
                 baseline_min_samples: int | None = None) -> None:
        self.policy = policy
        self.ledger = Ledger(ledger_path)
        self._client = httpx.Client(
            timeout=httpx.Timeout(15.0, connect=10.0),
            headers={"User-Agent": "afterbell-guard/0.1"})
        self._min_samples = (baseline_min_samples
                             if baseline_min_samples is not None
                             else policy.min_rth_samples)
        self._baselines: dict[str, bl.Baseline] | None = None

    @classmethod
    def from_policy(cls, path: str | Path | None = None, **kw) -> "Guard":
        return cls(load_policy(path), **kw)

    # ---------------- inputs ----------------

    def baselines(self, refresh: bool = False) -> dict[str, bl.Baseline]:
        if self._baselines is None or refresh:
            self._baselines = bl.build(min_samples=self._min_samples,
                                       band_pct=self.policy.depth_band_pct)
        return self._baselines

    def fetch_book(self, symbol: str) -> Book | None:
        """Live order book. None when it cannot be read (Law 3)."""
        try:
            r = self._client.get(f"{BINANCE}/api/v3/depth",
                                 params={"symbol": symbol,
                                         "limit": DEPTH_LEVELS})
            r.raise_for_status()
            d = r.json()
        except Exception:
            return None
        return Book.from_record({
            "symbol": symbol,
            "ts": datetime.now(timezone.utc)
                  .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "bids": d.get("bids", []), "asks": d.get("asks", []),
            "depth_limit": DEPTH_LEVELS})

    def fetch_status(self, symbol: str) -> str | None:
        try:
            r = self._client.get(f"{BINANCE}/api/v3/exchangeInfo",
                                 params={"symbol": symbol})
            r.raise_for_status()
            return r.json()["symbols"][0]["status"]
        except Exception:
            return None

    def fetch_reference(self, underlying: str):
        """Reference price, or None with the reason recorded by the caller.

        Yahoo by default: it needs no credential, so this path holds none.
        Alpaca stays available for anyone who has a key and wants the reference
        to come from the firm that custodies the underlying.
        """
        if os.environ.get("REFERENCE_PROVIDER", "yahoo").strip().lower() \
                != "alpaca":
            return self._fetch_yahoo(underlying)
        key = os.environ.get("ALPACA_API_KEY", "").strip()
        sec = os.environ.get("ALPACA_SECRET_KEY", "").strip()
        if not key or not sec:
            return None, "no Alpaca credentials configured"
        try:
            r = self._client.get(
                f"{ALPACA_DATA}/v2/stocks/snapshots",
                params={"symbols": underlying},
                headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
            r.raise_for_status()
            snap = r.json().get(underlying)
        except Exception as exc:
            return None, f"reference fetch failed: {type(exc).__name__}: {exc}"
        if not snap:
            return None, f"no snapshot returned for {underlying}"
        try:
            return from_snapshot(underlying, snap), None
        except ReferenceUnavailable as exc:
            return None, str(exc)

    def _fetch_yahoo(self, underlying: str):
        try:
            r = self._client.get(f"{YAHOO_CHART}/{underlying}",
                                 params={"range": "1d", "interval": "1d"})
            r.raise_for_status()
            meta = r.json()["chart"]["result"][0]["meta"]
        except Exception as exc:
            return None, f"reference fetch failed: {type(exc).__name__}: {exc}"
        try:
            return from_yahoo(underlying, meta), None
        except ReferenceUnavailable as exc:
            return None, str(exc)

    # ---------------- evaluation ----------------

    def build_context(self, req: OrderRequest) -> MarketContext:
        res = resolve(req.query or req.symbol)
        inst = REGISTRY.get(req.symbol)
        contract = (verify_contract(req.symbol, req.observed_contract,
                                    req.audit_verdict)
                    if req.observed_contract is not None else None)

        book = self.fetch_book(req.symbol)
        status = self.fetch_status(req.symbol)
        ref, ref_note = (self.fetch_reference(inst.underlying)
                         if inst else (None, "symbol not in registry"))

        ctx = MarketContext(
            clock=clock_at(),
            book=book,
            baseline=self.baselines().get(req.symbol),
            reference_price=ref.price if ref else None,
            reference_ts=ref.ts if ref else None,
            exchange_status=status,
            resolution=res,
            contract=contract,
            reference_note=ref_note)
        return ctx

    def evaluate(self, req: OrderRequest, ctx: MarketContext | None = None
                 ) -> Decision:
        """Evaluate and write the receipt. Refusals are receipted too."""
        ctx = ctx or self.build_context(req)
        decision = guard_evaluate(req, ctx, self.policy)
        receipt = to_receipt(decision, req)
        receipt["reference_note"] = ctx.reference_note
        receipt["query"] = req.query
        self.ledger.append(receipt)
        return decision


def render(d: Decision) -> str:
    """Terminal rendering of one decision. Formats; never calculates."""
    from afterbell.clock import format_age
    ctx = d.context
    age = ("no reference" if ctx.reference_age_s is None
           else format_age(ctx.reference_age_s))
    lines = [
        "",
        f"  TOKEN MARKET  OPEN            REFERENCE MARKET  {ctx.clock.state.value}",
        f"                                REFERENCE_AGE     {age}",
        "",
    ]
    for g in d.gates:
        lines.append(f"    {g.name}  {g.verdict.value:6}  f={g.factor:5.3f}  {g.detail}")
    lines += [
        "",
        f"  DECISION  {d.verdict.value}    requested {d.requested_notional:,.0f} "
        f"-> allowed {d.allowed_notional:,.0f} USDT",
        f"  BINDING   {d.binding_constraint}",
        "",
        f"  {d.rationale}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Evaluate one order against AFTERBELL.")
    ap.add_argument("--symbol", default="NVDABUSDT")
    ap.add_argument("--side", default="BUY", choices=["BUY", "SELL"])
    ap.add_argument("--notional", type=float, default=5000.0)
    ap.add_argument("--query", default="")
    ap.add_argument("--contract", default=None)
    ap.add_argument("--audit", default=None)
    ap.add_argument("--policy", default=None)
    a = ap.parse_args()

    guard = Guard.from_policy(a.policy)
    req = OrderRequest(a.symbol, Side(a.side), a.notional,
                       query=a.query or a.symbol,
                       observed_contract=a.contract, audit_verdict=a.audit)
    d = guard.evaluate(req)
    print(render(d))
    print(f"  receipt seq {guard.ledger.seq}  ledger head {guard.ledger.head[:16]}...")
    print(f"  policy {d.policy_sha256[:16]}...\n")


if __name__ == "__main__":
    main()
