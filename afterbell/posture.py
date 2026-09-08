"""What AFTERBELL notices on its own, between requests.

The continuous monitor evaluates the same advisory request every minute, which
makes it a good heartbeat and a poor observer: a thousand identical receipts
say nothing about the one minute where something actually changed.

This module reduces a monitor cycle to the bands the policy already sizes on --
where the reference market is in its calendar, how stale the independent price
has become, how the book compares with its own regular-hours normal, how far
the token has drifted from the reference, what the venue reports, and whether
there is current account evidence. A transition between two of those bands is
material *by construction*: it is a boundary the policy already changes its
answer at, not a threshold invented for reporting.

What this does not do, deliberately:

- it never originates an order (Law 7);
- it never issues a standing or unbound authorization. An authorization is
  bound to one specific proposal -- symbol, side, requested and permitted size,
  the evidence behind it, an expiry and a one-time nonce. There is no proposal
  behind a background observation, so there is nothing here to sign into
  executable authority. When an agent later proposes an order, the existing
  request-specific path runs unchanged and decides what it may do.

A posture change is an observation with a reason. It is recorded so the next
agent action meets a current safety picture instead of a stale one.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from afterbell.policy import Policy

UNKNOWN = "unknown"


@dataclass(frozen=True)
class Posture:
    """One symbol's safety-relevant state, reduced to comparable bands."""
    symbol: str
    market_state: str
    reference: str
    liquidity: str
    price_agreement: str
    venue_status: str
    account_evidence: str
    verdict: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


# The plain-language name of each band, and how to say that it moved. Keyed in
# the order a reader should meet them: where the market is, then what we can
# still measure about it, then what we concluded.
_FIELDS: tuple[tuple[str, str], ...] = (
    ("market_state", "Reference market"),
    ("reference", "Independent price"),
    ("liquidity", "Liquidity"),
    ("price_agreement", "Price agreement"),
    ("venue_status", "Venue status"),
    ("account_evidence", "Account evidence"),
    ("verdict", "Safety posture"),
)

_WHY = {
    "market_state": ("The market that supplies the independent price changed "
                     "session."),
    "reference": ("The independent stock price is not refreshing, so what the "
                  "token is worth is being judged against an older fact."),
    "liquidity": ("The book has moved away from what this symbol normally "
                  "looks like while its own market is open."),
    "price_agreement": ("The token and the last independent price have moved "
                        "apart."),
    "venue_status": "The venue changed what it reports about this pair.",
    "account_evidence": ("What the account already holds is no longer known "
                         "from a current signed report."),
    "verdict": ("The size AFTERBELL is willing to stand behind changed as a "
                "result."),
}


def _reference_band(age_s: float | None, pol: Policy) -> str:
    """Bands are the backward-gap ladder: the ages sizing already steps at."""
    if age_s is None:
        return "none"
    if age_s >= pol.max_reference_age_s:
        return "beyond use"
    labels = ("fresh", "ageing", "stale", "very stale")
    for i, rung in enumerate(pol.backward_gap):
        limit = rung.get("max_age_s")
        if limit is None or age_s <= float(limit):
            return labels[min(i, len(labels) - 1)]
    return "very stale"


def _liquidity_band(spread_ratio: Any, liquidity_ratio: Any,
                    pol: Policy) -> str:
    """Bands are the liquidity tiers, so a move is a move in permitted size."""
    if spread_ratio is None or liquidity_ratio is None:
        return UNKNOWN
    try:
        spread, depth = float(spread_ratio), float(liquidity_ratio)
    except (TypeError, ValueError):
        return UNKNOWN
    labels = ("normal", "thin", "very thin")
    for i, tier in enumerate(pol.liquidity_tiers):
        if (spread <= float(tier["max_spread_ratio"])
                and depth >= float(tier["min_liquidity_ratio"])):
            return labels[min(i, len(labels) - 1)]
    return "unusable"


def _account_band(exposure_check: Any) -> str:
    if not exposure_check:
        return "missing"
    text = str(exposure_check).strip().lower()
    if text in ("verified", "ok"):
        return "current"
    if "missing" in text or "not provided" in text:
        return "missing"
    if "expired" in text or "stale" in text:
        return "expired"
    return text


def observe(state: dict[str, Any], pol: Policy) -> Posture:
    """Reduce one monitor cycle to its bands."""
    m = state.get("measurements") or {}
    return Posture(
        symbol=str(state.get("symbol") or m.get("symbol") or "unknown"),
        market_state=str(state.get("market_state") or UNKNOWN),
        reference=_reference_band(state.get("reference_age_s"), pol),
        liquidity=_liquidity_band(m.get("spread_ratio"),
                                  m.get("liquidity_ratio"), pol),
        price_agreement=str(m.get("band") or UNKNOWN),
        # Normalised, because the same status reaches this from sources that
        # disagree on case, and a change of case is not a change of state.
        venue_status=str(m.get("exchange_status") or UNKNOWN).strip().lower(),
        account_evidence=_account_band(m.get("exposure_check")),
        verdict=str(state.get("status") or UNKNOWN),
    )


def transitions(before: Posture | None,
                after: Posture) -> list[tuple[str, str, str]]:
    """Every band that moved. Empty when nothing did, which is the usual case.

    A first observation has nothing to compare against, so it reports no
    transition rather than inventing one against a default.
    """
    if before is None:
        return []
    out = []
    for field, _ in _FIELDS:
        was, now = getattr(before, field), getattr(after, field)
        if was != now:
            out.append((field, was, now))
    return out


def explain(symbol: str, moved: list[tuple[str, str, str]]) -> str:
    """Plain language, deterministic. No model supplies any part of this."""
    if not moved:
        return f"{symbol}: nothing material changed."
    labels = dict(_FIELDS)
    lines = [f"AFTERBELL noticed a material change on {symbol}.", ""]
    for field, was, now in moved:
        lines.append(f"{labels.get(field, field)}: {was} -> {now}")
    lines.append("")
    seen: set[str] = set()
    for field, _, _ in moved:
        why = _WHY.get(field)
        if why and why not in seen:
            seen.add(why)
            lines.append(why)
    lines.append("")
    lines.append("Nobody asked for this. No order was created and no "
                 "authorization was issued; a request is still evaluated on "
                 "its own merits when one arrives.")
    return "\n".join(lines)


def change_record(before: Posture | None, after: Posture,
                  moved: list[tuple[str, str, str]], *, ts: str,
                  receipt_seq: int | None, receipt_hash: str | None,
                  narration: str | None = None) -> dict[str, Any]:
    """The ledger record for a noticed change.

    It carries no permitted size and no signature, because it authorises
    nothing. It is an observation, chained beside the decisions so the order
    of events is not in question.
    """
    return {
        "kind": "posture_change",
        "ts": ts,
        "symbol": after.symbol,
        "observed_from_receipt_seq": receipt_seq,
        "observed_from_receipt_hash": receipt_hash,
        "before": before.to_dict() if before else None,
        "after": after.to_dict(),
        "changed": [{"band": f, "before": w, "after": n} for f, w, n in moved],
        "explanation": explain(after.symbol, moved),
        "narration": narration,
        "authorizes": None,
    }
