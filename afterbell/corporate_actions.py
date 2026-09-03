"""Corporate-action lookahead backed by Alpaca's real data client.

This module is deliberately separate from the reference-price provider. Yahoo
remains the default price source for AFTERBELL. Alpaca is consulted here only
when an operator supplies Alpaca credentials and asks P4 for future corporate
actions. A failed or malformed response is raised; the guard never treats a
missing announcement feed as a clean result.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from alpaca.data.enums import CorporateActionsType
from alpaca.data.historical.corporate_actions import CorporateActionsClient
from alpaca.data.requests import CorporateActionsRequest


class CorporateActionUnavailable(RuntimeError):
    """Raised when the corporate-action source cannot be verified."""


@dataclass(frozen=True)
class CorporateAction:
    """One upcoming action selected from an Alpaca response."""

    symbol: str
    action_type: str
    event_date: date
    action_id: str | None = None

    @property
    def label(self) -> str:
        suffix = f" ({self.action_id})" if self.action_id else ""
        return f"{self.action_type} on {self.event_date.isoformat()}{suffix}"


def _model_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        result = dump()
        if isinstance(result, dict):
            return result
    raise CorporateActionUnavailable(
        f"unexpected Alpaca corporate-action item: {type(value).__name__}")


def _response_data(value: Any) -> dict[str, list[Any]]:
    data = getattr(value, "data", value)
    if not isinstance(data, dict):
        raise CorporateActionUnavailable(
            f"unexpected Alpaca corporate-action response: {type(data).__name__}")
    for symbol, items in data.items():
        if not isinstance(symbol, str) or not isinstance(items, list):
            raise CorporateActionUnavailable(
                "Alpaca corporate-action response has an invalid data bucket")
    return data


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise CorporateActionUnavailable(
                f"invalid corporate-action date {value!r}") from exc
    if value is None:
        return None
    raise CorporateActionUnavailable(
        f"invalid corporate-action date type {type(value).__name__}")


def _event_dates(row: dict[str, Any]) -> list[date]:
    # The current Alpaca data API exposes process/ex/record/payable dates;
    # split and merger variants may use effective_date. We retain every date
    # because any upcoming date is relevant to a new entry.
    keys = ("process_date", "effective_date", "ex_date", "record_date",
            "payable_date", "due_bill_on_date", "due_bill_off_date",
            "due_bill_redemption_date")
    result = []
    for key in keys:
        parsed = _as_date(row.get(key))
        if parsed is not None:
            result.append(parsed)
    if not result:
        raise CorporateActionUnavailable(
            "corporate-action item has no usable event date")
    return result


class AlpacaCorporateActions:
    """Read-only corporate-action client with strict response validation."""

    def __init__(self, api_key: str, secret_key: str,
                 client: Any | None = None) -> None:
        if not api_key or not secret_key:
            raise CorporateActionUnavailable(
                "Alpaca corporate-action credentials are not configured")
        self.client = client or CorporateActionsClient(
            api_key=api_key, secret_key=secret_key)

    def upcoming(self, symbol: str, now: datetime,
                 lookahead_hours: float) -> list[CorporateAction]:
        now = now.astimezone(timezone.utc)
        if lookahead_hours < 0:
            raise ValueError("corporate-action lookahead cannot be negative")
        start = now.date()
        end = (now + timedelta(hours=lookahead_hours)).date()
        request = CorporateActionsRequest(
            symbols=[symbol.upper()],
            types=list(CorporateActionsType),
            start=start, end=end, limit=1000)
        try:
            response = self.client.get_corporate_actions(request)
        except Exception as exc:
            raise CorporateActionUnavailable(
                f"Alpaca corporate-action request failed: "
                f"{type(exc).__name__}: {exc}") from exc

        rows = _response_data(response)
        events: list[CorporateAction] = []
        for bucket_symbol, items in rows.items():
            for item in items:
                row = _model_dict(item)
                dates = [d for d in _event_dates(row)
                         if start <= d <= end]
                if not dates:
                    continue
                action_type = row.get("corporate_action_type") or row.get("ca_type")
                if not isinstance(action_type, str) or not action_type:
                    raise CorporateActionUnavailable(
                        "corporate-action item has no type")
                action_symbol = (row.get("symbol") or row.get("initiating_symbol")
                                 or bucket_symbol)
                if not isinstance(action_symbol, str) or not action_symbol:
                    raise CorporateActionUnavailable(
                        "corporate-action item has no symbol")
                action_id = row.get("id")
                events.append(CorporateAction(
                    symbol=action_symbol.upper(),
                    action_type=action_type,
                    event_date=min(dates),
                    action_id=str(action_id) if action_id is not None else None))
        return sorted(events, key=lambda x: (x.event_date, x.action_type,
                                             x.symbol, x.action_id or ""))
