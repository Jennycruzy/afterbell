"""Yahoo reference provider.

The provider's timestamp is never trusted on its own. Every case here is about
what happens when the provider and this project's exchange calendar disagree.
"""
from datetime import datetime, timezone

import pytest

from afterbell.reference import ReferenceUnavailable, from_yahoo


def U(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def meta(price=224.41, ts="2026-09-02T20:00:00"):
    return {"regularMarketPrice": price,
            "regularMarketTime": int(U(ts).timestamp())}


def test_closing_bell_stamp_becomes_a_session_close():
    """The bell reads as RTH_POST on the clock, and is still a regular print."""
    r = from_yahoo("NVDA", meta(), now=U("2026-09-03T10:00:00"))
    assert r.source == "session_close"
    assert r.provider == "yahoo"
    assert r.price == 224.41
    assert r.ts == U("2026-09-02T20:00:00")


def test_reference_age_needs_no_restamping():
    """The whole reason for preferring this provider.

    Alpaca's daily bar is stamped 04:00Z and has to be moved to the real bell
    before REFERENCE_AGE means anything. Here the stamp is already the bell.
    """
    now = U("2026-09-03T10:00:00")
    r = from_yahoo("NVDA", meta(), now=now)
    assert (now - r.ts).total_seconds() == pytest.approx(14 * 3600)


def test_intraday_stamp_is_a_regular_trade():
    r = from_yahoo("NVDA", meta(ts="2026-09-03T17:00:00"),
                   now=U("2026-09-03T17:00:30"))
    assert r.source == "regular_trade"
    assert not r.is_extended


def test_stamp_outside_any_session_is_refused():
    """A provider asserting a regular print at 02:00Z disagrees with the
    calendar, and the calendar wins."""
    with pytest.raises(ReferenceUnavailable, match="outside any regular"):
        from_yahoo("NVDA", meta(ts="2026-09-03T02:00:00"),
                   now=U("2026-09-03T10:00:00"))


def test_weekend_stamp_is_refused():
    with pytest.raises(ReferenceUnavailable, match="outside any regular"):
        from_yahoo("NVDA", meta(ts="2026-09-05T14:00:00"),
                   now=U("2026-09-05T15:00:00"))


def test_future_stamp_is_refused():
    """A reference from the future is a broken clock, not a fresh price."""
    with pytest.raises(ReferenceUnavailable, match="future"):
        from_yahoo("NVDA", meta(ts="2026-09-03T17:00:00"),
                   now=U("2026-09-03T16:00:00"))


@pytest.mark.parametrize("bad", [
    {}, {"regularMarketPrice": 224.41}, {"regularMarketTime": 1788379200}])
def test_missing_fields_refuse_rather_than_default(bad):
    with pytest.raises(ReferenceUnavailable):
        from_yahoo("NVDA", bad, now=U("2026-09-03T10:00:00"))


def test_holiday_stamp_is_refused():
    """Labor Day, 7 Sep 2026. No regular session, so no regular print."""
    with pytest.raises(ReferenceUnavailable, match="outside any regular"):
        from_yahoo("NVDA", meta(ts="2026-09-07T17:00:00"),
                   now=U("2026-09-07T18:00:00"))
