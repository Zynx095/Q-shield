"""Phase 8: the evidence chain is append-only, hash-linked, ML-DSA-signed and tamper-evident."""
import json

import pytest

from backend.evidence.chain import GENESIS, EvidenceChain, EvidenceSigner, compute_hash


@pytest.fixture(scope="module")
def keys(pqc_backend):
    return pqc_backend.sig_keygen(), pqc_backend.sig_keygen()


@pytest.fixture
def chain(store, pqc_backend, keys):
    k, _ = keys
    return EvidenceChain(store, EvidenceSigner(pqc_backend, k.secret_key, k.public_key, "ev-1"))


def fill(chain, n=5):
    return [chain.append_event("test_event", {"i": i}, ts=1000.0 + i, device_id="D1" if i % 2 else "D2",
                               trust_state="TRUSTED", trust_score=100 - i) for i in range(n)]


def raw(chain):
    return chain.get_events(1000)


def test_empty_and_normal_chain(chain):
    v = chain.verify_chain()
    assert v.ok and v.count == 0 and v.head_hash == GENESIS
    es = fill(chain, 5)
    v = chain.verify_chain()
    assert v.ok and v.count == 5 and v.signed and v.head_hash == es[-1]["event_hash"]
    assert es[0]["prev_hash"] == GENESIS and es[1]["prev_hash"] == es[0]["event_hash"]
    assert chain.head() == {"seq": 5, "event_hash": es[-1]["event_hash"]}


def test_hash_is_recomputable(chain):
    e = fill(chain, 1)[0]
    body = {k: e[k] for k in ("seq", "event_id", "ts", "device_id", "event_type", "source", "trust_state", "trust_score",
                              "payload", "prev_hash", "key_id")}
    assert compute_hash(GENESIS, body) == e["event_hash"]


def test_device_timeline_and_lookup(chain):
    es = fill(chain, 6)
    tl = chain.get_device_timeline("D1")
    assert [e["seq"] for e in tl] == [2, 4, 6]
    assert chain.get_event(es[2]["event_id"])["seq"] == 3 and chain.get_event("nope") is None


def test_tampered_payload_detected(chain, store):
    fill(chain, 5)
    store.execute("UPDATE evidence_chain SET payload=? WHERE seq=3", (json.dumps({"i": 99}),))
    v = chain.verify_chain()
    assert not v.ok and v.first_bad_seq == 3 and v.reason == "hash_mismatch"


def test_tampered_metadata_detected(chain, store):
    fill(chain, 3)
    store.execute("UPDATE evidence_chain SET trust_score=100 WHERE seq=2")
    assert chain.verify_chain().reason == "hash_mismatch"


def test_deleted_event_detected(chain, store):
    fill(chain, 5)
    store.execute("DELETE FROM evidence_chain WHERE seq=3")
    v = chain.verify_chain()
    assert not v.ok and v.first_bad_seq in (4,) and v.reason in ("sequence_gap", "broken_link")


def test_reordered_events_detected(chain):
    fill(chain, 4)
    es = raw(chain)
    es[1], es[2] = es[2], es[1]
    v = chain.verify_chain(es)
    assert not v.ok and v.first_bad_seq == 3


def test_modified_prev_hash_detected(chain, store):
    fill(chain, 4)
    store.execute("UPDATE evidence_chain SET prev_hash=? WHERE seq=3", ("ab" * 32,))
    v = chain.verify_chain()
    assert not v.ok and v.first_bad_seq == 3 and v.reason == "broken_link"


def test_recomputed_hash_without_key_fails_signature(chain, store):
    """An attacker with DB access but not the signing key re-hashes a modified entry: the signature exposes it."""
    fill(chain, 1)
    e = raw(chain)[0]
    e["payload"] = json.dumps({"i": 42})
    body = {k: e[k] for k in ("seq", "event_id", "ts", "device_id", "event_type", "source", "trust_state", "trust_score",
                              "payload", "prev_hash", "key_id")}
    new_hash = compute_hash(e["prev_hash"], body)
    store.execute("UPDATE evidence_chain SET payload=?, event_hash=? WHERE seq=1", (e["payload"], new_hash))
    v = chain.verify_chain()
    assert not v.ok and v.reason == "invalid_signature"


def test_signature_from_another_key_rejected(store, pqc_backend, keys):
    k1, k2 = keys
    writer = EvidenceChain(store, EvidenceSigner(pqc_backend, k2.secret_key, k2.public_key, "ev-1"))
    fill(writer, 2)
    verifier = EvidenceChain(store, EvidenceSigner(pqc_backend, k1.secret_key, k1.public_key, "ev-1"))
    assert verifier.verify_chain().reason == "invalid_signature"


def test_garbage_signature_rejected(chain, store):
    fill(chain, 2)
    store.execute("UPDATE evidence_chain SET signature='zz' WHERE seq=2")
    assert chain.verify_chain().reason == "invalid_signature"


def test_unsigned_chain_is_reported_as_unsigned(store):
    c = EvidenceChain(store, None)
    fill(c, 3)
    v = c.verify_chain()
    assert v.ok and not v.signed


def test_verify_event_single(chain):
    e = fill(chain, 1)[0]
    assert chain.verify_event(e) is None
    e2 = dict(e, trust_score=1)
    assert chain.verify_event(e2) == "hash_mismatch"


def test_append_only_head_advances(chain):
    fill(chain, 2)
    h = chain.head()
    chain.append_event("x", {}, ts=5.0)
    assert chain.head()["seq"] == h["seq"] + 1


class _CountingSigner(EvidenceSigner):
    calls = 0

    def verify(self, digest_hex, sig_hex):
        type(self).calls += 1
        return super().verify(digest_hex, sig_hex)


def test_repeat_verification_skips_unchanged_signatures_but_still_catches_tampering(store, pqc_backend, keys):
    """The dashboard re-verifies the chain often. A signature already verified for an unchanged (event_hash,
    signature, key) is not re-verified; every hash is still recomputed, so any edit is still found."""
    k, _ = keys
    _CountingSigner.calls = 0
    chain = EvidenceChain(store, _CountingSigner(pqc_backend, k.secret_key, k.public_key, "ev-1"))
    es = fill(chain, 5)
    assert chain.verify_chain().ok and _CountingSigner.calls == 5
    assert chain.verify_chain().ok and _CountingSigner.calls == 5            # nothing changed: no ML-DSA work
    fill(chain, 1)
    assert chain.verify_chain().ok and _CountingSigner.calls == 6            # only the new entry is verified

    store.execute("UPDATE evidence_chain SET payload=? WHERE seq=2", (json.dumps({"i": 99}),))
    v = chain.verify_chain()
    assert not v.ok and v.first_bad_seq == 2 and v.reason == "hash_mismatch"
    store.execute("UPDATE evidence_chain SET payload=? WHERE seq=2", (es[1]["payload"],))
    assert chain.verify_chain().ok

    # rewrite entry 4 consistently (new payload, recomputed hash) but keep its old signature: the cache key changes,
    # so the signature is checked again and fails
    e4 = es[3]
    body = {k2: e4[k2] for k2 in ("seq", "event_id", "ts", "device_id", "event_type", "source", "trust_state",
                                  "trust_score", "payload", "prev_hash", "key_id")} | {"payload": json.dumps({"i": 7})}
    store.execute("UPDATE evidence_chain SET payload=?, event_hash=? WHERE seq=4", (body["payload"], compute_hash(e4["prev_hash"], body)))
    v = chain.verify_chain()
    assert not v.ok and v.first_bad_seq == 4 and v.reason == "invalid_signature"

    store.execute("UPDATE evidence_chain SET payload=?, event_hash=? WHERE seq=4", (e4["payload"], e4["event_hash"]))
    assert chain.verify_chain().ok
    store.execute("UPDATE evidence_chain SET signature=? WHERE seq=5", (es[0]["signature"],))   # a real but wrong signature
    v = chain.verify_chain()
    assert not v.ok and v.first_bad_seq == 5 and v.reason == "invalid_signature"
