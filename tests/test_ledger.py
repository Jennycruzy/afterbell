"""Ledger tests. The tampering cases are the point: a chain nobody has tried
to break is not evidence of anything."""
import json

import pytest

from afterbell.ledger import GENESIS, Ledger, head_of, verify


def receipts(led, n=3):
    for i in range(n):
        led.append({"symbol": "NVDABUSDT", "decision": "BLOCK",
                    "allowed_notional": 0.0, "binding_constraint": f"P{i+1}"})


def test_chain_links_and_verifies(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    receipts(led, 3)
    assert led.seq == 3
    assert verify(led.path) == []
    recs = list(led)
    assert recs[0]["prev_hash"] == GENESIS
    assert recs[1]["prev_hash"] == recs[0]["hash"]
    assert recs[2]["prev_hash"] == recs[1]["hash"]
    assert head_of(led.path) == recs[2]["hash"] == led.head


def test_altering_a_field_breaks_the_chain(tmp_path):
    """The refusal that gets quietly turned into an approval is the exact
    attack this exists to make visible."""
    led = Ledger(tmp_path / "l.jsonl")
    receipts(led, 3)
    lines = led.path.read_text().splitlines()
    rec = json.loads(lines[1])
    rec["decision"] = "PASS"
    rec["allowed_notional"] = 5000.0
    lines[1] = json.dumps(rec, sort_keys=True, separators=(",", ":"))
    led.path.write_text("\n".join(lines) + "\n")

    errs = verify(led.path)
    assert errs
    assert any("altered" in e.reason for e in errs)
    # reported precisely at the receipt that was changed, seq 2, rather than
    # cascading across every record after it
    assert {e.seq for e in errs} == {2}


def test_deleting_a_record_is_detected(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    receipts(led, 4)
    lines = led.path.read_text().splitlines()
    del lines[1]
    led.path.write_text("\n".join(lines) + "\n")
    errs = verify(led.path)
    assert any("sequence break" in e.reason for e in errs)


def test_reordering_records_is_detected(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    receipts(led, 3)
    lines = led.path.read_text().splitlines()
    lines[0], lines[1] = lines[1], lines[0]
    led.path.write_text("\n".join(lines) + "\n")
    assert verify(led.path)


def test_appending_a_forged_record_is_detected(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    receipts(led, 2)
    forged = {"seq": 3, "decision": "PASS", "prev_hash": "0" * 64,
              "hash": "f" * 64}
    with led.path.open("a") as fh:
        fh.write(json.dumps(forged, sort_keys=True, separators=(",", ":")) + "\n")
    errs = verify(led.path)
    assert any(e.seq == 3 for e in errs)


def test_caller_cannot_forge_its_position_in_the_chain(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    led.append({"decision": "BLOCK"})
    rec = led.append({"decision": "BLOCK", "seq": 999,
                      "prev_hash": "deadbeef", "hash": "cafe"})
    assert rec["seq"] == 2
    assert rec["prev_hash"] != "deadbeef"
    assert verify(led.path) == []


def test_reopening_resumes_the_existing_chain(tmp_path):
    p = tmp_path / "l.jsonl"
    first = Ledger(p)
    receipts(first, 2)
    head, seq = first.head, first.seq

    second = Ledger(p)          # process restarted
    assert second.head == head and second.seq == seq
    second.append({"decision": "WARN"})
    assert verify(p) == []
    assert list(second)[2]["prev_hash"] == head


def test_stale_ledger_instances_serialize_appends(tmp_path):
    """The recorder-style service and an interactive request share one ledger."""
    p = tmp_path / "l.jsonl"
    first = Ledger(p)
    second = Ledger(p)  # Both were opened at genesis.

    one = first.append({"decision": "BLOCK"})
    two = second.append({"decision": "WARN"})

    assert (one["seq"], two["seq"]) == (1, 2)
    assert two["prev_hash"] == one["hash"]
    assert verify(p) == []


def test_empty_ledger_starts_at_genesis(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    assert led.head == GENESIS and led.seq == 0
    assert head_of(led.path) is None


def test_append_does_not_full_verify_chain_again(tmp_path, monkeypatch):
    import afterbell.ledger as ledger_module
    path = tmp_path / "l.jsonl"
    led = Ledger(path)
    led.append({"decision": "BLOCK"})
    monkeypatch.setattr(
        ledger_module, "verify",
        lambda unused: pytest.fail("append performed a full ledger scan"))
    rec = led.append({"decision": "WARN"})
    assert rec["seq"] == 2 and head_of(path) == rec["hash"]
