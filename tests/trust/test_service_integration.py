"""Phase 4: pipeline over the real gateway: records -> authenticity -> features -> trust engine -> event."""
import base64
import json

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config import Settings
from backend.protocol.envelope import MSG_TELEMETRY, build_hmac_envelope
from backend.trust.config import TrustConfig
from backend.trust.service import TrustService
from device_agent.agent import DeviceAgent
from tests.conftest import OPERATOR_TOKEN
from tests.pqc_helpers import make_obs, signed_env


def trust_of(top, dev="DEVICE-001"):
    return top.get(f"/api/v1/trust/{dev}").json()


def boot(tc, secret):
    a = DeviceAgent("DEVICE-001", secret, tc)
    assert a.register().status_code == 200
    assert a.telemetry().status_code == 200
    return a


def custom_app(store, creds, clock, pqc_world, cfg):
    svc = TrustService(store, cfg, clock=clock)
    app = create_app(Settings(db_path=":memory:"), clock=clock, store=store, creds=creds, operator_token=OPERATOR_TOKEN,
                     pqc=pqc_world.gateway, trust=svc)
    return TestClient(app), TestClient(app, headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"})


def test_no_evidence_before_any_authenticated_message(top, device_secret):
    assert trust_of(top) == {"device_id": "DEVICE-001", "status": "NO_EVIDENCE"}


def test_authenticated_telemetry_creates_trusted_record(tc, top, device_secret):
    boot(tc, device_secret)
    t = trust_of(top)
    assert t["state"] == "TRUSTED" and t["score"] == 100 and t["status"] == "TRACKED"
    hist = top.get("/api/v1/trust/DEVICE-001/history").json()
    assert hist and hist[-1]["kind"] == "created" and hist[-1]["new_score"] == 100


def test_signed_visual_rule_violation_lowers_trust_with_exact_reason(tc, top, device_secret, pqc_world, clock):
    boot(tc, device_secret)
    r = tc.post("/api/v1/observations/signed", json=signed_env(pqc_world, clock, obs=make_obs(clock, confidence=0.9)))
    assert r.status_code == 200
    ch = top.get("/api/v1/trust/DEVICE-001/history").json()[0]
    assert ch["previous_score"] == 100 and ch["new_score"] < 100 and ch["delta"] == ch["new_score"] - ch["previous_score"]
    top_reason = ch["reasons"][0]
    assert top_reason["signal"] == "visual_rule_violation" and top_reason["confidence"] == 0.9 and top_reason["authenticity"] == "SIGNER_MLDSA"
    assert abs(sum(x["impact"] for x in ch["reasons"]) - (ch["new_exact"] - ch["previous_exact"])) < 1e-6
    assert trust_of(top)["factors"]["visual"]["penalty"] == pytest.approx(81.0)


def test_token_only_observation_has_half_the_effect(tc, top, ingest, device_secret, clock):
    boot(tc, device_secret)
    assert ingest.post("/api/v1/observations", json=make_obs(clock, confidence=0.9).to_wire()).status_code == 200
    assert trust_of(top)["factors"]["visual"]["penalty"] == pytest.approx(40.5)


def test_forged_observation_signature_is_pressure_only_and_bounded(tc, top, device_secret, pqc_world, clock):
    boot(tc, device_secret)
    for _ in range(60):
        env = signed_env(pqc_world, clock)
        env["signature"] = base64.b64encode(b"\x00" * 3309).decode()
        assert tc.post("/api/v1/observations/signed", json=env).status_code == 401
    t = trust_of(top)
    assert t["pressure"] == 25 and t["score"] >= 75 and t["state"] != "QUARANTINED"
    assert t["factors"]["visual"]["available"] is False               # forged data produced no visual evidence


def test_forged_hmac_flood_does_not_quarantine(tc, top, device_secret, clock):
    boot(tc, device_secret)
    for i in range(40):
        env = build_hmac_envelope(b"x" * 32, MSG_TELEMETRY, "DEVICE-001", 1000 + i, json.dumps({"tamper": True}))
        assert tc.post("/api/v1/telemetry", json=env).status_code == 401
    t = trust_of(top)
    assert t["state"] != "QUARANTINED" and t["score"] >= 75 and t["tamper_active"] is False


def test_unknown_device_events_are_unattributed(tc, top, device_secret):
    boot(tc, device_secret)
    env = build_hmac_envelope(b"x" * 32, MSG_TELEMETRY, "GHOST-9", 1, json.dumps({"tamper": True}))
    tc.post("/api/v1/telemetry", json=env)
    assert top.get("/api/v1/trust/GHOST-9").status_code == 404
    assert trust_of(top)["score"] == 100
    assert any(d["reason"].startswith("unattributed") for d in top.get("/api/v1/trust/diagnostics").json())


def test_operator_auth_failures_are_not_device_trust(tc, top, device_secret):
    boot(tc, device_secret)
    for _ in range(5):
        tc.get("/api/v1/devices")                                       # no operator token -> operator_auth_failed event
    assert trust_of(top)["score"] == 100


def test_device_tamper_telemetry_caps_and_persists(tc, top, device_secret):
    a = boot(tc, device_secret)
    a.tamper = True
    a.telemetry()
    a.tamper = False
    a.telemetry()
    t = trust_of(top)
    assert t["score"] <= 55 and any(c["name"] == "physical_tamper" for c in t["caps"])
    assert t["provenance"].get("physical_tamper") == "simulated by software-agent"


def test_tamper_plus_signed_visual_is_confirmed_incident(tc, top, device_secret, pqc_world, clock):
    a = boot(tc, device_secret)
    a.tamper = True
    a.telemetry()
    tc.post("/api/v1/observations/signed", json=signed_env(pqc_world, clock, obs=make_obs(clock, confidence=0.9)))
    t = trust_of(top)
    assert t["incident"]["class"] == "confirmed_incident" and t["state"] == "QUARANTINED" and t["score"] <= 30
    assert "quarantine recommended" in t["recommended_action"]


def test_no_sensor_limits_means_sensor_factor_unavailable(tc, top, device_secret):
    a = boot(tc, device_secret)
    a.telemetry(temperature_c=900.0)                                   # not invented into an anomaly
    assert trust_of(top)["factors"]["sensor_consistency"]["available"] is False


def test_configured_sensor_limit_flags_out_of_range(store, creds, clock, device_secret, pqc_world):
    c, op = custom_app(store, creds, clock, pqc_world, TrustConfig(sensor_limits={"temperature_c": (-20.0, 60.0)}))
    a = DeviceAgent("DEVICE-001", device_secret, c)
    a.register()
    a.telemetry(temperature_c=25.0)
    assert op.get("/api/v1/trust/DEVICE-001").json()["factors"]["sensor_consistency"]["penalty"] == 0
    a.telemetry(temperature_c=900.0)
    assert op.get("/api/v1/trust/DEVICE-001").json()["factors"]["sensor_consistency"]["penalty"] == 60


def test_integrity_expectation_from_config(store, creds, clock, device_secret, pqc_world):
    c, op = custom_app(store, creds, clock, pqc_world, TrustConfig(expected_fw_version="agent-0.1"))
    a = DeviceAgent("DEVICE-001", device_secret, c)
    a.register()
    a.telemetry()
    assert op.get("/api/v1/trust/DEVICE-001").json()["score"] == 100
    a.telemetry(fw_version="evil-9")
    t = op.get("/api/v1/trust/DEVICE-001").json()
    assert t["score"] <= 65 and any(x["name"] == "integrity_mismatch" for x in t["caps"])
    assert "not proof" in t["provenance"]["integrity_mismatch"]


def test_replayed_signed_observation_is_pressure_not_new_evidence(tc, top, device_secret, pqc_world, clock):
    boot(tc, device_secret)
    env = signed_env(pqc_world, clock, obs=make_obs(clock, confidence=0.9))
    assert tc.post("/api/v1/observations/signed", json=env).status_code == 200
    p1 = trust_of(top)["factors"]["visual"]["penalty"]
    for _ in range(4):
        assert tc.post("/api/v1/observations/signed", json=env).status_code == 409
    t = trust_of(top)
    assert t["factors"]["visual"]["penalty"] == p1 and t["pressure"] > 0
    assert any(c["name"] == "repeated_replay" for c in t["caps"])


def test_signer_misuse_is_auth_misbehavior_on_the_targeted_device_only(tc, top, device_secret, pqc_world, clock):
    boot(tc, device_secret)
    obs = make_obs(clock, device_id="DEVICE-002")                       # vision-1 is not authorised for DEVICE-002
    assert tc.post("/api/v1/observations/signed", json=signed_env(pqc_world, clock, obs=obs)).status_code == 401
    t = trust_of(top, "DEVICE-002")
    assert t["status"] == "TRACKED" and t["score"] <= 70 and any(c["name"] == "auth_violation" for c in t["caps"])
    assert trust_of(top)["score"] == 100


def test_revocation_zeroes_trust(tc, top, device_secret, store):
    boot(tc, device_secret)
    store.revoke_device("DEVICE-001")
    t = trust_of(top)
    assert t["score"] == 0 and t["state"] == "QUARANTINED" and t["revoked"]


def test_staleness_lowers_score_with_no_new_traffic(tc, top, device_secret, clock):
    boot(tc, device_secret)
    clock.advance(200)
    t = trust_of(top)
    assert t["score"] <= 79 and t["last_device_evidence_age_s"] >= 200
    hist = top.get("/api/v1/trust/DEVICE-001/history").json()
    assert hist[0]["kind"] == "time_driven" and hist[0]["reasons"][0]["signal"] == "network_liveness"


def test_restart_restores_state_and_cursors_prevent_double_counting(tc, top, device_secret, pqc_world, clock, store):
    boot(tc, device_secret)
    tc.post("/api/v1/observations/signed", json=signed_env(pqc_world, clock, obs=make_obs(clock, confidence=0.9)))
    before = trust_of(top)
    n = len(store.trust_history("DEVICE-001", 500))
    svc2 = TrustService(store, TrustConfig(), clock=clock)
    assert svc2.process_pending() == []
    assert svc2.snapshot("DEVICE-001")["score"] == before["score"]
    assert len(store.trust_history("DEVICE-001", 500)) == n


def test_trust_endpoints_require_operator_token(tc, ingest, device_secret):
    boot(tc, device_secret)
    for path in ("/api/v1/trust", "/api/v1/trust/DEVICE-001", "/api/v1/trust/DEVICE-001/history", "/api/v1/trust/diagnostics"):
        assert tc.get(path).status_code == 401
        assert ingest.get(path).status_code == 401                     # ingest token is a different security domain


def test_trust_endpoints_are_read_only(top):
    assert top.post("/api/v1/trust/DEVICE-001").status_code in (404, 405)
    assert top.put("/api/v1/trust/DEVICE-001").status_code in (404, 405)


def test_trust_engine_failure_never_breaks_the_gateway(tc, trust, device_secret, monkeypatch, store):
    def boom():
        raise RuntimeError("boom")
    monkeypatch.setattr(trust, "process_pending", boom)
    assert DeviceAgent("DEVICE-001", device_secret, tc).register().status_code == 200
    assert any(e["event_type"] == "trust_engine_error" for e in store.list_events(50))


def test_app_without_trust_has_no_trust_routes(client):
    assert client.get("/api/v1/trust").status_code == 404
