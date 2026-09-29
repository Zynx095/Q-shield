"""Operator/ingest bearer tokens are separate from device HMAC auth."""
import pytest

from backend.protocol.envelope import build_hmac_envelope
from backend.security.tokens import (
    TokenError, bearer_from_header, load_or_create_token, token_matches,
)
from tests.conftest import OPERATOR_TOKEN

READ_PATHS = ["/api/v1/devices", "/api/v1/devices/DEVICE-001", "/api/v1/devices/DEVICE-001/telemetry",
              "/api/v1/events", "/api/v1/observations"]


@pytest.mark.parametrize("path", READ_PATHS)
def test_reads_require_operator_token(anon_client, path):
    r = anon_client.get(path)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("path", READ_PATHS)
def test_reads_accept_operator_token(client, path):
    assert client.get(path).status_code == 200


def test_wrong_and_malformed_tokens_rejected(anon_client):
    for h in ["Bearer wrong", "Bearer ", "Basic " + OPERATOR_TOKEN, OPERATOR_TOKEN, "bearer"]:
        assert anon_client.get("/api/v1/devices", headers={"Authorization": h}).status_code == 401


def test_ingest_token_does_not_open_operator_apis(ingest_client):
    assert ingest_client.get("/api/v1/devices").status_code == 401


def test_operator_token_does_not_open_ingest(client):
    assert client.post("/api/v1/observations", json={}).status_code == 401


def test_health_is_open(anon_client):
    assert anon_client.get("/api/v1/health").status_code == 200


def test_device_endpoints_ignore_bearer_and_still_need_hmac(anon_client, client, device_secret):
    env = build_hmac_envelope(device_secret, "heartbeat", "DEVICE-001", 1, '{"uptime_ms":1}')
    assert anon_client.post("/api/v1/heartbeat", json=env).status_code == 200  # no bearer needed
    forged = {**build_hmac_envelope(device_secret, "heartbeat", "DEVICE-001", 2, '{"uptime_ms":2}'),
              "tag": "0" * 64}
    assert client.post("/api/v1/heartbeat", json=forged).status_code == 401  # bearer can't substitute


def test_failed_operator_auth_logged_but_throttled(anon_client, client, clock):
    for _ in range(5):
        anon_client.get("/api/v1/devices")
    ev = [e for e in client.get("/api/v1/events").json() if e["event_type"] == "operator_auth_failed"]
    assert len(ev) == 1
    assert OPERATOR_TOKEN not in str(ev)
    clock.advance(11)
    anon_client.get("/api/v1/devices")
    ev = [e for e in client.get("/api/v1/events").json() if e["event_type"] == "operator_auth_failed"]
    assert len(ev) == 2


def test_token_helpers(tmp_path):
    t = load_or_create_token("operator", tmp_path)
    assert len(t) >= 32 and load_or_create_token("operator", tmp_path) == t
    assert load_or_create_token("ingest", tmp_path) != t
    assert token_matches(t, t) and not token_matches(t + "x", t) and not token_matches(None, t)
    assert bearer_from_header(f"Bearer {t}") == t and bearer_from_header("Basic x") is None
    with pytest.raises(TokenError):
        load_or_create_token("operator", tmp_path, "short")
    with pytest.raises(TokenError):
        load_or_create_token("admin", tmp_path)
