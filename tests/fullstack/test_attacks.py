"""Phase 5: every simulated attack runs through the real gateway and is detected by the real pipeline."""
import json

from tests.fullstack.conftest import state, trusted


def test_forged_signature_rejected_and_bounded(stack):
    trusted(stack)
    r = stack.sim.forge()
    assert r.http_status == [401] and r.detected
    assert r.trust_effect["after"] < 100 and r.trust_effect["pressure_after"] <= 25
    assert r.state_effect["after"] in ("TRUSTED", "SUSPICIOUS")
    assert r.evidence_id and r.simulated


def test_replay_rejected(stack):
    trusted(stack)
    r = stack.sim.replay()
    assert r.http_status == [200, 409] and r.detected
    assert r.trust_effect["delta"] < 0


def test_malformed_packet_penalises_identity(stack):
    trusted(stack)
    r = stack.sim.malformed()
    assert r.http_status == [422] and r.detected
    t = stack.op.get("/api/v1/trust/DEVICE-001").json()
    assert t["factors"]["identity_crypto"]["penalty"] > 0


def test_authentication_violation_flood_cannot_quarantine(stack):
    trusted(stack)
    r = stack.sim.auth_violation(attempts=40)
    assert set(r.http_status) == {401} and r.detected
    assert r.state_effect["after"] != "QUARANTINED" and r.trust_effect["pressure_after"] <= 25
    t = stack.op.get("/api/v1/trust/DEVICE-001").json()
    assert t["tamper_active"] is False                      # the forged tamper claim was never believed


def test_rogue_device_rejected_and_unattributed(stack):
    trusted(stack)
    r = stack.sim.rogue_device()
    assert r.http_status == [401] and r.detected
    assert r.trust_effect["delta"] == 0
    rogue = r.payload["rogue_device_id"]
    assert stack.op.get(f"/api/v1/trust/{rogue}").status_code == 404


def test_abnormal_sensor_telemetry_uses_twin_range(stack):
    trusted(stack)
    r = stack.sim.sensor_anomaly("temperature_c", 95.0)
    assert r.http_status == [200] and r.detected and r.trust_effect["delta"] < 0
    cmp = stack.op.get("/api/v1/devices/DEVICE-001/twin").json()["comparison"]
    assert cmp["fields"]["sensor:temperature_c"]["status"] == "MISMATCH"


def test_physical_tamper(stack):
    trusted(stack)
    r = stack.sim.tamper()
    assert r.detected and r.trust_effect["after"] <= 55 and "physical_tamper" in r.trust_effect["caps_after"]
    assert r.state_effect == {"before": "TRUSTED", "after": "SUSPICIOUS"}


def test_config_integrity_mismatch(stack):
    trusted(stack)
    r = stack.sim.config_mismatch()
    assert r.detected and r.trust_effect["after"] <= 65
    assert stack.op.get("/api/v1/devices/DEVICE-001/twin").json()["comparison"]["fields"]["cfg_hash"]["status"] == "MISMATCH"


def test_visual_rule_violation(stack):
    trusted(stack)
    r = stack.sim.visual_violation(0.9)
    assert r.http_status == [200] and r.detected and r.trust_effect["delta"] < 0


def test_correlated_attack_quarantines_and_blocks(stack):
    trusted(stack)
    r = stack.sim.correlated()
    assert r.detected and r.state_effect["after"] == "QUARANTINED" and r.trust_effect["after"] <= 30
    b = stack.sim.quarantine_bypass()
    assert b.http_status == [403, 401] and b.detected


def test_every_result_is_serialisable_and_labelled(stack):
    trusted(stack)
    for fn in (stack.sim.forge, stack.sim.replay, stack.sim.rogue_device, stack.sim.visual_violation):
        fn()
    for res in stack.sim.results:
        d = res.to_dict()
        json.dumps(d)
        assert d["simulated"] is True and "SIMULATED" in d["note"]
        assert {"attack_id", "attack_type", "target_device", "timestamp", "payload", "expected_detection",
                "actual_detection", "trust_effect", "state_effect", "evidence_id"} <= set(d)
    assert len(stack.sim.summary()) == 4


def test_forged_attacks_leave_evidence_chain_valid(stack):
    trusted(stack)
    stack.sim.forge()
    stack.sim.replay()
    v = stack.op.get("/api/v1/evidence/verify").json()
    assert v["ok"] and v["signed"] and v["count"] >= 3
    assert state(stack) in ("TRUSTED", "SUSPICIOUS")
