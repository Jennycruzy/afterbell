"""Optional language-model narration around a deterministic decision.

The guard's receipt rationale is always produced by :mod:`afterbell.guard`.
This adapter can add a qualitative sentence for a human, but it cannot supply
or modify a number, verdict, size, threshold, or gate result. A provider is
opt-in through environment variables; no credential is needed for the guard
or recorder.
"""
from __future__ import annotations

import os
import re
from typing import Any

import httpx


class NarrationUnavailable(RuntimeError):
    """The optional narrator returned no safe qualitative text."""


_NUMERIC_WORDS = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"hundred|thousand|million|percent|percentage|basis|bps|usdt|"
    r"dollar|dollars|price|prices|quantity|notional|size|amount)\b",
    re.IGNORECASE,
)


def _endpoint(url: str) -> str:
    url = url.rstrip("/")
    return url if url.endswith("/chat/completions") else url + "/v1/chat/completions"


class Narrator:
    """Call an OpenAI-compatible chat endpoint for qualitative narration."""

    def __init__(self, url: str | None = None, api_key: str | None = None,
                 model: str | None = None,
                 client: httpx.Client | None = None) -> None:
        self.url = (url if url is not None else
                    os.environ.get("AFTERBELL_NARRATOR_URL", "").strip())
        self.api_key = (api_key if api_key is not None else
                        os.environ.get("AFTERBELL_NARRATOR_API_KEY", "").strip())
        self.model = (model if model is not None else
                      os.environ.get("AFTERBELL_NARRATOR_MODEL", "afterbell-narrator"))
        self.client = client or httpx.Client(timeout=30.0)

    @classmethod
    def from_env(cls) -> "Narrator":
        return cls()

    def narrate(self, decision: Any) -> str:
        """Return deterministic rationale plus safe optional prose."""
        base = getattr(decision, "rationale", None)
        if not isinstance(base, str) or not base:
            raise NarrationUnavailable("decision has no deterministic rationale")
        if not self.url:
            return base
        if not self.api_key:
            raise NarrationUnavailable(
                "AFTERBELL_NARRATOR_URL is configured but the API key is absent")

        prompt = (
            "The following text is the authoritative AFTERBELL decision. "
            "Explain its risk posture in one or two qualitative sentences. "
            "Do not repeat or introduce any digits, numbers, quantities, "
            "prices, units, percentages, basis points, sizes, or verdict "
            "labels. Do not recommend an action and do not change the text.\n\n"
            + base)
        try:
            response = self.client.post(
                _endpoint(self.url),
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json={"model": self.model, "temperature": 0,
                      "messages": [
                          {"role": "system", "content":
                           "You are a narration-only risk explainer. "
                           "Never calculate or alter a deterministic decision."},
                          {"role": "user", "content": prompt},
                      ]})
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise NarrationUnavailable(
                f"narration request failed: {type(exc).__name__}: {exc}") from exc

        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise NarrationUnavailable(
                "narration response omitted choices[0].message.content") from exc
        if not isinstance(text, str) or not text.strip():
            raise NarrationUnavailable("narration response was empty")
        text = text.strip()
        if any(ch.isdigit() for ch in text) or _NUMERIC_WORDS.search(text):
            raise NarrationUnavailable(
                "narration contained a number or measurement; deterministic "
                "rationale remains authoritative")
        return f"{base} Narrator: {text}"
