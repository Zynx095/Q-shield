"""ML-KEM-768 session establishment + AES-256-GCM protected messages."""
import base64
import json
import os
from datetime import timedelta

import pytest

from backend.protocol.signed_observation import iso_utc
from backend.security.pqc_gateway import PqcRejection
from backend.security.session import (
    HandshakeInit, INIT_CONTEXT, SessionError, client_initiate, init_signing_bytes,
)
from tests.pqc_helpers import make_obs, now_dt, signed_env

b64e = lambda b: base64.b64encode(b).decode()  # noqa: E731
b64d = base64.b64decode


def initiate(world, clock, signer="vision-1", gw_pk=None):
    return client_initiate(world.backend, "gateway-kem-1", gw_pk or world.kem_rec.public_key, signer,
                           world.signers[signer], now_dt(clock), clock)


def establish(world, clock, signer="vision-1"):
    init, pending = initiate(world, clock, signer)
    resp = world.gateway.establish_session(HandshakeInit(**init))
    return pending.finish(resp), resp


# ---------------- valid session ----------------

def test_valid_session_shared_secret_matches_both_directions(pqc_world, clock):
    client_ch, resp = establish(pqc_world, clock)
    server_ch = pqc_world.gateway._sessions[resp.session_id].channel
    # A message sealed by one side opens on the other only if both derived the same keys, i.e. the
    # ML-KEM shared secrets matched (and the key confirmation already verified this in finish()).
    c, ct = client_ch.seal(b"observation bytes")
    assert server_ch.open(c, ct) == b"observation bytes"
    c, ct = server_ch.seal(b"ack")
    assert client_ch.open(c, ct) == b"ack"


def test_sessions_are_independent(pqc_world, clock):
    a, ra = establish(pqc_world, clock)
    b, rb = establish(pqc_world, clock)
    assert ra.session_id != rb.session_id
    c, ct = a.seal(b"x")
    with pytest.raises(SessionError):
        pqc_world.gateway._sessions[rb.session_id].channel.open(c, ct)   # other session's key


# ---------------- tampering / wrong keys ----------------

@pytest.mark.parametrize("pos", [0, 500, 1087])
def test_tampered_ciphertext_in_flight_rejected_before_decapsulation(pqc_world, clock, pos):
    init, _ = initiate(pqc_world, clock)
    ct = bytearray(b64d(init["ciphertext"]))
    ct[pos] ^= 1
    init["ciphertext"] = b64e(bytes(ct))
    with pytest.raises(PqcRejection) as e:
        pqc_world.gateway.establish_session(HandshakeInit(**init))
    assert e.value.reason == "handshake_invalid_signature"


def test_corrupted_ciphertext_signed_by_client_fails_key_confirmation(pqc_world, clock, pqc_backend):
    """Even if a (buggy) client signs a corrupted ciphertext, ML-KEM implicit rejection makes the
    gateway derive an unrelated secret, and the client detects it via the confirmation tag."""
    init, pending = initiate(pqc_world, clock)
    ct = bytearray(b64d(init["ciphertext"]))
    ct[7] ^= 1
    init["ciphertext"] = b64e(bytes(ct))
    init["signature"] = b64e(pqc_backend.sign(pqc_world.signers["vision-1"], init_signing_bytes(init), INIT_CONTEXT))
    resp = pqc_world.gateway.establish_session(HandshakeInit(**init))   # server cannot tell
    with pytest.raises(SessionError) as e:
        pending.finish(resp)
    assert e.value.reason == "key_confirmation_failed"


def test_wrong_gateway_key_rejected_by_client(pqc_world, clock, pqc_backend):
    impostor = pqc_backend.kem_keygen()                      # client pinned/encapsulated to the wrong key
    init, pending = initiate(pqc_world, clock, gw_pk=impostor.public_key)
    resp = pqc_world.gateway.establish_session(HandshakeInit(**init))
    with pytest.raises(SessionError) as e:
        pending.finish(resp)
    assert e.value.reason == "key_confirmation_failed"


def test_tampered_server_response_rejected(pqc_world, clock):
    init, pending = initiate(pqc_world, clock)
    resp = pqc_world.gateway.establish_session(HandshakeInit(**init)).model_dump()
    for field in ("confirm", "server_nonce", "session_id"):
        bad = dict(resp)
        raw = bytearray(b64d(bad[field]))
        raw[0] ^= 1
        bad[field] = b64e(bytes(raw))
        with pytest.raises(SessionError):
            pending.finish(bad)


# ---------------- handshake authentication ----------------

def test_unknown_signer_rejected(pqc_world, clock, pqc_backend):
    rogue = pqc_backend.sig_keygen()
    init, _ = client_initiate(pqc_backend, "gateway-kem-1", pqc_world.kem_rec.public_key, "rogue-1",
                              rogue.secret_key, now_dt(clock))
    with pytest.raises(PqcRejection) as e:
        pqc_world.gateway.establish_session(HandshakeInit(**init))
    assert e.value.reason == "unknown_signer"


def test_signer_identity_cannot_be_changed(pqc_world, clock):
    init, _ = initiate(pqc_world, clock, "vision-1")
    init["signer_id"] = "vision-2"
    with pytest.raises(PqcRejection) as e:
        pqc_world.gateway.establish_session(HandshakeInit(**init))
    assert e.value.reason == "handshake_invalid_signature"


def test_handshake_replay_rejected(pqc_world, clock):
    init, _ = initiate(pqc_world, clock)
    pqc_world.gateway.establish_session(HandshakeInit(**init))
    with pytest.raises(PqcRejection) as e:
        pqc_world.gateway.establish_session(HandshakeInit(**init))
    assert e.value.reason == "handshake_replay"


def test_concurrent_replay_of_one_handshake_yields_one_session(pqc_world, clock, monkeypatch):
    """Regression: the nonce check and the nonce record were in two separate critical sections around the (slow)
    signature verification and decapsulation, so two copies of one init racing through the gateway both got a
    session. The nonce is now reserved atomically with the check."""
    import threading
    import backend.security.pqc_gateway as gw_mod

    init, _ = initiate(pqc_world, clock)
    gate = threading.Barrier(2, timeout=5)
    real = gw_mod.server_accept

    def slow_accept(*a, **kw):                      # both requests are inside the crypto at the same time
        try:
            gate.wait()
        except threading.BrokenBarrierError:
            pass
        return real(*a, **kw)

    monkeypatch.setattr(gw_mod, "server_accept", slow_accept)
    results = []

    def go():
        try:
            results.append(pqc_world.gateway.establish_session(HandshakeInit(**init)).session_id)
        except PqcRejection as e:
            results.append(e.reason)

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert sorted(r == "handshake_replay" for r in results) == [False, True], results
    assert len(pqc_world.gateway._sessions) == 1


def test_failed_handshake_does_not_keep_its_nonce(pqc_world, clock):
    """A rejected handshake (bad signature) must not leave its nonce behind: memory stays bounded by real sessions."""
    init, _ = initiate(pqc_world, clock)
    bad = {**init, "signature": b64e(bytes(3309))}
    with pytest.raises(PqcRejection):
        pqc_world.gateway.establish_session(HandshakeInit(**bad))
    assert init["client_nonce"] not in pqc_world.gateway._seen_nonces
    pqc_world.gateway.establish_session(HandshakeInit(**init))        # the genuine init still works once
    with pytest.raises(PqcRejection) as e:
        pqc_world.gateway.establish_session(HandshakeInit(**init))
    assert e.value.reason == "handshake_replay"


def test_stale_and_future_handshake_rejected(pqc_world, clock, pqc_backend):
    for delta in (-400, 400):
        init, _ = client_initiate(pqc_backend, "gateway-kem-1", pqc_world.kem_rec.public_key, "vision-1",
                                  pqc_world.signers["vision-1"], now_dt(clock) + timedelta(seconds=delta))
        with pytest.raises(PqcRejection) as e:
            pqc_world.gateway.establish_session(HandshakeInit(**init))
        assert e.value.reason == "handshake_stale_or_future_handshake"


def test_unknown_gateway_key_id_and_algorithm_mismatch(pqc_world, clock):
    init, _ = initiate(pqc_world, clock)
    with pytest.raises(PqcRejection):
        pqc_world.gateway.establish_session(HandshakeInit(**{**init, "gateway_key_id": "gateway-kem-9"}))
    with pytest.raises(PqcRejection):
        pqc_world.gateway.establish_session(HandshakeInit(**{**init, "kem_algorithm": "ML-KEM-512"}))


def test_malformed_handshake_fields(pqc_world, clock, pqc_backend):
    init, _ = initiate(pqc_world, clock)
    for field, val in (("client_nonce", b64e(b"short")), ("ciphertext", b64e(b"\x00" * 100)),
                       ("ciphertext", "!!!"), ("signature", "!!!")):
        bad = {**init, field: val}
        if field == "ciphertext" and val != "!!!":   # re-sign so the failure is in decapsulation, not the signature
            bad["signature"] = b64e(pqc_backend.sign(pqc_world.signers["vision-1"], init_signing_bytes(bad), INIT_CONTEXT))
        with pytest.raises((PqcRejection, SessionError)):
            pqc_world.gateway.establish_session(HandshakeInit(**bad))


def test_session_cap(pqc_world, clock):
    pqc_world.gateway.max_sessions = 2
    establish(pqc_world, clock)
    establish(pqc_world, clock)
    init, _ = initiate(pqc_world, clock)
    with pytest.raises(PqcRejection) as e:
        pqc_world.gateway.establish_session(HandshakeInit(**init))
    assert e.value.reason == "too_many_sessions"


# ---------------- protected messages ----------------

def test_tampered_message_ciphertext_rejected_and_does_not_advance_counter(pqc_world, clock):
    client_ch, resp = establish(pqc_world, clock)
    server_ch = pqc_world.gateway._sessions[resp.session_id].channel
    c, ct = client_ch.seal(b"hello")
    bad = bytearray(ct)
    bad[0] ^= 1
    with pytest.raises(SessionError) as e:
        server_ch.open(c, bytes(bad))
    assert e.value.reason == "decryption_failed"
    assert server_ch.open(c, ct) == b"hello"          # genuine message still accepted afterwards


def test_replayed_and_reordered_messages_rejected(pqc_world, clock):
    client_ch, resp = establish(pqc_world, clock)
    server_ch = pqc_world.gateway._sessions[resp.session_id].channel
    m1, m2 = client_ch.seal(b"one"), client_ch.seal(b"two")
    assert server_ch.open(*m2) == b"two"
    for m in (m1, m2):
        with pytest.raises(SessionError) as e:
            server_ch.open(*m)
        assert e.value.reason == "replayed_or_reordered_message"


def test_counter_or_direction_tampering_rejected(pqc_world, clock):
    client_ch, resp = establish(pqc_world, clock)
    server_ch = pqc_world.gateway._sessions[resp.session_id].channel
    c, ct = client_ch.seal(b"x")
    with pytest.raises(SessionError):
        server_ch.open(c + 1, ct)                      # counter is in the nonce and AAD
    with pytest.raises(SessionError):
        client_ch.open(c, ct)                          # a client's own message cannot be reflected back to it


def test_expired_session_rejected(pqc_world, clock):
    client_ch, resp = establish(pqc_world, clock)
    server_ch = pqc_world.gateway._sessions[resp.session_id].channel
    c, ct = client_ch.seal(b"x")
    clock.advance(3601)
    with pytest.raises(SessionError) as e:
        server_ch.open(c, ct)
    assert e.value.reason == "session_expired"


# ---------------- over HTTP: signed observation inside the session ----------------

def http_session(client, world, clock, signer="vision-1"):
    init, pending = initiate(world, clock, signer)
    r = client.post("/api/v1/pqc/session", json=init)
    assert r.status_code == 200, r.text
    return pending.finish(r.json()), r.json()["session_id"]


def send(client, ch, sid, env: dict):
    c, ct = ch.seal(json.dumps(env).encode())
    return client.post("/api/v1/observations/secure", json={"session_id": sid, "counter": c, "ciphertext": b64e(ct)}), c, ct


def test_secure_endpoint_accepts_signed_observation_in_session(pqc_client, pqc_operator, pqc_world, clock):
    ch, sid = http_session(pqc_client, pqc_world, clock)
    r, _, ct = send(pqc_client, ch, sid, signed_env(pqc_world, clock))
    assert r.status_code == 200
    assert b"person" not in ct and b"restricted_zone" not in ct        # payload is not visible on the wire
    o = pqc_operator.get("/api/v1/observations").json()[0]
    assert o["auth"] == "ML-DSA-65:vision-1" and o["transport"] == "secure"   # arrived inside the ML-KEM session


def test_secure_endpoint_rejects_tampered_ciphertext(pqc_client, pqc_operator, pqc_world, clock):
    ch, sid = http_session(pqc_client, pqc_world, clock)
    c, ct = ch.seal(json.dumps(signed_env(pqc_world, clock)).encode())
    bad = bytearray(ct)
    bad[5] ^= 1
    r = pqc_client.post("/api/v1/observations/secure", json={"session_id": sid, "counter": c, "ciphertext": b64e(bytes(bad))})
    assert r.status_code == 401
    assert "pqc_session_decryption_failed" in [e["event_type"] for e in pqc_operator.get("/api/v1/events").json()]
    assert pqc_operator.get("/api/v1/observations").json() == []


def test_secure_endpoint_rejects_replayed_message(pqc_client, pqc_world, clock):
    ch, sid = http_session(pqc_client, pqc_world, clock)
    r, c, ct = send(pqc_client, ch, sid, signed_env(pqc_world, clock))
    assert r.status_code == 200
    again = pqc_client.post("/api/v1/observations/secure", json={"session_id": sid, "counter": c, "ciphertext": b64e(ct)})
    assert again.status_code == 401


def test_secure_endpoint_unknown_session_and_bad_base64(pqc_client, pqc_world, clock):
    ch, sid = http_session(pqc_client, pqc_world, clock)
    c, ct = ch.seal(b"{}")
    assert pqc_client.post("/api/v1/observations/secure", json={"session_id": b64e(os.urandom(16)), "counter": c,
                                                                "ciphertext": b64e(ct)}).status_code == 401
    assert pqc_client.post("/api/v1/observations/secure", json={"session_id": sid, "counter": c,
                                                                "ciphertext": "***"}).status_code == 422


def test_only_a_gone_session_asks_the_client_to_handshake_again(pqc_client, pqc_world, clock):
    """401 'session_expired' for an unknown or expired session; every other rejection stays 'authentication_failed',
    so a client re-handshakes only when that can help (no session churn on rejected observations)."""
    ch, sid = http_session(pqc_client, pqc_world, clock)
    c, ct = ch.seal(b"{}")
    r = pqc_client.post("/api/v1/observations/secure", json={"session_id": b64e(os.urandom(16)), "counter": c, "ciphertext": b64e(ct)})
    assert (r.status_code, r.json()["detail"]) == (401, "session_expired")
    bad = bytearray(ct)
    bad[-1] ^= 1
    r = pqc_client.post("/api/v1/observations/secure", json={"session_id": sid, "counter": c, "ciphertext": b64e(bytes(bad))})
    assert (r.status_code, r.json()["detail"]) == (401, "authentication_failed")       # tampering is not "expired"
    clock.advance(3601)
    c2, ct2 = ch.seal(b"{}")
    r = pqc_client.post("/api/v1/observations/secure", json={"session_id": sid, "counter": c2, "ciphertext": b64e(ct2)})
    assert (r.status_code, r.json()["detail"]) == (401, "session_expired")


def test_inner_signature_still_required_inside_session(pqc_client, pqc_operator, pqc_world, clock):
    ch, sid = http_session(pqc_client, pqc_world, clock)
    env = signed_env(pqc_world, clock)
    p = json.loads(env["payload"])
    p["confidence"] = 0.01
    env["payload"] = json.dumps(p, sort_keys=True)                      # encrypted channel does not excuse a bad signature
    r, _, _ = send(pqc_client, ch, sid, env)
    assert r.status_code == 401 and pqc_operator.get("/api/v1/observations").json() == []


def test_session_signer_must_match_inner_signer(pqc_client, pqc_operator, pqc_world, clock):
    ch, sid = http_session(pqc_client, pqc_world, clock, signer="vision-1")
    r, _, _ = send(pqc_client, ch, sid, signed_env(pqc_world, clock, signer="vision-2"))   # valid signature, other identity
    assert r.status_code == 401
    assert "pqc_signer_session_mismatch" in [e["event_type"] for e in pqc_operator.get("/api/v1/events").json()]


def test_secure_endpoint_accepts_signed_replay_only_once(pqc_client, pqc_world, clock):
    ch, sid = http_session(pqc_client, pqc_world, clock)
    env = signed_env(pqc_world, clock)
    assert send(pqc_client, ch, sid, env)[0].status_code == 200
    assert send(pqc_client, ch, sid, env)[0].status_code == 409       # fresh transport message, same observation
