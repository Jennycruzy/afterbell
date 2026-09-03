"""Hash-chained receipt ledger.

Law 4: every evaluation leaves a receipt, and the refusals are the product.
Binance can see the orders an agent places; its VP of Product has said publicly
that Binance cannot see the agent's reasoning. This ledger is the answer to
that - an append-only record in which any altered, removed, reordered or
forged receipt is identified by sequence number when the chain is re-derived,
and whose daily head hash is published.

    hash = sha256(prev_hash || canonical_json(record_without_hash))

Canonical JSON here means sorted keys, no insignificant whitespace, UTF-8. The
genesis record chains from 64 zeros.
"""
from __future__ import annotations

import hashlib
import json
import os
import fcntl
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

GENESIS = "0" * 64
_HASH_FIELD = "hash"


def canonical_json(record: dict[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def compute_hash(prev_hash: str, record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != _HASH_FIELD}
    payload = prev_hash.encode() + canonical_json(body).encode()
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class ChainError:
    seq: int | None
    line_no: int
    reason: str


class Ledger:
    """Append-only, hash-chained JSONL.

    Opened in append mode with a flush and fsync per record: a receipt that is
    still sitting in a buffer when the process dies is a receipt that does not
    exist, and the demonstration depends on records written at moments when
    nobody is watching the terminal.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        # Opening instances concurrently must not make them disagree about
        # the starting head. append() refreshes again under the same lock.
        with self._exclusive_lock():
            self._seq, self._head = self._resume()

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        """Serialize ledger writers, including separate service processes.

        The guard service and an interactive executor can both leave receipts.
        A process-local sequence counter would let them append different
        records at the same position, destroying the evidence chain. flock is
        deliberately attached to a sibling lock file so it remains effective
        while the JSONL itself is opened, flushed and fsynced per record.
        """
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _resume(self) -> tuple[int, str]:
        """Pick up from the existing chain, or start a new one."""
        if not self.path.exists() or self.path.stat().st_size == 0:
            return 0, GENESIS
        last = None
        with self.path.open() as fh:
            for line in fh:
                if line.strip():
                    last = line
        if last is None:
            return 0, GENESIS
        errors = verify(self.path)
        if errors:
            first = errors[0]
            raise RuntimeError(
                f"receipt ledger verification failed at line {first.line_no}: "
                f"{first.reason}")
        rec = json.loads(last)
        return int(rec["seq"]), str(rec[_HASH_FIELD])

    @property
    def head(self) -> str:
        """Current head hash - the value published daily."""
        return self._head

    @property
    def seq(self) -> int:
        return self._seq

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        """Append one receipt and return it, complete with seq/prev_hash/hash.

        `seq`, `ts`, `prev_hash` and `hash` are assigned here and any caller
        supplied values for them are overwritten, so a caller cannot forge a
        position in the chain.
        """
        with self._exclusive_lock():
            # Another long-lived process may have appended after this Ledger
            # object was constructed. Refresh *inside* the exclusive lock;
            # correctness is more important than avoiding this small scan in
            # a six-day evidence ledger.
            self._seq, self._head = self._resume()
            rec = dict(record)
            rec["seq"] = self._seq + 1
            rec.setdefault("ts", datetime.now(timezone.utc)
                           .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z")
            rec["prev_hash"] = self._head
            rec[_HASH_FIELD] = compute_hash(self._head, rec)

            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(canonical_json(rec) + "\n")
                fh.flush()
                os.fsync(fh.fileno())

            self._seq = rec["seq"]
            self._head = rec[_HASH_FIELD]
            return rec

    def __iter__(self) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)


def verify(path: str | Path) -> list[ChainError]:
    """Re-derive every hash. An empty list means the chain is intact.

    Detects edited fields, removed records, reordered records and appended
    forgeries, because each record's hash commits to its predecessor's.

    Verification continues from each record's stored hash rather than from the
    recomputed one, so an altered receipt is reported at its own sequence
    number instead of cascading a false alarm across every record after it.
    Identifying which receipt was changed is more useful than reporting that
    everything downstream of it looks wrong.
    """
    path = Path(path)
    errors: list[ChainError] = []
    if not path.exists():
        return [ChainError(None, 0, f"ledger does not exist: {path}")]

    prev_hash = GENESIS
    expected_seq = 1
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(ChainError(None, line_no, f"unparseable: {exc}"))
                return errors

            seq = rec.get("seq")
            if seq != expected_seq:
                errors.append(ChainError(seq, line_no,
                              f"sequence break: expected {expected_seq}, got {seq}"))
            if rec.get("prev_hash") != prev_hash:
                errors.append(ChainError(seq, line_no,
                              "prev_hash does not match the preceding record"))
            recomputed = compute_hash(prev_hash, rec)
            if recomputed != rec.get(_HASH_FIELD):
                errors.append(ChainError(seq, line_no,
                              "hash mismatch: record content has been altered"))

            prev_hash = rec.get(_HASH_FIELD, prev_hash)
            expected_seq = (seq or expected_seq) + 1
    return errors


def head_of(path: str | Path) -> str | None:
    """Head hash without loading the whole ledger."""
    path = Path(path)
    if not path.exists():
        return None
    last = None
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                last = line
    return json.loads(last)[_HASH_FIELD] if last else None
