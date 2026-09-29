"""ML-DSA-65 signed observations: acceptance and rejection at the gateway API."""
import base64
import json
import uuid

import pytest

from backend.protocol.canonical import encode_fields
from backend.protocol.signed_observation import (
    SignedObservationEnvelope, iso_utc, signing_bytes,
)
from tests.pqc_helpers import make_obs, now_dt, raw_body, sign_body, signed_env

URL = "/api/v1/observations/signed"


def events(op):
    return [e["event_type"] for e in op.get("/api/v1/events").json()]


def stored(op):
    return op.get("/api/v1/observations").json()


# ---------------- accepted ----------------

def test_valid_signed_observation_accepted_without_any_token(pqc_client, pqc_operator, pqc_world, clock):
    r = pqc_client.post(URL, json=signed_env(pqc_world, clock))
    assert r.status_code == 200 and r.json()["auth"] == "ML-DSA-65:vision-1"
    (o,) = stored(pqc_operator)
    assert o["object"] == "person" and o["auth"] == "ML-DSA-65:vision-1"


def test_stored_envelope_is_independently_verifiable(pqc_client, store, pqc_world, clock, pqc_backend):
    env = signed_env(pqc_world, clock)
    pqc_client.post(URL, json=env)
    saved = SignedObservationEnvelope.model_validate_json(store.get_observation_envelope(env["observation_id"]))
    pk = store.get_signer("vision-1").public_key
    from backend.protocol.signed_observation import CONTEXT
    assert pqc_backend.verify(pk, signing_bytes(saved), base64.b64decode(saved.signature), CONTEXT)


def test_unsigned_ingest_path_labelled_token_only(ingest_client, pqc_operator, pqc_world, clock, pqc_app):
    from fastapi.testclient import TestClient
    from tests.conftest import INGEST_TOKEN
    c = TestClient(pqc_app, headers={"Authorization": f"Bearer {INGEST_TOKEN}"})
    body = make_obs(clock).to_wire()
    assert c.post("/api/v1/observations", json=body).status_code == 200
    assert stored(pqc_operator)[0]["auth"] == "ingest-token"   # never presented as PQC-authenticated


# ---------------- modification ----------------

def test_modified_payload_rejected(pqc_client, pqc_operator, pqc_world, clock):
    env = signed_env(pqc_world, clock)
    p = json.loads(env["payload"])
    p["anomaly"], p["anomaly_reason"] = False, None      # attacker hides the anomaly
    env["payload"] = json.dumps(p, sort_keys=True)
    assert pqc_client.post(URL, json=env).status_code == 401
    assert "pqc_invalid_signature" in events(pqc_operator) and stored(pqc_operator) == []


@pytest.mark.parametrize("field,value", [
    ("source_id", "usb_webcam:1"), ("observation_id", str(uuid.uuid4())), ("timestamp", "2023-11-14T22:13:21.000000Z"),
    ("algorithm", "ML-DSA-87"), ("protocol_version", 2), ("signer_id", "vision-2"),
])
def test_modified_metadata_rejected(pqc_client, pqc_operator, pqc_world, clock, field, value):
    env = signed_env(pqc_world, clock)
    env[field] = value
    assert pqc_client.post(URL, json=env).status_code == 401
    assert stored(pqc_operator) == []


def test_modified_signature_rejected(pqc_client, pqc_world, clock):
    env = signed_env(pqc_world, clock)
    sig = bytearray(base64.b64decode(env["signature"]))
    sig[10] ^= 1
    assert pqc_client.post(URL, json={**env, "signature": base64.b64encode(bytes(sig)).decode()}).status_code == 401


@pytest.mark.parametrize("mutate", [
    lambda s: base64.b64encode(base64.b64decode(s)[:-1]).decode(),   # truncated
    lambda s: base64.b64encode(base64.b64decode(s) + b"\x00").decode(),  # extended
    lambda s: "",                                                    # empty
    lambda s: "***not base64***",
    lambda s: base64.b64encode(b"\x00" * 3309).decode(),             # right size, all zero
])
def test_malformed_signature_rejected(pqc_client, pqc_world, clock, mutate):
    env = signed_env(pqc_world, clock)
    assert pqc_client.post(URL, json={**env, "signature": mutate(env["signature"])}).status_code == 401


def test_signature_from_other_enrolled_signer_rejected(pqc_client, pqc_world, clock):
    env = signed_env(pqc_world, clock, signer="vision-2")
    env["signer_id"] = "vision-1"      # claims to be vision-1, signed by vision-2's key
    assert pqc_client.post(URL, json=env).status_code == 401


def test_wrong_signing_context_rejected(pqc_client, pqc_world, clock):
    env = sign_body(pqc_world, "vision-1", raw_body(clock), context=b"some-other-protocol")
    assert pqc_client.post(URL, json=env).status_code == 401


# ---------------- identity ----------------

def test_unknown_signer_rejected(pqc_client, pqc_operator, pqc_world, clock, pqc_backend):
    rogue = pqc_backend.sig_keygen()                       # valid ML-DSA key, never enrolled
    body = raw_body(clock, signer="rogue-1")
    sig = pqc_backend.sign(rogue.secret_key, signing_bytes(body), b"qshield/signed-observation/v1")
    env = {**body, "signature": base64.b64encode(sig).decode()}
    assert pqc_client.post(URL, json=env).status_code == 401
    assert "pqc_unknown_signer" in events(pqc_operator)


@pytest.mark.parametrize("status,reason", [("retired", "pqc_signer_retired"), ("revoked", "pqc_signer_revoked")])
def test_retired_or_revoked_signer_rejected(pqc_client, pqc_operator, store, pqc_world, clock, status, reason):
    env = signed_env(pqc_world, clock)
    store.set_signer_status("vision-1", status, clock())
    assert pqc_client.post(URL, json=env).status_code == 401
    assert reason in events(pqc_operator)


def test_signer_not_authorised_for_device_rejected(pqc_client, pqc_operator, pqc_world, clock):
    env = signed_env(pqc_world, clock, obs=make_obs(clock, device_id="DEVICE-002"))
    assert pqc_client.post(URL, json=env).status_code == 401
    assert "pqc_signer_not_authorised" in events(pqc_operator)


def test_signer_source_binding(pqc_client, pqc_world, clock):
    env = signed_env(pqc_world, clock, source_id="other_cam:0")   # validly signed, wrong source for this signer
    assert pqc_client.post(URL, json=env).status_code == 401


def test_metadata_payload_mismatch_rejected(pqc_client, pqc_operator, pqc_world, clock):
    env = sign_body(pqc_world, "vision-1", raw_body(clock, observation_id=str(uuid.uuid4())))
    assert pqc_client.post(URL, json=env).status_code == 401
    assert "pqc_payload_metadata_mismatch" in events(pqc_operator)


def test_unknown_device_in_payload_rejected(pqc_client, pqc_world, store, clock):
    store.revoke_device("DEVICE-001")
    assert pqc_client.post(URL, json=signed_env(pqc_world, clock)).status_code == 422


# ---------------- malformed ----------------

def test_validly_signed_but_malformed_payload_rejected(pqc_client, pqc_operator, pqc_world, clock):
    obs = make_obs(clock)
    body = raw_body(clock, obs=obs, payload='{"event_type": "trust_update"}')
    assert pqc_client.post(URL, json=sign_body(pqc_world, "vision-1", body)).status_code == 422
    assert "pqc_malformed_payload" in events(pqc_operator)


@pytest.mark.parametrize("break_it", [
    lambda e: e.pop("signature"), lambda e: e.pop("payload"), lambda e: e.pop("signer_id"),
    lambda e: e.update(extra_field=1), lambda e: e.update(protocol_version="one"),
    lambda e: e.update(signer_id="bad id/../"), lambda e: e.update(payload="x" * 20000),
    lambda e: e.update(observation_id="short"), lambda e: e.clear(),
])
def test_malformed_envelope_rejected(pqc_client, pqc_operator, pqc_world, clock, break_it):
    env = signed_env(pqc_world, clock)
    break_it(env)
    assert pqc_client.post(URL, json=env).status_code == 422
    assert stored(pqc_operator) == []


def test_non_json_body_rejected(pqc_client):
    assert pqc_client.post(URL, content=b"garbage", headers={"content-type": "application/json"}).status_code == 422


# ---------------- freshness and replay ----------------

def test_replayed_signed_observation_rejected(pqc_client, pqc_operator, pqc_world, clock):
    env = signed_env(pqc_world, clock)
    assert pqc_client.post(URL, json=env).status_code == 200
    r = pqc_client.post(URL, json=env)
    assert r.status_code == 409 and r.json()["detail"] == "replay_detected"
    assert "pqc_observation_replay" in events(pqc_operator)
    assert len(stored(pqc_operator)) == 1


def test_stale_signed_observation_rejected(pqc_client, pqc_operator, pqc_world, clock):
    env = signed_env(pqc_world, clock)          # signed "now"
    clock.advance(301)                          # replayed later than the freshness window
    assert pqc_client.post(URL, json=env).status_code == 401
    assert "pqc_stale_timestamp" in events(pqc_operator)


def test_future_timestamp_rejected(pqc_client, pqc_operator, pqc_world, clock):
    from datetime import timedelta
    env = signed_env(pqc_world, clock, at=now_dt(clock) + timedelta(seconds=600))
    assert pqc_client.post(URL, json=env).status_code == 401
    assert "pqc_future_timestamp" in events(pqc_operator)


def test_within_window_accepted(pqc_client, pqc_world, clock):
    env = signed_env(pqc_world, clock)
    clock.advance(299)
    assert pqc_client.post(URL, json=env).status_code == 200


# ---------------- canonical encoding ----------------

def test_field_boundaries_cannot_be_shifted():
    assert encode_fields(b"D", ["ab", "c"]) != encode_fields(b"D", ["a", "bc"])
    assert encode_fields(b"D", ["a", ""]) != encode_fields(b"D", ["a"])
    assert encode_fields(b"D", ["a"]) != encode_fields(b"E", ["a"])


def test_signing_bytes_independent_of_json_formatting_and_bound_to_every_field(pqc_world, clock):
    env = signed_env(pqc_world, clock)
    base = signing_bytes(env)
    for k in ("protocol_version", "algorithm", "signer_id", "source_id", "observation_id", "timestamp", "payload"):
        changed = {**env, k: (env[k] + 1 if isinstance(env[k], int) else env[k] + "x")}
        assert signing_bytes(changed) != base, k
    assert signing_bytes({**env, "signature": "different"}) == base   # signature itself is not signed


# ---------------- configuration ----------------

def test_signed_endpoints_503_when_pqc_not_configured(client, pqc_world, clock):
    r = client.post(URL, json=signed_env(pqc_world, clock))
    assert r.status_code == 503 and client.get("/api/v1/pqc/gateway-key").status_code == 503


def test_unsigned_path_can_be_disabled(store, creds, clock, device_secret, pqc_world):
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    from backend.config import Settings
    from tests.conftest import INGEST_TOKEN, OPERATOR_TOKEN
    app = create_app(Settings(db_path=":memory:", require_signed_observations=True), clock=clock, store=store,
                     creds=creds, operator_token=OPERATOR_TOKEN, ingest_token=INGEST_TOKEN, pqc=pqc_world.gateway)
    c = TestClient(app, headers={"Authorization": f"Bearer {INGEST_TOKEN}"})
    assert c.post("/api/v1/observations", json=make_obs(clock).to_wire()).status_code == 403
    assert TestClient(app).post(URL, json=signed_env(pqc_world, clock)).status_code == 200


def test_esp32_device_auth_unaffected_and_still_hmac(pqc_operator, pqc_client, device_secret, clock):
    from backend.protocol.envelope import build_hmac_envelope
    env = build_hmac_envelope(device_secret, "heartbeat", "DEVICE-001", 1, '{"uptime_ms":1}')
    assert pqc_client.post("/api/v1/heartbeat", json=env).status_code == 200
    assert pqc_operator.get("/api/v1/devices/DEVICE-001").json()["auth_profile"] == "hmac-sha256-psk"
    # a device HMAC envelope is not a valid PQC message
    assert pqc_client.post(URL, json=env).status_code == 422


def test_gateway_public_key_endpoint_matches_record(pqc_client, pqc_world):
    d = pqc_client.get("/api/v1/pqc/gateway-key").json()
    assert d["key_id"] == "gateway-kem-1" and d["algorithm"] == "ML-KEM-768"
    assert d["fingerprint_sha256"] == pqc_world.kem_rec.fingerprint
    assert base64.b64decode(d["public_key"]) == pqc_world.kem_rec.public_key
