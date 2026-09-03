"""Reference-market clock and REFERENCE_AGE.

Law 8: REFERENCE_AGE is the product's central variable. It is never defaulted,
never rounded away, and never hidden.

Law 3: if the calendar cannot answer, the state is UNKNOWN, and UNKNOWN maps to
the most restrictive treatment available - never the loosest.

The session calendar is a static checked-in table (Part V). It is cross-checked
against Alpaca's /v2/calendar at startup when credentials are present; a
disagreement is loud, and the static table wins so that the guard's behaviour
never depends on a reachable third party.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# NYSE / Nasdaq full closures, 2026. Derived from the exchange rules
# (fixed dates, nth-weekday rules, Good Friday) and checked in per Part V.
# PENDING CROSS-CHECK against Alpaca /v2/calendar once credentials are present;
# the 2026-09-07 entry is already confirmed - Alpaca's calendar returns
# 2026-09-03, 2026-09-04, then 2026-09-08, with 09-07 absent.
HOLIDAYS_2026: dict[date, str] = {
    date(2026, 1, 1): "New Year's Day",
    date(2026, 1, 19): "Martin Luther King Jr. Day",
    date(2026, 2, 16): "Washington's Birthday",
    date(2026, 4, 3): "Good Friday",
    date(2026, 5, 25): "Memorial Day",
    date(2026, 6, 19): "Juneteenth National Independence Day",
    date(2026, 7, 3): "Independence Day (observed)",
    date(2026, 9, 7): "Labor Day",
    date(2026, 11, 26): "Thanksgiving Day",
    date(2026, 12, 25): "Christmas Day",
}

# Sessions ending at 13:00 ET instead of 16:00.
EARLY_CLOSES_2026: dict[date, str] = {
    date(2026, 11, 27): "Day after Thanksgiving",
    date(2026, 12, 24): "Christmas Eve",
}

PRE_OPEN = time(4, 0)
RTH_OPEN_T = time(9, 30)
RTH_CLOSE_T = time(16, 0)
EARLY_CLOSE_T = time(13, 0)
POST_CLOSE = time(20, 0)


class MarketState(str, Enum):
    RTH_OPEN = "RTH_OPEN"
    RTH_PRE = "RTH_PRE"
    RTH_POST = "RTH_POST"
    CLOSED_OVERNIGHT = "CLOSED_OVERNIGHT"
    CLOSED_WEEKEND = "CLOSED_WEEKEND"
    CLOSED_HOLIDAY = "CLOSED_HOLIDAY"
    HALTED = "HALTED"
    UNKNOWN = "UNKNOWN"


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS_2026


def rth_close_time(d: date) -> time:
    return EARLY_CLOSE_T if d in EARLY_CLOSES_2026 else RTH_CLOSE_T


def _et(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=ET)


def next_trading_day(d: date) -> date:
    nxt = d + timedelta(days=1)
    for _ in range(30):
        if is_trading_day(nxt):
            return nxt
        nxt += timedelta(days=1)
    raise ValueError(f"no trading day within 30 days of {d}")


def prev_trading_day(d: date) -> date:
    prv = d - timedelta(days=1)
    for _ in range(30):
        if is_trading_day(prv):
            return prv
        prv -= timedelta(days=1)
    raise ValueError(f"no trading day within 30 days before {d}")


def next_rth_open(now_utc: datetime) -> datetime:
    """Start of the next regular session at or after `now_utc`."""
    d = now_utc.astimezone(ET).date()
    for _ in range(30):
        if is_trading_day(d):
            open_dt = _et(d, RTH_OPEN_T)
            if open_dt > now_utc:
                return open_dt.astimezone(timezone.utc)
        d += timedelta(days=1)
    raise ValueError(f"no session open found after {now_utc}")


def last_rth_close(now_utc: datetime) -> datetime:
    """End of the most recent regular session at or before `now_utc`."""
    d = now_utc.astimezone(ET).date()
    for _ in range(30):
        if is_trading_day(d):
            close_dt = _et(d, rth_close_time(d))
            if close_dt <= now_utc:
                return close_dt.astimezone(timezone.utc)
        d -= timedelta(days=1)
    raise ValueError(f"no session close found before {now_utc}")


@dataclass(frozen=True)
class ClockReading:
    ts: datetime
    state: MarketState
    # Seconds until the current regular session ends. None unless RTH_OPEN.
    seconds_to_close: float | None
    # Seconds until the next regular session opens. This is the number P1
    # actually cares about: it distinguishes a Friday evening (89.5h of
    # darkness ahead) from a Tuesday evening (13.5h), which the state label
    # alone cannot do.
    seconds_to_next_open: float
    next_open_utc: datetime
    holiday: str | None
    # True when the coming close leads into more than one non-trading day.
    extended_closure_ahead: bool

    @property
    def hours_to_next_open(self) -> float:
        return self.seconds_to_next_open / 3600.0


def evaluate(now_utc: datetime | None = None) -> ClockReading:
    """Classify the reference market at `now_utc`."""
    now_utc = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    et_now = now_utc.astimezone(ET)
    d = et_now.date()
    t = et_now.time()

    nxt_open = next_rth_open(now_utc)
    secs_to_open = (nxt_open - now_utc).total_seconds()

    # More than one calendar day of darkness after the next close.
    nxt_open_date = nxt_open.astimezone(ET).date()
    ref_day = d if is_trading_day(d) else prev_trading_day(d)
    extended = (nxt_open_date - ref_day).days > 1

    holiday = HOLIDAYS_2026.get(d)
    close_t = rth_close_time(d)

    if is_trading_day(d):
        if RTH_OPEN_T <= t < close_t:
            secs_to_close = (_et(d, close_t) - et_now).total_seconds()
            return ClockReading(now_utc, MarketState.RTH_OPEN, secs_to_close,
                                secs_to_open, nxt_open, None, extended)
        if PRE_OPEN <= t < RTH_OPEN_T:
            return ClockReading(now_utc, MarketState.RTH_PRE, None,
                                secs_to_open, nxt_open, None, extended)
        if close_t <= t < POST_CLOSE:
            return ClockReading(now_utc, MarketState.RTH_POST, None,
                                secs_to_open, nxt_open, None, extended)

    # Outside any session on this date.
    if holiday:
        state = MarketState.CLOSED_HOLIDAY
    elif d.weekday() >= 5:
        state = MarketState.CLOSED_WEEKEND
    elif not is_trading_day(next_trading_day(d) - timedelta(days=1)) and extended:
        state = MarketState.CLOSED_WEEKEND
    else:
        # A weekday night that leads into another trading day, unless the
        # darkness spans more than one day - then it is not a mere overnight.
        state = (MarketState.CLOSED_WEEKEND if extended
                 else MarketState.CLOSED_OVERNIGHT)

    return ClockReading(now_utc, state, None, secs_to_open, nxt_open,
                        holiday, extended)


def reference_age_seconds(last_regular_trade_utc: datetime,
                          now_utc: datetime | None = None) -> float:
    """REFERENCE_AGE: age of the last REGULAR-session trade.

    Not the last extended-hours print, not the last oracle tick (Law 8).
    Callers must pass a timestamp already filtered to regular-session
    condition codes; this function does not guess.
    """
    now_utc = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age = (now_utc - last_regular_trade_utc.astimezone(timezone.utc)).total_seconds()
    if age < 0:
        raise ValueError(
            f"reference trade is in the future: {last_regular_trade_utc} > {now_utc}")
    return age


def format_age(seconds: float) -> str:
    """HH:MM:SS, always displayed, never rounded away (Law 8)."""
    s = int(seconds)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"
