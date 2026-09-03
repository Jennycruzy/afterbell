from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from afterbell.corporate_actions import (
    AlpacaCorporateActions, CorporateActionUnavailable,
)


NOW = datetime(2026, 9, 3, 15, 0, tzinfo=timezone.utc)


class FakeClient:
    def __init__(self, data):
        self.data = data
        self.request = None

    def get_corporate_actions(self, request):
        self.request = request
        return SimpleNamespace(data=self.data)


def test_lookahead_uses_real_sdk_request_and_sorts_events():
    fake = FakeClient({"NVDA": [
        {"id": "split", "corporate_action_type": "forward_split",
         "symbol": "NVDA", "process_date": date(2026, 9, 4),
         "ex_date": date(2026, 9, 5)},
        {"id": "div", "corporate_action_type": "cash_dividend",
         "symbol": "NVDA", "process_date": date(2026, 9, 3),
         "ex_date": date(2026, 9, 3)},
    ]})
    source = AlpacaCorporateActions("key", "secret", client=fake)

    events = source.upcoming("nvda", NOW, 48)

    assert [e.action_type for e in events] == ["cash_dividend", "forward_split"]
    assert events[0].event_date == date(2026, 9, 3)
    assert events[0].label.startswith("cash_dividend on 2026-09-03")
    assert fake.request.symbols == ["NVDA"]
    assert fake.request.start == date(2026, 9, 3)
    assert fake.request.end == date(2026, 9, 5)


def test_events_outside_window_are_not_selected():
    fake = FakeClient({"NVDA": [{
        "id": "old", "corporate_action_type": "cash_dividend",
        "symbol": "NVDA", "process_date": date(2026, 9, 2),
        "ex_date": date(2026, 9, 2),
    }]})
    source = AlpacaCorporateActions("key", "secret", client=fake)
    assert source.upcoming("NVDA", NOW, 24) == []


def test_malformed_action_fails_loudly():
    fake = FakeClient({"NVDA": [{"id": "bad", "symbol": "NVDA",
                                  "corporate_action_type": "split"}]})
    source = AlpacaCorporateActions("key", "secret", client=fake)
    with pytest.raises(CorporateActionUnavailable, match="no usable event date"):
        source.upcoming("NVDA", NOW, 24)


def test_source_failure_fails_loudly():
    class Broken:
        def get_corporate_actions(self, request):
            raise TimeoutError("network down")

    source = AlpacaCorporateActions("key", "secret", client=Broken())
    with pytest.raises(CorporateActionUnavailable, match="request failed"):
        source.upcoming("NVDA", NOW, 24)


def test_credentials_are_required():
    with pytest.raises(CorporateActionUnavailable, match="not configured"):
        AlpacaCorporateActions("", "secret")
