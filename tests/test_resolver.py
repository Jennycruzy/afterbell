"""Resolver tests. The refusals are the interesting cases."""
import pytest

from afterbell.instruments import REGISTRY
from afterbell.resolver import (
    ContractStatus, ResolutionStatus, render_panel, resolve, verify_contract,
)

NVDA_CONTRACT = "0x02Fca66C1D1aFB4E2A7884261eB00F63598a7436"


@pytest.mark.parametrize("q", [
    "nvidia", "NVIDIA", "  Nvidia  ", "nvda", "NVDAB", "nvdabusdt",
    "buy some nvidia now", "please buy Nvidia",
])
def test_resolves_nvidia_variants(q):
    r = resolve(q)
    assert r.resolved and r.instrument.token_symbol == "NVDABUSDT"


def test_resolution_carries_the_whole_chain():
    i = resolve("buy Nvidia").instrument
    assert i.underlying == "NVDA"
    assert i.token_asset == "NVDAB"
    assert "BTech Holdings" in i.issuer
    assert "NOT direct share ownership" in i.instrument_class
    assert i.network == "BNB Smart Chain"
    assert i.contract == NVDA_CONTRACT


def test_unknown_instrument_is_refused_not_guessed():
    r = resolve("buy Apple")
    assert r.status is ResolutionStatus.UNKNOWN_INSTRUMENT
    assert not r.resolved and r.instrument is None


def test_ambiguous_request_is_refused():
    r = resolve("rotate from nvidia into tesla")
    assert r.status is ResolutionStatus.AMBIGUOUS
    assert set(r.candidates) == {"NVDABUSDT", "TSLABUSDT"}
    assert not r.resolved


def test_empty_request_is_refused():
    assert not resolve("   ").resolved


def test_canonical_contract_matches_case_insensitively():
    """EIP-55 mixed case carries no address information."""
    assert verify_contract("NVDABUSDT", NVDA_CONTRACT).canonical
    assert verify_contract("NVDABUSDT", NVDA_CONTRACT.lower()).canonical
    assert verify_contract("NVDABUSDT", NVDA_CONTRACT.upper()).canonical


def test_counterfeit_is_blocked_even_when_the_audit_passes():
    """The point of P6: either check alone is insufficient."""
    c = verify_contract("NVDABUSDT", "0xDEADBEEF00000000000000000000000000000000",
                        audit_verdict="no honeypot detected")
    assert c.status is ContractStatus.MISMATCH
    assert not c.canonical
    assert c.audit_verdict == "no honeypot detected"


def test_missing_contract_is_not_a_pass():
    c = verify_contract("NVDABUSDT", None)
    assert c.status is ContractStatus.NOT_PROVIDED
    assert not c.canonical


def test_every_registry_symbol_verifies_against_itself():
    for sym, inst in REGISTRY.items():
        assert verify_contract(sym, inst.contract).canonical


def test_unknown_symbol_raises():
    with pytest.raises(KeyError):
        verify_contract("APPLEBUSDT", NVDA_CONTRACT)


def test_panel_titles_a_resolved_chain_as_resolution():
    assert render_panel(resolve("buy Nvidia"), "CLOSED", "0:0", None, None
                        ).startswith("INSTRUMENT RESOLUTION")


def test_panel_states_the_block_on_a_counterfeit():
    c = verify_contract("NVDABUSDT", "0xDEAD", audit_verdict="no honeypot detected")
    panel = render_panel(resolve("nvidia"), "CLOSED", "61:14:22", 182.0, "WATCH", c)
    assert "BLOCKED - non-canonical asset" in panel
    assert "either check alone is insufficient" in panel


def test_panel_states_it_is_not_share_ownership():
    panel = render_panel(resolve("buy Nvidia"), "CLOSED", "61:14:00",
                         182.0, "WATCH")
    assert "NOT direct share ownership" in panel
    assert "BTech Holdings" in panel
    assert "61:14:00" in panel
    assert "+182 bps" in panel


def test_panel_for_unresolved_request_says_refused():
    panel = render_panel(resolve("buy Apple"), "CLOSED", "61:14:00", None, None)
    assert "REFUSED" in panel and "UNRESOLVED" in panel
