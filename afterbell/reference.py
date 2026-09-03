"""Reference price: the last REGULAR-session trade of the underlying.

Law 8 hinges on this being right. Not the last extended-hours print, not an
oracle tick, not a stale quote. Extended-hours prints are recorded and flagged
EXT; they are information, not a reference.

Measured limitation (2026-09-02 20:00Z): Alpaca's free tier serves the IEX feed
only, and its off-hours quotes are unusable as a reference - NVDA quoted bid
212.20 / ask 0.00 against a 224.435 last trade, TSLA 335.51 / 371.79 around a
355.68 trade. Quotes are therefore never used here. Trades and the session's
official close are.

Two providers, because the spec lists Alpaca's failure mode as
"Finnhub -> Twelve Data -> Stooq CSV" and one of those is already gone: Stooq
now answers automated requests with a JavaScript proof-of-work challenge rather
than CSV (measured 2026-09-03), so it cannot serve an unattended recorder.

The default provider is Yahoo, which needs no key and no account. That is not
only a convenience. An Alpaca key is not scoped - Alpaca issues no read-only
credential, so a key that fetches a reference price can also place an order,
and this repository is public. A provider requiring no credential at all is the
stronger position for a component whose entire claim is that it cannot trade.

Yahoo also carries a better timestamp. Alpaca's daily bar is stamped 04:00Z and
has to be re-stamped to the real closing bell before REFERENCE_AGE means
anything; Yahoo's `regularMarketTime` is already the bell. Its price is the
consolidated tape rather than IEX alone, which is the more defensible
denominator for a basis. Cross-checked 2026-09-03: NVDA 224.41 consolidated
against the 224.435 IEX print measured the previous session, 1.1bps apart.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from afterbell.clock import ET, MarketState, evaluate as clock_at, rth_close_time

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart"

# Trade condition codes that mark a print as outside the regular session.
# T: extended-hours trade. U: extended-hours sold out of sequence.
EXTENDED_CONDITIONS = {"T", "U"}


@dataclass(frozen=True)
class ReferencePrice:
    symbol: str
    price: float
    ts: datetime              # when the print happened
    source: str               # "regular_trade" | "session_close"
    is_extended: bool = False
    provider: str = "alpaca"


class ReferenceUnavailable(RuntimeError):
    """Raised loudly. A missing reference is never treated as agreement."""


def _parse_ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(
        timezone.utc)


def _session_close_before(now: datetime, ts: datetime) -> datetime | None:
    """The closing bell of the session `ts` belongs to, if it has happened."""
    session_date = ts.astimezone(ET).date()
    close_dt = datetime.combine(session_date, rth_close_time(session_date),
                                tzinfo=ET).astimezone(timezone.utc)
    return close_dt if close_dt <= now else None


def from_yahoo(symbol: str, meta: dict,
               now: datetime | None = None) -> ReferencePrice:
    """Derive the reference from one Yahoo chart `meta` block.

    `regularMarketTime` is what makes this usable: it is the timestamp of the
    last regular-session print, so while the session is open it moves with the
    tape, and once the bell has rung it stops at the bell. Neither case needs
    re-stamping.

    The stamp is still checked against this project's own exchange calendar
    rather than trusted. A provider asserting a regular-session print at a time
    when no regular session was running is a provider disagreeing with the
    calendar, and the calendar wins - Law 3, a reference that cannot be
    confirmed is refused, never assumed.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    price = meta.get("regularMarketPrice")
    raw_ts = meta.get("regularMarketTime")
    if price is None or raw_ts is None:
        raise ReferenceUnavailable(
            f"no regularMarketPrice/Time returned for {symbol}")
    ts = datetime.fromtimestamp(int(raw_ts), timezone.utc)

    if ts > now:
        raise ReferenceUnavailable(
            f"{symbol} reference is stamped in the future ({ts.isoformat()})")

    if clock_at(ts).state is MarketState.RTH_OPEN:
        return ReferencePrice(symbol, float(price), ts, "regular_trade",
                              False, "yahoo")

    # Not inside a session. The one stamp that is still a regular-session
    # print is the closing bell itself, which the clock reads as RTH_POST
    # because the session has ended by then.
    close_dt = _session_close_before(now, ts)
    if close_dt is not None and abs((ts - close_dt).total_seconds()) <= 60:
        return ReferencePrice(symbol, float(price), close_dt, "session_close",
                              False, "yahoo")

    raise ReferenceUnavailable(
        f"{symbol} reference stamped {ts.isoformat()} is outside any regular "
        f"session on this project's calendar")


def from_snapshot(symbol: str, snap: dict,
                  now: datetime | None = None) -> ReferencePrice:
    """Derive the reference from one Alpaca snapshot.

    While the regular session is open, the latest trade is the reference, but
    only if its own condition codes and its own timestamp agree that it is a
    regular-session print. Otherwise the reference is the last session's
    official close, timestamped at that session's actual closing bell rather
    than at the bar's start - a daily bar is stamped 04:00Z, and using that
    would overstate REFERENCE_AGE by most of a day.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    state = clock_at(now).state

    trade = snap.get("latestTrade") or {}
    if state is MarketState.RTH_OPEN and trade.get("p") and trade.get("t"):
        ts = _parse_ts(trade["t"])
        conds = set(trade.get("c") or [])
        extended = bool(conds & EXTENDED_CONDITIONS)
        if not extended and clock_at(ts).state is MarketState.RTH_OPEN:
            return ReferencePrice(symbol, float(trade["p"]), ts,
                                  "regular_trade", False, "alpaca")

    for key in ("dailyBar", "prevDailyBar"):
        bar = snap.get(key) or {}
        if not bar.get("c") or not bar.get("t"):
            continue
        close_dt = _session_close_before(now, _parse_ts(bar["t"]))
        if close_dt is not None:
            return ReferencePrice(symbol, float(bar["c"]), close_dt,
                                  "session_close", False, "alpaca")

    raise ReferenceUnavailable(
        f"no regular-session reference available for {symbol}")
