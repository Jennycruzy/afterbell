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
from afterbell.public_checks import PublicCheckUnavailable, PublicChecks
from afterbell.reference import (
    YAHOO_CHART, ReferenceUnavailable, from_snapshot, from_yahoo,
)
from afterbell.resolver import resolve, verify_contract

BINANCE = "https://api.binance.com"
ALPACA_DATA = "https://data.alpaca.markets"
ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = ROOT / "data" / "receipts.jsonl"
GAP_PATH = ROOT / "data" / "guard_gaps.jsonl"
DEPTH_LEVELS = 5000


def _gap(endpoint: str, symbol: str | None, reason: str) -> None:
    """Persist a failed live input without writing a fabricated measurement."""
    GAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "kind": "gap", "ts": datetime.now(timezone.utc).isoformat(),
        "source": "guard", "endpoint": endpoint, "symbol": symbol,
        "reason": reason[:500],
    }
    with GAP_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
        fh.flush()


class Guard:
    """The public surface. One policy, one ledger, one evaluate()."""

    def __init__(self, policy: Policy, ledger_path: Path | str = LEDGER_PATH,
                 baseline_min_samples: int | None = None) -> None:
        self.policy = policy
        self.ledger = Ledger(ledger_path)
        self._client = httpx.Client(
            timeout=httpx.Timeout(15.0, connect=10.0),
            headers={"User-Agent": "afterbell-guard/0.1"})
        self._public_checks = PublicChecks(self._client)
        self.last_receipt: dict | None = None
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
            self._baselines = bl.build(
                min_samples=self._min_samples,
                band_pct=self.policy.depth_band_pct,
                window_days=self.policy.baseline_window_days)
        return self._baselines

    def baseline_for(self, symbol: str) -> bl.Baseline | None:
        """Return a baseline, refreshing while this symbol is uncalibrated.

        The guard service is long-lived while the recorder is still collecting
        its minimum RTH sample set. A one-time cache would preserve an obsolete
        BLOCK forever, so an affected symbol is rebuilt until its measured
        denominator becomes usable. Once calibrated, the explicit cache keeps
        the full-depth history from being reparsed every minute.
        """
        baseline = self.baselines().get(symbol)
        if baseline is None or not baseline.is_calibrated:
            baseline = self.baselines(refresh=True).get(symbol)
        return baseline

    def fetch_book(self, symbol: str) -> Book | None:
        """Live order book. None when it cannot be read (Law 3)."""
        endpoint = "/api/v3/depth"
        try:
            r = self._client.get(f"{BINANCE}{endpoint}",
                                 params={"symbol": symbol,
                                         "limit": DEPTH_LEVELS})
            r.raise_for_status()
            d = r.json()
            if not isinstance(d, dict) or not d.get("bids") or not d.get("asks"):
                raise ValueError("empty order book response")
            book = Book.from_record({
                "symbol": symbol,
                "ts": datetime.now(timezone.utc)
                      .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "bids": d["bids"], "asks": d["asks"],
                "depth_limit": DEPTH_LEVELS})
            if book is None:
                raise ValueError("order book parser returned no book")
            return book
        except Exception as exc:
            _gap(endpoint, symbol, f"{type(exc).__name__}: {exc}")
            return None

    def fetch_status(self, symbol: str) -> str | None:
        endpoint = "/api/v3/exchangeInfo"
        try:
            r = self._client.get(f"{BINANCE}{endpoint}",
                                 params={"symbol": symbol})
            r.raise_for_status()
            data = r.json()
            symbols = data.get("symbols") if isinstance(data, dict) else None
            if not isinstance(symbols, list) or len(symbols) != 1:
                raise ValueError("exchangeInfo did not return exactly one symbol")
            status = symbols[0].get("status")
            if not isinstance(status, str) or not status:
                raise ValueError("exchangeInfo symbol has no status")
            return status
        except Exception as exc:
            _gap(endpoint, symbol, f"{type(exc).__name__}: {exc}")
            return None

    def fetch_corporate_state(
            self, inst, exchange_status: str | None = None
            ) -> tuple[str | None, bool, bool, str | None, str]:
        """Read Binance bStocks processing status.

        Corporate-action protection uses Binance's current issuer/venue status and reported reason
        messages. Binance does not guarantee advance corporate-action notice,
        so a clear current state remains an explicit partial result rather than
        a claimed issuer-level lookahead.
        """
        status = None
        status_error = None
        try:
            status = self._public_checks.rwa_status(inst)
        except PublicCheckUnavailable as exc:
            status_error = str(exc)
            _gap("binance-tokenized-securities-info/status", inst.token_symbol,
                 status_error)

        source = "binance-bstocks-status"
        if status is None:
            allowed = ((exchange_status or "").upper()
                       in self.policy.tradable_statuses)
            if not allowed:
                note = ("neither the bStocks status endpoint nor a tradable "
                        f"exchangeInfo status was verified: {status_error}")
                return None, False, False, None, note
            source = "exchangeInfo-fallback"
            note = ("bStocks status endpoint unavailable; current pair status "
                    f"verified by exchangeInfo ({exchange_status})")
            current_action = None
        else:
            reason_code = status.reason_code.upper()
            message = status.reason_message
            action_terms = {
                "cash_dividend", "stock_dividend", "stock_split", "merger",
                "acquisition", "spinoff", "earnings",
            }
            combined = " ".join(x for x in (reason_code, message or "") if x)
            if not status.open_state or reason_code != "TRADING":
                current_action = message if message else reason_code
            elif any(term in combined.lower() for term in action_terms):
                current_action = message if message else reason_code
            else:
                current_action = None
            note = (f"bStocks status endpoint: openState={status.open_state}, "
                    f"reasonCode={status.reason_code}; current status verified")

        # A current halt/pause is already a hard corporate-action result. It does not need a
        # second source before the guard refuses the order.
        if current_action:
            return current_action, True, True, source, note

        return (None, True, False, source,
                f"{note}; Binance current processing status is verified, but "
                "advance corporate-action notice is not guaranteed")

    def fetch_token_audit(self, contract: str) -> tuple[str, bool, bool | None, str]:
        """Contract-verification source; unsupported bStocks is registry-only."""
        try:
            audit = self._public_checks.token_audit(contract)
        except PublicCheckUnavailable as exc:
            note = f"token audit unavailable: {exc}"
            _gap("query-token-audit", contract, note)
            return "UNAVAILABLE", False, None, note
        note = (f"query-token-audit: {audit.status}; supported="
                f"{audit.supported}; hasResult={audit.has_result}")
        return audit.status, audit.supported, audit.safe, note

    def fetch_reference(self, underlying: str, at: datetime | None = None):
        """Reference price, or None with the reason recorded by the caller.

        Yahoo by default: it needs no credential, so this path holds none.
        Alpaca stays available for anyone who has a key and wants the reference
        to come from the firm that custodies the underlying.
        """
        if os.environ.get("REFERENCE_PROVIDER", "yahoo").strip().lower() \
                != "alpaca":
            return self._fetch_yahoo(underlying, at)
        key = os.environ.get("ALPACA_API_KEY", "").strip()
        sec = os.environ.get("ALPACA_SECRET_KEY", "").strip()
        if not key or not sec:
            note = "no Alpaca credentials configured"
            _gap("/v2/stocks/snapshots", underlying, note)
            return None, note
        try:
            r = self._client.get(
                f"{ALPACA_DATA}/v2/stocks/snapshots",
                params={"symbols": underlying},
                headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
            r.raise_for_status()
            snap = r.json().get(underlying)
        except Exception as exc:
            note = f"reference fetch failed: {type(exc).__name__}: {exc}"
            _gap("/v2/stocks/snapshots", underlying, note)
            return None, note
        if not snap:
            note = f"no snapshot returned for {underlying}"
            _gap("/v2/stocks/snapshots", underlying, note)
            return None, note
        try:
            return from_snapshot(underlying, snap, at), None
        except ReferenceUnavailable as exc:
            _gap("/v2/stocks/snapshots", underlying, str(exc))
            return None, str(exc)

    def _fetch_yahoo(self, underlying: str, at: datetime | None = None):
        try:
            r = self._client.get(f"{YAHOO_CHART}/{underlying}",
                                 params={"range": "1d", "interval": "1d"})
            r.raise_for_status()
            meta = r.json()["chart"]["result"][0]["meta"]
        except Exception as exc:
            note = f"reference fetch failed: {type(exc).__name__}: {exc}"
            _gap(f"{YAHOO_CHART}/{underlying}", underlying, note)
            return None, note
        try:
            return from_yahoo(underlying, meta, at), None
        except ReferenceUnavailable as exc:
            _gap(f"{YAHOO_CHART}/{underlying}", underlying, str(exc))
            return None, str(exc)

    # ---------------- evaluation ----------------

    def build_context(self, req: OrderRequest,
                      at: datetime | None = None) -> MarketContext:
        """Assemble the context, optionally as of a stated time.

        `at` moves the CLOCK only. The book, the pair status and the reference
        are whatever the market says right now, because there is no honest way
        to fetch a live order book as it stood at a past or future instant. A
        rehearsal therefore shows real depth under a simulated calendar, and
        the rehearsal script says so on every frame. Nothing in the production
        path passes `at`.
        """
        symbol = req.symbol.upper()
        res = resolve(req.query or symbol)
        inst = REGISTRY.get(symbol)
        contract = None
        audit_note = None
        if req.observed_contract is not None and inst is not None:
            audit_status, audit_supported, audit_passed, audit_note = \
                self.fetch_token_audit(req.observed_contract)
            contract = verify_contract(
                symbol, req.observed_contract, audit_verdict=audit_status,
                audit_status=audit_status, audit_supported=audit_supported,
                audit_passed=audit_passed)

        book = self.fetch_book(symbol)
        status = self.fetch_status(symbol)
        if inst is not None:
            (corporate_action, corp_checked, corp_lookahead_checked,
             corp_source, corp_note) = self.fetch_corporate_state(
                 inst, exchange_status=status)
            ref, ref_note = self.fetch_reference(inst.underlying, at)
        else:
            corporate_action, corp_checked = None, False
            corp_lookahead_checked, corp_source = False, None
            corp_note = "symbol not in canonical registry"
            ref, ref_note = None, "symbol not in registry"
        if audit_note:
            corp_note = f"{corp_note}; {audit_note}"

        ctx = MarketContext(
            clock=clock_at(at),
            book=book,
            baseline=self.baseline_for(symbol),
            reference_price=ref.price if ref else None,
            reference_ts=ref.ts if ref else None,
            exchange_status=status,
            corporate_action=corporate_action,
            resolution=res,
            contract=contract,
            reference_note=ref_note,
            corporate_action_checked=corp_checked,
            corporate_action_lookahead_checked=corp_lookahead_checked,
            corporate_action_source=corp_source,
            corporate_action_note=corp_note)
        return ctx

    def evaluate(self, req: OrderRequest, ctx: MarketContext | None = None
                 ) -> Decision:
        """Evaluate and write the receipt. Refusals are receipted too."""
        ctx = ctx or self.build_context(req)
        decision = guard_evaluate(req, ctx, self.policy)
        receipt = to_receipt(decision, req)
        receipt["reference_note"] = ctx.reference_note
        receipt["corporate_action_note"] = ctx.corporate_action_note
        receipt["query"] = req.query
        # The appended record carries seq, prev_hash and hash. An
        # authorization has to name them, so it is kept rather than discarded.
        self.last_receipt = self.ledger.append(receipt)
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


SIGNING_KEY = ROOT / "config" / "authorization.key"


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
    ap.add_argument("--authorize", default=None, metavar="PATH",
                    help="write a signed, short-lived authorization for this "
                         "decision. It permits what the guard permitted and "
                         "nothing more; a supported MCP client transcribes it")
    ap.add_argument("--signing-key", default=str(SIGNING_KEY))
    ap.add_argument("--narrate", action="store_true",
                    help="ask the optional narration provider for qualitative "
                         "prose; it cannot change the receipt or any number")
    a = ap.parse_args()

    guard = Guard.from_policy(a.policy)
    if a.authorize and not guard.policy.executor_enabled:
        raise SystemExit(
            "authorization issuance is disabled by policy; use a deliberate, "
            "checksummed demo policy with executor.enabled: true")
    req = OrderRequest(a.symbol, Side(a.side), a.notional,
                       query=a.query or a.symbol,
                       observed_contract=a.contract, audit_verdict=a.audit)
    d = guard.evaluate(req)
    print(render(d))
    if a.narrate:
        from afterbell.rationale import NarrationUnavailable, Narrator
        try:
            print("  NARRATION  " + Narrator.from_env().narrate(d))
        except NarrationUnavailable as exc:
            _gap("narration", req.symbol, str(exc))
            print(f"  NARRATION GAP  {exc}")
    print(f"  receipt seq {guard.ledger.seq}  ledger head {guard.ledger.head[:16]}...")
    print(f"  policy {d.policy_sha256[:16]}...\n")

    if a.authorize:
        from afterbell.authorization import issue, load_private_key
        auth = issue(d, req, guard.last_receipt,
                     load_private_key(a.signing_key),
                     cap=guard.policy.executor_max_order_usdt)
        Path(a.authorize).write_text(auth.to_json())
        print(f"  AUTHORIZATION  {auth.permitted_notional:,.2f} USDT "
              f"{auth.side} {auth.symbol}, valid {auth.seconds_remaining():.0f}s")
        print(f"                 nonce {auth.nonce}  -> {a.authorize}\n")


if __name__ == "__main__":
    main()
