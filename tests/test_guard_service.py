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


# ---------------- noticing, without being asked ----------------

def test_the_service_records_a_change_only_when_a_band_moves(tmp_path,
                                                             monkeypatch):
    """The loop's initiative, end to end: quiet cycles write nothing."""
    import afterbell.guard_service as gs
    from afterbell.ledger import Ledger
    from tests.test_guard import POL
    from tests.test_posture import state

    monkeypatch.setattr(gs, "POSTURE", tmp_path / "posture.json")

    class _Guard:
        def __init__(self):
            self.ledger = Ledger(tmp_path / "receipts.jsonl")
            self.policy = POL

    guard = _Guard()
    open_market = state(receipt_seq=1, receipt_hash="a")

    assert gs.notice_change(guard, open_market, POL) is None      # first sight
    assert gs.notice_change(guard, open_market, POL) is None      # unchanged

    closed = state(market_state="CLOSED_WEEKEND", status="REDUCE",
                   receipt_seq=2, receipt_hash="b")
    record = gs.notice_change(guard, closed, POL)

    assert record is not None
    assert record["kind"] == "posture_change"
    assert record["authorizes"] is None
    assert {c["band"] for c in record["changed"]} == {"market_state", "verdict"}
    assert "No order was created" in record["explanation"]
    assert gs.notice_change(guard, closed, POL) is None           # settled


def test_a_restart_does_not_invent_a_change(tmp_path, monkeypatch):
    """The bands are reloaded from disk, so the first cycle after a restart
    compares against what was really seen last."""
    import afterbell.guard_service as gs
    from afterbell.ledger import Ledger
    from tests.test_guard import POL
    from tests.test_posture import state

    monkeypatch.setattr(gs, "POSTURE", tmp_path / "posture.json")

    class _Guard:
        def __init__(self):
            self.ledger = Ledger(tmp_path / "receipts.jsonl")
            self.policy = POL

    gs.notice_change(_Guard(), state(), POL)
    assert gs.notice_change(_Guard(), state(), POL) is None
