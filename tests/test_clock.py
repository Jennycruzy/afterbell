"""Clock tests, anchored on the Labor Day weekend the build is aimed at."""
from datetime import datetime, timezone

import pytest

from afterbell.clock import (
    HOLIDAYS_2026, MarketState, evaluate, format_age, is_trading_day,
    last_rth_close, next_rth_open, reference_age_seconds,
)


def U(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


BELL = U("2026-09-04T20:00:00")      # Friday close, ET 16:00
REOPEN = U("2026-09-08T13:30:00")    # Tuesday open, ET 09:30


def test_labor_day_is_closed():
    # Independently confirmed against Alpaca /v2/calendar, which returns
    # 2026-09-03, 2026-09-04, 2026-09-08 - with 2026-09-07 absent.
    assert not is_trading_day(REOPEN.date().replace(day=7))
    assert HOLIDAYS_2026[REOPEN.date().replace(day=7)] == "Labor Day"


def test_reference_gap_is_eighty_nine_and_a_half_hours():
    assert next_rth_open(BELL) == REOPEN
    assert (REOPEN - BELL).total_seconds() == pytest.approx(89.5 * 3600)
    assert format_age(reference_age_seconds(BELL, REOPEN)) == "89:30:00"


@pytest.mark.parametrize("ts,expected", [
    ("2026-09-03T13:35:00", MarketState.RTH_OPEN),
    ("2026-09-03T12:00:00", MarketState.RTH_PRE),
    ("2026-09-04T19:55:00", MarketState.RTH_OPEN),   # five minutes to the bell
    ("2026-09-04T20:01:00", MarketState.RTH_POST),
    ("2026-09-05T03:00:00", MarketState.CLOSED_WEEKEND),
    ("2026-09-06T12:00:00", MarketState.CLOSED_WEEKEND),
    ("2026-09-07T15:00:00", MarketState.CLOSED_HOLIDAY),
    ("2026-09-08T13:31:00", MarketState.RTH_OPEN),
    ("2026-09-09T02:00:00", MarketState.CLOSED_OVERNIGHT),
])
def test_states(ts, expected):
    assert evaluate(U(ts)).state is expected


def test_bell_transition_is_exact():
    assert evaluate(U("2026-09-04T19:59:59")).state is MarketState.RTH_OPEN
    assert evaluate(U("2026-09-04T20:00:00")).state is MarketState.RTH_POST


def test_extended_closure_flag_separates_friday_from_tuesday():
    """The state label alone cannot tell these apart; the flag and the
    hours-to-next-open must, because P1 sizes on the darkness ahead."""
    friday = evaluate(U("2026-09-04T23:00:00"))
    tuesday = evaluate(U("2026-09-08T23:00:00"))
    assert friday.state is tuesday.state is MarketState.RTH_POST
    assert friday.extended_closure_ahead and not tuesday.extended_closure_ahead
    assert friday.hours_to_next_open > 86
    assert tuesday.hours_to_next_open < 15


def test_ramp_window_before_the_bell():
    r = evaluate(U("2026-09-04T19:55:00"))
    assert r.seconds_to_close == pytest.approx(300, abs=1)


def test_reference_age_refuses_a_future_timestamp():
    """Law 3: a nonsensical reference halts rather than producing a basis."""
    with pytest.raises(ValueError):
        reference_age_seconds(REOPEN, BELL)


def test_last_close_before_the_weekend():
    assert last_rth_close(U("2026-09-06T12:00:00")) == BELL
    assert last_rth_close(U("2026-09-07T23:00:00")) == BELL


def test_early_close_is_respected():
    """Christmas Eve 2026 closes at 13:00 ET, not 16:00."""
    assert evaluate(U("2026-12-24T19:00:00")).state is MarketState.RTH_POST
