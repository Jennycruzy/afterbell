"""Instrument resolution and canonical-contract verification (identity and contract verification).

The identity check exists because "buy Nvidia" is a category error waiting to happen. The
request names a company; what is actually purchasable is a certificate issued
by a Binance affiliate, referencing a share, trading on a venue that never
closes, against a reference market that is shut most of the week. The guard
refuses to act until that whole chain is resolved and shown.

The contract-verification check exists because bStocks can be withdrawn to self-custody on BNB Chain, so
counterfeit BEP-20 tokens carrying these names are inevitable. A contract can
pass a security audit and still not be the canonical asset. The registry check
and the audit are independent, and both are required: the demonstrative case is
a counterfeit that the audit clears and the registry blocks anyway.

Law 5: nothing here produces a number. Resolution is a deterministic lookup
over a checked-in table. A model may phrase the question; it never answers it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from afterbell.instruments import REGISTRY, Instrument, TOKEN_SYMBOLS

# Company names and common shorthands for the five launch instruments. Kept
# explicit rather than fuzzy-matched: a resolver that guesses is a resolver
# that will eventually guess wrong on a live order.
ALIASES: dict[str, str] = {
    "nvidia": "NVDABUSDT", "nvidia corp": "NVDABUSDT", "nvda": "NVDABUSDT",
    "nvdab": "NVDABUSDT", "nvdabusdt": "NVDABUSDT",
    "tesla": "TSLABUSDT", "tesla inc": "TSLABUSDT", "tsla": "TSLABUSDT",
    "tslab": "TSLABUSDT", "tslabusdt": "TSLABUSDT",
    "micron": "MUBUSDT", "micron technology": "MUBUSDT", "mu": "MUBUSDT",
    "mub": "MUBUSDT", "mubusdt": "MUBUSDT",
    "circle": "CRCLBUSDT", "circle internet": "CRCLBUSDT", "crcl": "CRCLBUSDT",
    "crclb": "CRCLBUSDT", "crclbusdt": "CRCLBUSDT",
    "sandisk": "SNDKBUSDT", "sandisk corp": "SNDKBUSDT", "sndk": "SNDKBUSDT",
    "sndkb": "SNDKBUSDT", "sndkbusdt": "SNDKBUSDT",
}


class ResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    UNKNOWN_INSTRUMENT = "UNKNOWN_INSTRUMENT"
    AMBIGUOUS = "AMBIGUOUS"


class ContractStatus(str, Enum):
    CANONICAL = "CANONICAL"
    MISMATCH = "MISMATCH"
    NOT_PROVIDED = "NOT_PROVIDED"


@dataclass(frozen=True)
class Resolution:
    query: str
    status: ResolutionStatus
    instrument: Instrument | None = None
    candidates: tuple[str, ...] = ()
    note: str = ""

    @property
    def resolved(self) -> bool:
        return self.status is ResolutionStatus.RESOLVED


@dataclass(frozen=True)
class ContractCheck:
    symbol: str
    expected: str
    observed: str | None
    status: ContractStatus
    audit_verdict: str | None = None
    audit_status: str | None = None
    audit_supported: bool | None = None
    audit_passed: bool | None = None

    @property
    def canonical(self) -> bool:
        return self.status is ContractStatus.CANONICAL


_MAX_ALIAS_WORDS = max(len(a.split()) for a in ALIASES)

# A token is a run of word characters, and non-ASCII letters are word
# characters here on purpose. "nvdaa" spelled with a trailing Cyrillic A must
# come out as one unfamiliar token rather than as the ticker plus a separator,
# because a lookalike ticker is not the ticker.
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def _phrases(q: str) -> set[str]:
    """Every 1..n word phrase in the request, for matching whole aliases.

    Matching on raw substrings is what a fuzzy resolver looks like from the
    inside. The alias "mu" occurs in "must", "much" and "amused", so
    "I must act now" resolved to Micron - an instrument the request never
    named - and "buy nvidia, must fill today" read as two instruments and was
    refused as ambiguous. Both directions are wrong on a live order. Aliases
    are matched as whole words, and multi-word aliases as adjacent runs of
    them.
    """
    words = _TOKEN.findall(q)
    return {" ".join(words[i:i + n])
            for n in range(1, _MAX_ALIAS_WORDS + 1)
            for i in range(len(words) - n + 1)}


def resolve(query: str) -> Resolution:
    """Resolve a request to exactly one instrument, or refuse."""
    if not query or not query.strip():
        return Resolution(query, ResolutionStatus.UNKNOWN_INSTRUMENT,
                          note="empty request")
    q = query.strip().lower()

    if q in ALIASES:
        return Resolution(query, ResolutionStatus.RESOLVED,
                          REGISTRY[ALIASES[q]])

    hits = {sym for alias, sym in ALIASES.items() if alias in _phrases(q)}
    if len(hits) == 1:
        return Resolution(query, ResolutionStatus.RESOLVED,
                          REGISTRY[hits.pop()])
    if len(hits) > 1:
        return Resolution(
            query, ResolutionStatus.AMBIGUOUS,
            candidates=tuple(sorted(hits)),
            note="request names more than one instrument")
    return Resolution(
        query, ResolutionStatus.UNKNOWN_INSTRUMENT,
        candidates=tuple(TOKEN_SYMBOLS),
        note="no tokenized instrument in the canonical registry matches")


def verify_contract(token_symbol: str, observed_contract: str | None,
                    audit_verdict: str | None = None, *,
                    audit_status: str | None = None,
                    audit_supported: bool | None = None,
                    audit_passed: bool | None = None) -> ContractCheck:
    """Check an observed contract address against the canonical registry.

    Address comparison is case-insensitive: EIP-55 mixed-case checksums encode
    no address information, so two spellings of the same address are the same
    address and must not read as a mismatch.

    A missing address is NOT_PROVIDED, which is not a pass. The caller decides
    what that means; on-chain delivery without an address is not verifiable and
    the guard treats it as a hard failure.
    """
    inst = REGISTRY.get(token_symbol)
    if inst is None:
        raise KeyError(f"{token_symbol} is not in the canonical registry")
    if observed_contract is None or not observed_contract.strip():
        return ContractCheck(token_symbol, inst.contract, None,
                             ContractStatus.NOT_PROVIDED, audit_verdict,
                             audit_status, audit_supported, audit_passed)
    ok = observed_contract.strip().lower() == inst.contract.lower()
    return ContractCheck(
        token_symbol, inst.contract, observed_contract.strip(),
        ContractStatus.CANONICAL if ok else ContractStatus.MISMATCH,
        audit_verdict, audit_status, audit_supported, audit_passed)


def render_panel(res: Resolution, reference_state: str, reference_age: str,
                 basis_bps: float | None, basis_band: str | None,
                 contract: ContractCheck | None = None) -> str:
    """The resolution panel shown before acting.

    Every value here is passed in already computed. This function formats; it
    does not calculate, and it never sources a number of its own (Law 5).
    """
    if not res.resolved or res.instrument is None:
        lines = ["UNRESOLVED INSTRUMENT", "",
                 f"  Request           {res.query!r}",
                 f"  Status            {res.status.value}",
                 f"  Note              {res.note}"]
        if res.candidates:
            lines.append(f"  Known instruments {', '.join(res.candidates)}")
        lines += ["", "  REFUSED - the guard does not act on an unresolved",
                  "  instrument."]
        return "\n".join(lines)

    i = res.instrument
    basis_txt = ("unavailable" if basis_bps is None
                 else f"{basis_bps:+.0f} bps  [{basis_band}]")
    # The spec's mockup titles this panel "AMBIGUOUS INSTRUMENT". That reads
    # wrong above a cleanly resolved chain: the request was ambiguous, the
    # instrument no longer is. The panel exists to show the resolution.
    lines = [
        "INSTRUMENT RESOLUTION", "",
        f"  Request           {res.query!r}",
        f"  Underlying        {i.underlying} - {i.underlying_name}",
        f"  Available token   {i.token_asset} - {i.underlying} bStock",
        f"  Issuer            {i.issuer}",
        f"  Instrument class  {i.instrument_class}",
        f"  Network           {i.network}",
    ]
    if contract is None:
        lines.append(f"  Contract          {i.contract}  (canonical)")
    else:
        mark = {"CANONICAL": "match", "MISMATCH": "MISMATCH",
                "NOT_PROVIDED": "not provided"}[contract.status.value]
        lines.append(f"  Expected          {i.contract}")
        lines.append(f"  Observed          {contract.observed or '-'}")
        lines.append(f"  Canonical match   {mark}")
        if contract.audit_verdict:
            lines.append(f"  Token audit       {contract.audit_verdict}")
        elif contract.audit_status:
            lines.append(f"  Token audit       {contract.audit_status}")
    lines += [
        "  Token market      OPEN (24/7)",
        f"  Reference market  {reference_state} - {reference_age}",
        f"  Basis             {basis_txt}",
    ]
    if contract is not None and not contract.canonical:
        lines += ["",
                  "  RESULT            BLOCKED - non-canonical asset"]
        if contract.audit_verdict:
            lines.append("                    the audit passed and the guard "
                         "blocked it anyway;")
            lines.append("                    either check alone is "
                         "insufficient.")
    return "\n".join(lines)
