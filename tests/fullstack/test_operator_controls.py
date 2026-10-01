"""Operator control layer (dashboard actions): start/abort recovery and set the digital-twin expected state.
Every action goes through the existing operator-token guard and the recovery orchestrator / trust state machine."""
import pytest
from fastapi.testclient import TestClient

from backend.recovery.orchestrator import RecoveryTimer
from tests.conftest import INGEST_TOKEN
from tests.fullstack.conftest import EXPECTED, quarantine_by_correlated_attack, state, trusted
from tests.fullstack.test_recovery import rec, report, reach_verified

DEV = "/api/v1/devices/DEVICE-001"
REASON = {"reason": "operator: incident contained"}
ACTIONS = [("post", f"{DEV}/recovery/start", REASON), ("post", f"{DEV}/recovery/abort", REASON),
           ("put", f"{DEV}/twin/expected", {"cfg_hash": "x"})]


@pytest.mark.parametrize("method,path,body", ACTIONS)
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong-token"}, {"Authorization": f"Bearer {INGEST_TOKEN}"},
                                     {"Authorization": "Basic Zm9vOmJhcg=="}])
def test_operator_actions_require_the_operator_token(stack, method, path, body, headers):
    quarantine_by_correlated_attack(stack)
    before = (state(stack), stack.twin.expected("DEVICE-001"))
    r = getattr(TestClient(stack.app), method)(path, json=body, headers=headers)
    assert r.status_code == 401
    assert (state(stack), stack.twin.expected("DEVICE-001")) == before and rec(stack) is None


def test_unknown_device_rejected(stack):
    for m, p, b in ACTIONS:
        assert getattr(stack.op, m)(p.replace("DEVICE-001", "NOPE-9"), json=b).status_code == 404


def test_start_requires_quarantined_device(stack):
    trusted(stack)
    r = stack.op.post(f"{DEV}/recovery/start", json=REASON)
    assert r.status_code == 409 and "device_not_quarantined" in r.text and state(stack) == "TRUSTED"


def test_start_cannot_smuggle_a_target_state_or_skip_reason(stack):
    quarantine_by_correlated_attack(stack)
    assert stack.op.post(f"{DEV}/recovery/start", json={**REASON, "target": "TRUSTED"}).status_code == 422
    assert stack.op.post(f"{DEV}/recovery/start", json={"reason": ""}).status_code == 422
    assert stack.op.post(f"{DEV}/recovery/start", json={}).status_code == 422
    assert state(stack) == "QUARANTINED"


def test_duplicate_start_is_refused_and_keeps_the_first_recovery(stack):
    quarantine_by_correlated_attack(stack)
    first = stack.op.post(f"{DEV}/recovery/start", json=REASON).json()
    r = stack.op.post(f"{DEV}/recovery/start", json=REASON)
    assert r.status_code == 409 and "recovery_already_active" in r.text
    assert rec(stack)["recovery_id"] == first["recovery_id"] and state(stack) == "RECOVERING"


def test_abort_without_active_recovery_is_refused(stack):
    quarantine_by_correlated_attack(stack)
    r = stack.op.post(f"{DEV}/recovery/abort", json=REASON)
    assert r.status_code == 409 and "no_active_recovery" in r.text and state(stack) == "QUARANTINED"


def test_abort_from_verified_returns_to_quarantined_and_is_recorded(stack):
    quarantine_by_correlated_attack(stack)
    stack.agent.cfg_hash = None
    reach_verified(stack)
    r = stack.op.post(f"{DEV}/recovery/abort", json={"reason": "operator: new indicator of compromise"})
    assert r.status_code == 200 and r.json()["status"] == "failed"
    # Phase 13: the abort reason carries the authenticated operator identity
    assert r.json()["failure_reason"] == "aborted: operator: new indicator of compromise (by bootstrap-admin)"
    assert state(stack) == "QUARANTINED"
    evs = [e for e in stack.store.list_events(200) if e["event_type"] == "recovery_failed"]
    assert evs and evs[0]["device_id"] == "DEVICE-001"
    tl = stack.op.get("/api/v1/evidence/device/DEVICE-001").json()
    assert any(e["event_type"] == "recovery_failed" and "aborted" in str(e) for e in tl)
    assert stack.op.get("/api/v1/evidence/verify").json()["ok"]


@pytest.mark.parametrize("bad", [{}, {"fw_version": ""}, {"cfg_hash": 5}, {"cfg_hash": "x" * 129},
                                 {"cfg_hash": "a", "root": True}, {"cfg_hash": "a", "sensor_ranges": {"t": [5, 1]}},
                                 {"capabilities": ["tamper"]}])
def test_invalid_expected_state_rejected(stack, bad):
    trusted(stack)
    before = stack.twin.expected("DEVICE-001")
    assert stack.op.put(f"{DEV}/twin/expected", json=bad).status_code == 422
    assert stack.twin.expected("DEVICE-001") == before


def test_expected_state_frozen_during_recovery(stack):
    quarantine_by_correlated_attack(stack)
    stack.op.post(f"{DEV}/recovery/start", json=REASON)
    r = stack.op.put(f"{DEV}/twin/expected", json={**EXPECTED, "cfg_hash": "attacker-cfg"})
    assert r.status_code == 409 and stack.twin.expected("DEVICE-001")["cfg_hash"] == "cfg-good-1"
    stack.op.post(f"{DEV}/recovery/abort", json=REASON)
    assert stack.op.put(f"{DEV}/twin/expected", json={**EXPECTED, "cfg_hash": "cfg-good-2"}).status_code == 200


def test_expected_state_update_drives_match_and_mismatch_and_is_recorded(stack):
    trusted(stack)
    tw = stack.op.get(f"{DEV}/twin").json()
    assert tw["comparison"]["overall"] == "MATCH" and tw["observed"]["cfg_hash"] == "cfg-good-1"
    r = stack.op.put(f"{DEV}/twin/expected", json={**EXPECTED, "cfg_hash": "cfg-good-2"})
    assert r.status_code == 200 and r.json()["expected"]["cfg_hash"] == "cfg-good-2"
    tw = stack.op.get(f"{DEV}/twin").json()
    assert tw["expected"]["cfg_hash"] == "cfg-good-2" and tw["observed"]["cfg_hash"] == "cfg-good-1"   # kept distinct
    assert tw["comparison"]["fields"]["cfg_hash"]["status"] == "MISMATCH"
    stack.agent.cfg_hash = "cfg-good-2"
    stack.clock.advance(10)
    assert stack.agent.telemetry().status_code == 200
    assert stack.op.get(f"{DEV}/twin").json()["comparison"]["overall"] == "MATCH"
    tl = stack.op.get("/api/v1/evidence/device/DEVICE-001").json()
    assert any(e["event_type"] == "twin_expected_updated" for e in tl)


def test_operator_start_then_timeout_via_background_timer(stack):
    quarantine_by_correlated_attack(stack)
    assert stack.op.post(f"{DEV}/recovery/start", json=REASON).status_code == 200
    report(stack)                                   # device picks up the command, then goes silent
    stack.clock.advance(1000)
    RecoveryTimer(stack.recovery, 1.0).run_once()   # no HTTP request involved
    r = stack.recovery.latest("DEVICE-001")
    assert r["status"] == "failed" and r["failure_reason"] == "deadline_exceeded_before_verification"
    assert stack.trust.state_of("DEVICE-001").name == "QUARANTINED"
    # operator can try again; the timer keeps working on the new recovery
    assert stack.op.post(f"{DEV}/recovery/start", json=REASON).status_code == 200
    stack.clock.advance(1000)
    RecoveryTimer(stack.recovery, 1.0).run_once()
    assert stack.recovery.latest("DEVICE-001")["status"] == "failed"
