"""Append-only, hash-linked, ML-DSA-signed security evidence chain (Phase 8, design TD-09).

Each entry:
    event_hash = SHA-256( prev_hash_bytes || canonical_json(body) )
    signature  = ML-DSA-65( event_hash, context = b"qshield/evidence/v1" )   by the gateway evidence key
where `body` is every field except event_hash and signature. The first entry links to 64 zero hex digits.

Verification walks the chain from seq 1: recomputes every hash, checks prev_hash links, sequence continuity and the
signature. A modified, reordered or removed-from-the-middle entry fails at that entry.

Limitations (TD-09, unchanged): an attacker holding BOTH write access to the DB and the evidence signing key can
rewrite history. Truncating the tail is only detectable against an externally held copy of the head
(`head()`); no external anchoring is implemented. Timestamps are the gateway clock, not trusted time.
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import dataclass, field

from backend.devices.store import Store

CONTEXT = b"qshield/evidence/v1"
GENESIS = "0" * 64
SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence_chain (
    seq         INTEGER PRIMARY KEY,
    event_id    TEXT NOT NULL UNIQUE,
    ts          REAL NOT NULL,
    device_id   TEXT,
    event_type  TEXT NOT NULL,
    source      TEXT NOT NULL,
    trust_state TEXT,
    trust_score INTEGER,
    payload     TEXT NOT NULL,
    prev_hash   TEXT NOT NULL,
    event_hash  TEXT NOT NULL,
    signature   TEXT NOT NULL,
    key_id      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_dev ON evidence_chain(device_id, seq);
"""
BODY_FIELDS = ("seq", "event_id", "ts", "device_id", "event_type", "source", "trust_state", "trust_score", "payload",
               "prev_hash", "key_id")


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_hash(prev_hash: str, body: dict) -> str:
    return hashlib.sha256(bytes.fromhex(prev_hash) + canonical(body)).hexdigest()


@dataclass
class EvidenceSigner:
    """ML-DSA signer for the chain. `backend` is a backend.security.pqc.PqcBackend."""
    backend: object
    secret_key: bytes
    public_key: bytes
    key_id: str

    def sign(self, digest_hex: str) -> str:
        return self.backend.sign(self.secret_key, bytes.fromhex(digest_hex), CONTEXT).hex()

    def verify(self, digest_hex: str, sig_hex: str) -> bool:
        try:
            sig = bytes.fromhex(sig_hex)
        except ValueError:
            return False
        return self.backend.verify(self.public_key, bytes.fromhex(digest_hex), sig, CONTEXT)


@dataclass
class VerifyReport:
    ok: bool
    count: int
    signed: bool
    first_bad_seq: int | None = None
    reason: str | None = None
    head_hash: str = GENESIS
    problems: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "count": self.count, "signed": self.signed, "first_bad_seq": self.first_bad_seq,
                "reason": self.reason, "head_hash": self.head_hash, "problems": self.problems[:20]}


class EvidenceChain:
    def __init__(self, store: Store, signer: EvidenceSigner | None = None):
        """`signer=None` produces a hash-linked but UNSIGNED chain (reported as such by verify); the gateway builds a
        signed chain whenever PQC keys are provisioned."""
        self.store, self.signer = store, signer
        self._lock = threading.Lock()
        store.ensure_schema(SCHEMA)

    # ------------------------------------------------------------------ write
    def head(self) -> dict:
        rows = self.store.query("SELECT seq, event_hash FROM evidence_chain ORDER BY seq DESC LIMIT 1")
        return {"seq": rows[0]["seq"], "event_hash": rows[0]["event_hash"]} if rows else {"seq": 0, "event_hash": GENESIS}

    def append_event(self, event_type: str, payload: dict, *, ts: float, device_id: str | None = None,
                     source: str = "gateway", trust_state: str | None = None, trust_score: int | None = None,
                     event_id: str | None = None) -> dict:
        with self._lock:
            h = self.head()
            body = {
                "seq": h["seq"] + 1, "event_id": event_id or f"EV-{uuid.uuid4()}", "ts": float(ts), "device_id": device_id,
                "event_type": event_type, "source": source, "trust_state": trust_state,
                "trust_score": trust_score, "payload": canonical(payload).decode("utf-8"), "prev_hash": h["event_hash"],
                "key_id": self.signer.key_id if self.signer else "unsigned",
            }
            event_hash = compute_hash(h["event_hash"], body)
            signature = self.signer.sign(event_hash) if self.signer else ""
            self.store.execute(
                "INSERT INTO evidence_chain(seq, event_id, ts, device_id, event_type, source, trust_state, trust_score, payload,"
                " prev_hash, event_hash, signature, key_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (body["seq"], body["event_id"], body["ts"], device_id, event_type, source, trust_state, trust_score,
                 body["payload"], body["prev_hash"], event_hash, signature, body["key_id"]))
            return {**body, "event_hash": event_hash, "signature": signature}

    # ------------------------------------------------------------------ read
    @staticmethod
    def _entry(r) -> dict:
        return {k: r[k] for k in BODY_FIELDS} | {"event_hash": r["event_hash"], "signature": r["signature"]}

    def get_events(self, limit: int = 100, after_seq: int = 0) -> list[dict]:
        rows = self.store.query("SELECT * FROM evidence_chain WHERE seq>? ORDER BY seq LIMIT ?", (after_seq, limit))
        return [self._entry(r) for r in rows]

    def get_device_timeline(self, device_id: str, limit: int = 200) -> list[dict]:
        rows = self.store.query("SELECT * FROM evidence_chain WHERE device_id=? ORDER BY seq LIMIT ?", (device_id, limit))
        return [self._entry(r) for r in rows]

    def get_event(self, event_id: str) -> dict | None:
        rows = self.store.query("SELECT * FROM evidence_chain WHERE event_id=?", (event_id,))
        return self._entry(rows[0]) if rows else None

    # ------------------------------------------------------------------ verify
    def verify_event(self, entry: dict, expected_prev: str | None = None) -> str | None:
        """Returns None if the single entry is internally consistent, else a reason code."""
        body = {k: entry[k] for k in BODY_FIELDS}
        if expected_prev is not None and entry["prev_hash"] != expected_prev:
            return "broken_link"
        try:
            if compute_hash(entry["prev_hash"], body) != entry["event_hash"]:
                return "hash_mismatch"
        except ValueError:
            return "malformed_hash"
        if self.signer is not None:
            if entry["key_id"] != self.signer.key_id:
                return "unknown_key"
            if not self.signer.verify(entry["event_hash"], entry["signature"]):
                return "invalid_signature"
        return None

    def verify_chain(self, entries: list[dict] | None = None) -> VerifyReport:
        """Verify the stored chain (or a supplied list of entries, e.g. an exported copy)."""
        if entries is None:
            entries = [self._entry(r) for r in self.store.query("SELECT * FROM evidence_chain ORDER BY seq")]
        rep = VerifyReport(ok=True, count=len(entries), signed=self.signer is not None)
        prev = GENESIS
        for i, e in enumerate(entries, start=1):
            reason = "sequence_gap" if e["seq"] != i else self.verify_event(e, expected_prev=prev)
            if reason:
                rep.problems.append({"seq": e["seq"], "event_id": e["event_id"], "reason": reason})
                if rep.ok:
                    rep.ok, rep.first_bad_seq, rep.reason = False, e["seq"], reason
            prev = e["event_hash"]
        rep.head_hash = prev
        return rep


class EvidenceRecorder:
    """Glue that turns trust changes and control-plane actions into evidence entries."""

    def __init__(self, chain: EvidenceChain):
        self.chain = chain

    def on_trust_change(self, c) -> None:
        d = c.to_dict()
        etype = ("trust_state_transition" if d["previous_state"] != d["new_state"] else
                 "trust_incident" if d.get("incident") else "trust_score_change")
        payload = {"trust_event_id": d["event_id"], "previous_score": d["previous_score"], "new_score": d["new_score"],
                   "previous_state": d["previous_state"], "new_state": d["new_state"],
                   "trigger_signals": d["trigger_signals"], "caps_active": d["caps_active"], "incident": d.get("incident"),
                   "reasons": [{k: r.get(k) for k in ("signal", "impact", "factor", "source_ref")} for r in d["reasons"][:6]]}
        self.chain.append_event(etype, payload, ts=d["timestamp"], device_id=d["device_id"], source="trust_engine",
                                trust_state=d["new_state"], trust_score=d["new_score"], event_id=f"EV-{d['event_id']}")

    def record(self, event_type: str, payload: dict, *, ts: float, device_id: str | None, source: str,
               trust_state: str | None = None, trust_score: int | None = None) -> dict:
        return self.chain.append_event(event_type, payload, ts=ts, device_id=device_id, source=source,
                                       trust_state=trust_state, trust_score=trust_score)
