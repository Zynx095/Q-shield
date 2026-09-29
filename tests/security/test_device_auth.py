"""HMAC-SHA256 device authentication (symmetric; not PQC)."""
import json
import secrets
from pathlib import Path

from backend.protocol.envelope import (
    AUTH_HMAC, Envelope, build_hmac_envelope, hmac_tag, signing_input,
)

VECTOR = json.loads((Path(__file__).parents[1] / "vectors" / "envelope_v1.json").read_text())
PAYLOAD = '{"temperature_c":27.4,"vibration_g":0.02,"tamper":false}'


def test_shared_vector_matches_implementation():
    secret = bytes.fromhex(VECTOR["secret_hex"])
    data = signing_input(VECTOR["auth"], VECTOR["type"], VECTOR["device_id"], VECTOR["counter"], VECTOR["payload"])
    assert data.hex() == VECTOR["signing_input_hex"]
    assert hmac_tag(secret, data) == VECTOR["tag"]


def post(client, env):
    return client.post(f"/api/v1/{env['type']}", json=env)


def env_for(secret, counter, payload=PAYLOAD, msg_type="telemetry", device_id="DEVICE-001"):
    return build_hmac_envelope(secret, msg_type, device_id, counter, payload)


def event_types(client):
    return [e["event_type"] for e in client.get("/api/v1/events").json()]


def test_valid_message_accepted(client, device_secret):
    assert post(client, env_for(device_secret, 1)).status_code == 200


def test_modified_payload_rejected(client, device_secret):
    env = env_for(device_secret, 1)
    env["payload"] = env["payload"].replace("27.4", "97.4")  # attacker edits temperature
    r = post(client, env)
    assert r.status_code == 401
    assert "invalid_tag" in event_types(client)
    assert client.get("/api/v1/devices/DEVICE-001").json()["temperature_c"] is None  # nothing stored


def test_wrong_key_rejected(client):
    r = post(client, env_for(secrets.token_bytes(32), 1))
    assert r.status_code == 401
    assert "invalid_tag" in event_types(client)


def test_tag_covering_wrong_counter_rejected(client, device_secret):
    env = env_for(device_secret, 5)
    env["counter"] = 6  # counter is bound into the tag
    assert post(client, env).status_code == 401


def test_message_type_is_bound_to_tag(client, device_secret):
    env = env_for(device_secret, 1, payload='{"uptime_ms":1}', msg_type="heartbeat")
    env["type"] = "telemetry"
    assert post(client, env).status_code == 401


def test_unknown_device_rejected(client):
    r = post(client, env_for(secrets.token_bytes(32), 1, device_id="ROGUE-999"))
    assert r.status_code == 401
    ev = client.get("/api/v1/events").json()[0]
    assert ev["event_type"] == "unknown_device"
    assert ev["details"]["claimed_device_id"] == "ROGUE-999"


def test_error_does_not_reveal_reason(client, device_secret):
    bad_tag = post(client, {**env_for(device_secret, 1), "tag": "00" * 32})
    unknown = post(client, env_for(device_secret, 1, device_id="ROGUE-999"))
    assert bad_tag.json() == unknown.json() == {"detail": "authentication_failed"}


def test_replay_rejected(client, device_secret):
    env = env_for(device_secret, 7)
    assert post(client, env).status_code == 200
    assert post(client, env).status_code == 401
    assert "replay_or_stale_counter" in event_types(client)


def test_stale_counter_rejected(client, device_secret):
    assert post(client, env_for(device_secret, 10)).status_code == 200
    assert post(client, env_for(device_secret, 9)).status_code == 401


def test_unauthenticated_sender_cannot_burn_counter(client, device_secret):
    post(client, env_for(secrets.token_bytes(32), 1000))  # attacker, wrong key
    assert post(client, env_for(device_secret, 1)).status_code == 200


def test_revoked_device_rejected(client, store, device_secret):
    store.revoke_device("DEVICE-001")
    assert post(client, env_for(device_secret, 1)).status_code == 401
    assert "revoked_device" in event_types(client)


def test_unsupported_protocol_version_rejected(client, device_secret):
    env = env_for(device_secret, 1)
    env["proto"] = 2
    assert post(client, env).status_code == 401


def test_pqc_profile_not_pretended(client, device_secret):
    """Phase 1 must refuse the PQC profile instead of pretending to verify it."""
    env = env_for(device_secret, 1)
    env["auth"] = "pqc-mldsa-mlkem"
    assert post(client, env).status_code == 401
    assert "auth_profile_mismatch" in event_types(client)  # device enrolled for HMAC


def test_wrong_endpoint_rejected(client, device_secret):
    env = env_for(device_secret, 1)  # a telemetry envelope
    assert client.post("/api/v1/heartbeat", json=env).status_code == 401


def test_authenticated_but_malformed_payload_rejected(client, device_secret):
    r = post(client, env_for(device_secret, 1, payload='{"tamper":"maybe"}'))
    assert r.status_code == 422
    assert "malformed_payload" in event_types(client)


def test_envelope_model_rejects_bad_device_id():
    import pydantic, pytest
    with pytest.raises(pydantic.ValidationError):
        Envelope(proto=1, auth=AUTH_HMAC, type="telemetry", device_id="a b/../c", counter=1, payload="{}", tag="x")
