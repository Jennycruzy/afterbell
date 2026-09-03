from types import SimpleNamespace

import httpx
import pytest

from afterbell.rationale import NarrationUnavailable, Narrator


DECISION = SimpleNamespace(
    rationale="BLOCK: BUY NVDABUSDT requested; REFERENCE_AGE 12:00:00.")


def client_for(payload):
    def handler(request):
        return httpx.Response(
            200, json=payload, request=httpx.Request("POST", str(request.url)))
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_no_provider_returns_authoritative_deterministic_rationale():
    narrator = Narrator(url="", api_key="", client=httpx.Client())
    assert narrator.narrate(DECISION) == DECISION.rationale


def test_provider_can_add_only_qualitative_text():
    narrator = Narrator(
        url="https://llm.example/v1/chat/completions", api_key="secret",
        model="test", client=client_for({
            "choices": [{"message": {"content":
                "The reference is stale, so the proposed exposure is unsafe."}}]}))
    text = narrator.narrate(DECISION)
    assert text.startswith(DECISION.rationale)
    assert "Narrator:" in text


@pytest.mark.parametrize("content", [
    "The limit is 600.",
    "The two clocks disagree.",
    "The basis is wide in bps.",
])
def test_numeric_or_measurement_text_is_rejected(content):
    narrator = Narrator(
        url="https://llm.example/v1/chat/completions", api_key="secret",
        client=client_for({"choices": [{"message": {"content": content}}]}))
    with pytest.raises(NarrationUnavailable, match="number or measurement"):
        narrator.narrate(DECISION)


def test_provider_shape_failure_is_loud():
    narrator = Narrator(
        url="https://llm.example", api_key="secret",
        client=client_for({"not_choices": []}))
    with pytest.raises(NarrationUnavailable, match="omitted"):
        narrator.narrate(DECISION)
