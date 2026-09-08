"""The continuous dashboard monitor must leave auditable receipts."""
from types import SimpleNamespace

from afterbell import guard_service as service
from afterbell.guard import OrderRequest
from afterbell.measure import Side


def test_evaluate_once_records_and_links_receipt(monkeypatch, tmp_path):
    decision = SimpleNamespace(verdict=SimpleNamespace(value="BLOCK"),
                               allowed_notional=0.0,
                               requested_notional=5000.0,
                               binding_constraint="P1")
    seen = {}

    class FakeGuard:
        ledger = SimpleNamespace(seq=18, head="a" * 64)

        def build_context(self, req):
            seen["built"] = req
            return object()

        def evaluate(self, req, context):
            seen["evaluated"] = (req, context)
            return decision

    receipt = {
        "market_state": "CLOSED_WEEKEND", "reference_age_s": 1.0,
        "reference_age": "00:00:01", "reference_price": 1.0,
        "reference_ts": "2026-09-03T00:00:00Z", "token_price": 1.0,
        "gates": {}, "gate_detail": {}, "measurements": {},
        "policy_sha256": "policy", "policy_status": "CALIBRATED", "rationale": "blocked",
    }
    written = {}
    monkeypatch.setattr(service, "to_receipt", lambda d, r: receipt)
    monkeypatch.setattr(service, "_write_json",
                        lambda path, value: written.setdefault("state", value))
    monkeypatch.setattr(service, "HEARTBEAT", tmp_path / "heartbeat")
    req = OrderRequest("NVDABUSDT", Side.BUY, 5000.0,
                       evaluation_source="continuous_read_only_monitor")

    assert service.evaluate_once(FakeGuard(), req) is decision
    assert seen["evaluated"][0] is req
    assert written["state"]["receipt_seq"] == 18
    assert written["state"]["receipt_hash"] == "a" * 64
    assert written["state"]["evaluation_source"] == "continuous_read_only_monitor"
    assert (tmp_path / "heartbeat").exists()
