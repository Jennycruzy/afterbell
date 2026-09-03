"""Reference price: the last REGULAR-session trade of the underlying.

Law 8 hinges on this being right. Not the last extended-hours print, not an
oracle tick, not a stale quote. Extended-hours prints are recorded and flagged
EXT; they are information, not a reference.

Measured limitation (2026-09-02 20:00Z): Alpaca's free tier serves the IEX feed
only, and its off-hours quotes are unusable as a reference - NVDA quoted bid
212.20 / ask 0.00 against a 224.435 last trade, TSLA 335.51 / 371.79 around a
355.68 trade. Quotes are therefore never used here. Trades and the session's
official close are.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from afterbell.clock import ET, MarketState, evaluate as clock_at, rth_close_time

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


class ReferenceUnavailable(RuntimeError):
    """Raised loudly. A missing reference is never treated as agreement."""


def _parse_ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(
        timezone.utc)


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
                                  "regular_trade", False)

    for key in ("dailyBar", "prevDailyBar"):
        bar = snap.get(key) or {}
        if not bar.get("c") or not bar.get("t"):
            continue
        session_date = _parse_ts(bar["t"]).astimezone(ET).date()
        close_dt = datetime.combine(session_date, rth_close_time(session_date),
                                    tzinfo=ET).astimezone(timezone.utc)
        if close_dt <= now:
            return ReferencePrice(symbol, float(bar["c"]), close_dt,
                                  "session_close", False)

    raise ReferenceUnavailable(
        f"no regular-session reference available for {symbol}")
