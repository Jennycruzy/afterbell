import httpx
import pytest

from afterbell.instruments import REGISTRY
from afterbell.public_checks import PublicCheckUnavailable, PublicChecks


def response(payload, status=200):
    return httpx.Response(status, json=payload,
                          request=httpx.Request("GET", "https://test"))


def checks_for(payload):
    def handler(request):
        return response(payload)
    return PublicChecks(httpx.Client(transport=httpx.MockTransport(handler)))


def test_rwa_status_requires_real_fields():
    checks = checks_for({"success": True, "data": {
        "openState": True, "reasonCode": "TRADING",
        "reasonMsg": None, "marketStatus": None,
    }})
    status = checks.rwa_status(REGISTRY["NVDABUSDT"])
    assert status.open_state is True
    assert status.reason_code == "TRADING"


def test_unsupported_audit_is_not_called_clean():
    checks = checks_for({"success": True, "data": {
        "hasResult": False, "isSupported": False,
        "riskLevelEnum": "LOW", "riskItems": [],
    }})
    audit = checks.token_audit(REGISTRY["NVDABUSDT"].contract)
    assert audit.status == "UNSUPPORTED"
    assert audit.safe is None


@pytest.mark.parametrize("level, safe", [("LOW", True), ("HIGH", False), (4, False)])
def test_audit_risk_level_is_deterministic(level, safe):
    checks = checks_for({"success": True, "data": {
        "hasResult": True, "isSupported": True,
        "riskLevelEnum": level, "riskItems": [],
    }})
    audit = checks.token_audit(REGISTRY["NVDABUSDT"].contract)
    assert audit.status == ("SAFE" if safe else "UNSAFE")
    assert audit.safe is safe


def test_public_check_failure_is_loud():
    checks = checks_for({"success": False, "data": None})
    with pytest.raises(PublicCheckUnavailable):
        checks.rwa_status(REGISTRY["NVDABUSDT"])
