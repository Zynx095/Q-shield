"""Phase 4.1: recovery-state semantics (spec section 7.1). Phase 4 records and validates; Phase 7 will drive these transitions."""
import pytest

from backend.trust.engine import TrustEngine
from backend.trust.model import Auth, IllegalTransition, Kind, State
from tests.trust.helpers import T0, engine, evidence, healthy, integrity, run, sensor, sig, tamper, unauth, visual


def quarantined_engine():
    e = engine()
    healthy(e)
    run(e, tamper(T0 + 20), sensor(T0 + 20), integrity(T0 + 20))
    s = e.snapshot("D1", T0 + 20)
    assert s["state"] == "QUARANTINED" and s["score"] < 50
    return e


def clear_faults(e, t):
    e.apply(tamper(t, False))
    e.apply(sensor(t, False))
    e.apply(integrity(t, False))


def stream(e, t, until_score=None, step=20, limit=3000):
    """Fresh clean authenticated evidence; optionally until the score reaches `until_score`."""
    for _ in range(limit):
        t += step
        e.apply(evidence(t))
        e.apply(tamper(t, False))
        if until_score is not None and e.snapshot("D1", t)["score"] >= until_score:
            return t
    if until_score is not None:
        raise AssertionError("score never reached the target")
    return t


def test_recovering_with_score_below_50_holds_and_still_credits_fresh_evidence():
    e = quarantined_engine()
    e.request_transition("D1", State.RECOVERING, "start", "ev-1", T0 + 30)
    clear_faults(e, T0 + 31)
    s0 = e.snapshot("D1", T0 + 31)["score"]
    t = stream(e, T0 + 31, step=20, limit=20)
    s = e.snapshot("D1", t)
    assert s["state"] == "RECOVERING" and s["score"] < 50 and e.devices["D1"].credit_clock > 0
    assert s["score"] >= s0                                  # fresh evidence can only help


@pytest.mark.parametrize("fault", [
    lambda t: tamper(t), lambda t: sensor(t), lambda t: integrity(t),
    lambda t: visual(t, 0.9), lambda t: sig(Kind.CAMERA_OBSTRUCTED, t, auth=Auth.SIGNER_MLDSA),
    lambda t: sig(Kind.AUTH_MISBEHAVIOR, t, auth=Auth.SIGNER_MLDSA), lambda t: sig(Kind.MALFORMED_PAYLOAD, t)])
@pytest.mark.parametrize("phase", [State.RECOVERING, State.VERIFIED])
def test_remediation_failure_authenticated_fault_returns_to_quarantined(fault, phase):
    e = quarantined_engine()
    e.request_transition("D1", State.RECOVERING, "start", "ev-1", T0 + 30)
    if phase is State.VERIFIED:
        e.request_transition("D1", State.VERIFIED, "checks passed", "ev-2", T0 + 31)
    out = e.apply(fault(T0 + 40))
    assert e.snapshot("D1", T0 + 40)["state"] == "QUARANTINED"
    assert any(c.previous_state is phase and c.new_state is State.QUARANTINED for c in out)
    assert e.devices["D1"].recovery_fault is False           # the flag does not leak into the next attempt


def test_fault_flag_does_not_leak_when_no_recovery_is_running():
    e = engine()
    healthy(e)
    e.apply(tamper(T0 + 20))
    assert e.devices["D1"].recovery_fault is False


def test_unauthenticated_flood_and_token_only_reports_cannot_knock_a_device_out_of_recovery():
    e = quarantined_engine()
    e.request_transition("D1", State.RECOVERING, "start", "ev-1", T0 + 30)
    clear_faults(e, T0 + 31)
    for i in range(50):
        e.apply(unauth(Kind.INVALID_TAG, T0 + 32 + i * 0.1))
    e.apply(visual(T0 + 60, 0.99, auth=Auth.TOKEN_ONLY))
    assert e.snapshot("D1", T0 + 60)["state"] == "RECOVERING"


def test_remediation_success_full_ramp_requires_score_before_recovered_and_trusted():
    e = quarantined_engine()
    e.request_transition("D1", State.RECOVERING, "remediation started", "ev-1", T0 + 30)
    clear_faults(e, T0 + 31)
    e.request_transition("D1", State.VERIFIED, "health checks passed", "ev-2", T0 + 32)
    # verification succeeded but dynamic trust is still below the threshold: RECOVERED is refused, state holds
    assert e.snapshot("D1", T0 + 32)["score"] < 50
    with pytest.raises(IllegalTransition):
        e.request_transition("D1", State.RECOVERED, "ramp done", "ev-3", T0 + 33)
    assert e.snapshot("D1", T0 + 33)["state"] == "VERIFIED"
    t = stream(e, T0 + 33, until_score=50)
    assert e.snapshot("D1", t)["state"] == "VERIFIED"        # holds while the ramp runs
    e.request_transition("D1", State.RECOVERED, "ramp done", "ev-3", t + 1)
    s = e.snapshot("D1", t + 1)
    assert s["state"] == "RECOVERED" and 50 <= s["score"] < 85
    with pytest.raises(IllegalTransition):                   # below the re-entry threshold: not TRUSTED yet
        e.request_transition("D1", State.TRUSTED, "done", "ev-4", t + 2)
    e.request_transition("D1", State.SUSPICIOUS, "partially rebuilt", "ev-4", t + 2)
    assert e.snapshot("D1", t + 2)["state"] == "SUSPICIOUS"
    t = stream(e, t + 2, until_score=85)                      # automatic SUSPICIOUS -> TRUSTED once >= 85
    assert e.snapshot("D1", t)["state"] == "TRUSTED"


def test_recovered_to_trusted_directly_when_score_is_high_enough():
    e = quarantined_engine()
    e.request_transition("D1", State.RECOVERING, "start", "ev-1", T0 + 30)
    clear_faults(e, T0 + 31)
    e.request_transition("D1", State.VERIFIED, "checks", "ev-2", T0 + 32)
    t = stream(e, T0 + 32, until_score=85)
    e.request_transition("D1", State.RECOVERED, "ramp", "ev-3", t + 1)
    e.request_transition("D1", State.TRUSTED, "rebuilt", "ev-4", t + 2)
    assert e.snapshot("D1", t + 2)["state"] == "TRUSTED"


def test_recovered_regresses_to_quarantined_if_score_falls_below_50():
    e = quarantined_engine()
    e.request_transition("D1", State.RECOVERING, "s", "e1", T0 + 30)
    clear_faults(e, T0 + 31)
    e.request_transition("D1", State.VERIFIED, "c", "e2", T0 + 32)
    t = stream(e, T0 + 32, until_score=50)
    e.request_transition("D1", State.RECOVERED, "r", "e3", t + 1)
    run(e, tamper(t + 5), sensor(t + 5), integrity(t + 5))
    assert e.snapshot("D1", t + 5)["state"] == "QUARANTINED"


def test_fresh_evidence_unavailable_state_holds_score_does_not_rise_and_failure_is_explicit():
    e = quarantined_engine()
    e.request_transition("D1", State.RECOVERING, "start", "ev-1", T0 + 30)
    clear_faults(e, T0 + 31)
    credit, before = e.devices["D1"].credit_clock, e.snapshot("D1", T0 + 31)["score_exact"]
    later = e.snapshot("D1", T0 + 100_000)                   # a long silence
    assert later["state"] == "RECOVERING"                    # the engine has no recovery timeout (orchestrator's job)
    assert e.devices["D1"].credit_clock == credit and later["score_exact"] <= before   # nothing credited, never rises
    with pytest.raises(IllegalTransition):
        e.request_transition("D1", State.VERIFIED, "", "", T0 + 100_000)          # checks need a reason + evidence id
    ch = e.request_transition("D1", State.QUARANTINED, "recovery timed out: no fresh authenticated evidence", "timeout-1", T0 + 100_000)[-1]
    assert ch.new_state is State.QUARANTINED and ch.reasons[0].signal == "state_transition_request"


def test_explicit_failed_check_always_allowed_from_every_recovery_state():
    for path in ([State.RECOVERING], [State.RECOVERING, State.VERIFIED]):
        e = quarantined_engine()
        for i, st in enumerate(path):
            e.request_transition("D1", st, "x", f"e{i}", T0 + 30 + i)
        e.request_transition("D1", State.QUARANTINED, "check failed", "chk", T0 + 40)
        assert e.snapshot("D1", T0 + 40)["state"] == "QUARANTINED"


def test_no_shortcuts_out_of_quarantine_or_around_the_ramp():
    e = quarantined_engine()
    for target in (State.TRUSTED, State.SUSPICIOUS, State.VERIFIED, State.RECOVERED):
        with pytest.raises(IllegalTransition):
            e.request_transition("D1", target, "x", "e", T0 + 30)
    e.request_transition("D1", State.RECOVERING, "x", "e", T0 + 30)
    for target in (State.TRUSTED, State.SUSPICIOUS, State.RECOVERED):
        with pytest.raises(IllegalTransition):
            e.request_transition("D1", target, "x", "e", T0 + 31)


def test_revoked_device_cannot_enter_recovery():
    e = engine()
    healthy(e)
    e.apply(sig(Kind.DEVICE_REVOKED, T0 + 20, auth=Auth.GATEWAY_LOCAL))
    with pytest.raises(IllegalTransition):
        e.request_transition("D1", State.RECOVERING, "x", "e", T0 + 30)
    assert e.snapshot("D1", T0 + 30)["state"] == "QUARANTINED"


def test_revocation_during_recovery_returns_to_quarantined():
    e = quarantined_engine()
    e.request_transition("D1", State.RECOVERING, "x", "e", T0 + 30)
    e.apply(sig(Kind.DEVICE_REVOKED, T0 + 40, auth=Auth.GATEWAY_LOCAL))
    assert e.snapshot("D1", T0 + 40)["state"] == "QUARANTINED"


def test_recovery_state_survives_serialisation_including_pending_fault_flag():
    e = quarantined_engine()
    e.request_transition("D1", State.RECOVERING, "x", "e", T0 + 30)
    e2 = TrustEngine()
    e2.import_state(e.export_state())
    assert e2.snapshot("D1", T0 + 31)["state"] == "RECOVERING"
    e2.apply(tamper(T0 + 40))
    assert e2.snapshot("D1", T0 + 40)["state"] == "QUARANTINED"
