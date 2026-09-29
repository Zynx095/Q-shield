"""Phase 7: orchestrated recovery with real authenticated evidence, and every failure path fails closed."""
from tests.fullstack.conftest import quarantine_by_correlated_attack, state, trusted

STEP = 40          # seconds between device reports (<= the trust engine's 45 s credit cap)


def rec(s):
    return s.op.get("/api/v1/devices/DEVICE-001/recovery").json()["current"]


def start(s, reason="operator: incident contained, begin remediation"):
    r = s.op.post("/api/v1/devices/DEVICE-001/recovery/start", json={"reason": reason})
    assert r.status_code == 200, r.text
    return r.json()


def report(s, **kw):
    s.clock.advance(STEP)
    r = s.agent.recovery_report(**kw)
    assert r.status_code == 200, r.text
    return r


def reach_verified(s):
    start(s)
    assert state(s) == "RECOVERING"
    r = report(s)                                  # receives the remediation command
    assert r.json()["command"]["action"] == "apply_known_good_config"
    report(s)                                      # acknowledges it (agent applied the known-good config)
    assert rec(s)["stage"] == "health_checks"
    for _ in range(3):
        report(s)
    assert state(s) == "VERIFIED" and rec(s)["stage"] == "trust_ramp"


def test_full_successful_recovery_rebuilds_trust(stack):
    quarantine_by_correlated_attack(stack)
    stack.agent.cfg_hash = None                    # compromised device lost its known-good configuration
    reach_verified(stack)
    assert stack.agent.telemetry().status_code == 403            # VERIFIED: normal access still closed
    for _ in range(200):
        report(stack)
        if state(stack) == "RECOVERED":
            break
    assert state(stack) == "RECOVERED" and stack.trust.score_of("DEVICE-001") >= 50
    for _ in range(400):                                          # access restored: back on the normal channel
        stack.clock.advance(STEP)
        assert stack.agent.telemetry().status_code == 200
        if rec(stack)["status"] == "completed":
            break
    r = rec(stack)
    assert r["status"] == "completed" and state(stack) == "TRUSTED" and stack.trust.score_of("DEVICE-001") >= 85
    kinds = [e["event"] for e in r["log"]]
    for k in ("recovery_started", "remediation_acknowledged", "recovery_verified", "access_restored", "recovery_completed"):
        assert k in kinds
    v = stack.op.get("/api/v1/evidence/verify").json()
    assert v["ok"] and v["signed"]
    tl = [e["event_type"] for e in stack.op.get("/api/v1/evidence/device/DEVICE-001").json()]
    assert "recovery_started" in tl and "recovery_completed" in tl and "trust_state_transition" in tl


def test_start_preconditions(stack):
    trusted(stack)
    assert stack.op.post("/api/v1/devices/DEVICE-001/recovery/start", json={"reason": "no need"}).status_code == 409
    stack.sim.correlated()
    stack.store.execute("DELETE FROM device_twin WHERE device_id='DEVICE-001'")
    r = stack.op.post("/api/v1/devices/DEVICE-001/recovery/start", json={"reason": "go now"})
    assert r.status_code == 409 and "no_expected_state" in r.text


def test_fault_during_recovery_returns_to_quarantine(stack):
    quarantine_by_correlated_attack(stack)
    start(stack)
    report(stack, tamper=True)                     # persistent physical fault, authenticated
    r = rec(stack)
    assert r["status"] == "failed" and "fault_reported" in r["failure_reason"]
    assert state(stack) == "QUARANTINED"


def test_twin_mismatch_during_health_checks_fails_recovery(stack):
    quarantine_by_correlated_attack(stack)
    start(stack)
    report(stack)
    report(stack)                                  # ack
    report(stack, cfg_hash="cfg-evil")             # remediation did not stick
    assert rec(stack)["status"] == "failed" and state(stack) == "QUARANTINED"


def test_insufficient_evidence_holds_then_deadline_fails(stack):
    quarantine_by_correlated_attack(stack)
    start(stack)
    stack.clock.advance(300)
    r = rec(stack)
    assert r["status"] == "active" and r["stage"] == "remediation_pending" and state(stack) == "RECOVERING"
    stack.clock.advance(700)                       # past the 900 s deadline, device still silent
    r = rec(stack)
    assert r["status"] == "failed" and r["failure_reason"] == "deadline_exceeded_before_verification"
    assert state(stack) == "QUARANTINED"


def test_unacknowledged_remediation_never_verifies(stack):
    quarantine_by_correlated_attack(stack)
    start(stack)
    stack.agent.pending_ack = None
    for _ in range(6):
        stack.clock.advance(STEP)
        stack.agent.pending_ack = None             # device ignores the command
        assert stack.agent.recovery_report().status_code == 200
        stack.agent.pending_ack = None
    assert rec(stack)["stage"] == "remediation_pending" and state(stack) == "RECOVERING"


def test_revocation_during_recovery_fails(stack):
    quarantine_by_correlated_attack(stack)
    start(stack)
    stack.store.revoke_device("DEVICE-001")
    r = rec(stack)
    assert r["status"] == "failed" and r["failure_reason"] == "credential_revoked" and state(stack) == "QUARANTINED"


def test_abort_and_restart(stack):
    quarantine_by_correlated_attack(stack)
    start(stack)
    a = stack.op.post("/api/v1/devices/DEVICE-001/recovery/abort", json={"reason": "operator abort"})
    assert a.status_code == 200 and state(stack) == "QUARANTINED"
    assert stack.op.post("/api/v1/devices/DEVICE-001/recovery/start", json={"reason": "second try"}).status_code == 200
    assert len(stack.op.get("/api/v1/devices/DEVICE-001/recovery").json()["history"]) == 2


def test_verified_is_not_trusted_until_score_rebuilt(stack):
    quarantine_by_correlated_attack(stack)
    reach_verified(stack)
    assert stack.trust.score_of("DEVICE-001") < 50 and state(stack) == "VERIFIED"
