"""Phase 6: quarantine is enforced at the gateway; the recovery channel stays open; forged traffic cannot bypass it."""
import json

from backend.protocol.envelope import MSG_TELEMETRY, build_hmac_envelope
from device_agent.agent import DeviceAgent
from tests.fullstack.conftest import quarantine_by_correlated_attack, state, trusted


def events(s, etype):
    return [e for e in s.op.get("/api/v1/events", params={"limit": 500}).json() if e["event_type"] == etype]


def test_trusted_device_allowed_and_recovery_channel_closed(stack):
    trusted(stack)
    assert stack.agent.telemetry().status_code == 200
    assert stack.agent.heartbeat().status_code == 200
    r = stack.agent.recovery_report()
    assert r.status_code == 403 and r.json()["detail"] == "recovery_channel_not_open"
    acc = stack.op.get("/api/v1/devices/DEVICE-001/access").json()
    assert acc["normal"]["allowed"] and not acc["recovery"]["allowed"]


def test_suspicious_device_still_allowed(stack):
    trusted(stack)
    stack.sim.tamper()
    assert state(stack) == "SUSPICIOUS"
    assert stack.agent.telemetry(tamper=False).status_code == 200


def test_quarantined_device_blocked_on_every_normal_endpoint(stack):
    quarantine_by_correlated_attack(stack)
    assert stack.agent.telemetry().status_code == 403
    assert stack.agent.heartbeat().status_code == 403
    assert stack.agent.register().status_code == 403
    assert events(stack, "quarantine_access_blocked")
    acc = stack.op.get("/api/v1/devices/DEVICE-001/access").json()
    assert not acc["normal"]["allowed"] and acc["recovery"]["allowed"]


def test_blocked_messages_are_not_trust_evidence(stack):
    quarantine_by_correlated_attack(stack)
    credit = stack.trust.engine.devices["DEVICE-001"].credit_clock
    stack.clock.advance(40)
    assert stack.agent.telemetry(tamper=False).status_code == 403
    assert stack.trust.engine.devices["DEVICE-001"].credit_clock == credit      # nothing credited
    assert stack.trust.engine.devices["DEVICE-001"].tamper_active is True       # blocked "all clear" not believed


def test_recovery_channel_preserved_and_credits_evidence(stack):
    quarantine_by_correlated_attack(stack)
    credit = stack.trust.engine.devices["DEVICE-001"].credit_clock
    stack.clock.advance(40)
    r = stack.agent.recovery_report(tamper=False)
    assert r.status_code == 200 and r.json()["channel"] == "recovery"
    assert stack.trust.engine.devices["DEVICE-001"].credit_clock > credit
    assert state(stack) == "QUARANTINED"                                       # evidence alone never leaves quarantine


def test_forged_traffic_cannot_bypass_quarantine(stack):
    quarantine_by_correlated_attack(stack)
    for path, t in (("telemetry", MSG_TELEMETRY), ("recovery/report", "recovery")):
        env = build_hmac_envelope(b"z" * 32, t, "DEVICE-001", 10**12, json.dumps({"tamper": False}))
        assert stack.gw.post(f"/api/v1/{path}", json=env).status_code == 401
    assert state(stack) == "QUARANTINED"


def test_revoked_device_stays_blocked_everywhere(stack):
    quarantine_by_correlated_attack(stack)
    stack.store.revoke_device("DEVICE-001")
    assert stack.agent.telemetry().status_code == 401
    assert stack.agent.recovery_report().status_code == 401
    t = stack.op.get("/api/v1/trust/DEVICE-001").json()
    assert t["score"] == 0 and t["state"] == "QUARANTINED"
    assert stack.op.post("/api/v1/devices/DEVICE-001/recovery/start", json={"reason": "try"}).status_code == 409


def test_operator_manual_quarantine_and_control_channel_auth(stack):
    trusted(stack)
    assert stack.gw.post("/api/v1/devices/DEVICE-001/quarantine", json={"reason": "manual"}).status_code == 401
    r = stack.op.post("/api/v1/devices/DEVICE-001/quarantine", json={"reason": "operator saw something"})
    assert r.status_code == 200 and r.json()["state"] == "QUARANTINED"
    assert stack.agent.telemetry().status_code == 403
    for path in ("/api/v1/devices/DEVICE-001/access", "/api/v1/evidence", "/api/v1/devices/DEVICE-001/twin",
                 "/api/v1/devices/DEVICE-001/recovery"):
        assert stack.gw.get(path).status_code == 401


def test_unauthorised_control_actions_rejected(stack):
    trusted(stack)
    assert stack.gw.put("/api/v1/devices/DEVICE-001/twin/expected", json={"cfg_hash": "x"}).status_code == 401
    assert stack.gw.post("/api/v1/devices/DEVICE-001/recovery/start", json={"reason": "xyz"}).status_code == 401


def test_enforcement_uses_last_known_state_when_trust_engine_faults(stack, monkeypatch):
    quarantine_by_correlated_attack(stack)

    def boom():
        raise RuntimeError("boom")
    monkeypatch.setattr(stack.trust, "process_pending", boom)
    assert stack.agent.telemetry().status_code == 403                        # known-quarantined stays blocked
    other = DeviceAgent("DEVICE-002", b"\x00" * 32, stack.gw)
    assert other.telemetry().status_code == 401                              # authentication unaffected


def test_block_logging_is_throttled(stack):
    quarantine_by_correlated_attack(stack)
    for _ in range(20):
        stack.agent.telemetry()
    assert len(events(stack, "quarantine_access_blocked")) == 1


def test_dashboard_is_served_and_holds_no_data(stack):
    r = stack.gw.get("/dashboard/")
    assert r.status_code == 200 and "Q-SHIELD" in r.text
    assert "Bearer" not in r.text                          # token only ever comes from the operator
    # The dashboard is ES modules since the UI rework: routes in lib/api.js, escaping in lib/html.js.
    api = stack.gw.get("/dashboard/src/lib/api.js").text
    assert "/api/v1/evidence/verify" in api and "Bearer" in api      # the header is built from the signed-in token
    assert "esc(" in stack.gw.get("/dashboard/src/lib/html.js").text
    assert "qso_" not in r.text and "token=" not in r.text                 # no credential baked into the page
