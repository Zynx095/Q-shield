"""The camera as part of the security boundary, in the trust engine (spec sections 3, 4.4, 6.3, 7.1 and 9).

Camera interference (obstructed, frozen, view changed) lowers trust on its own but never quarantines on its own;
signed, it is VISUAL modality evidence, so with a tamper report it confirms an incident. Weak evidence (lost source,
degraded image, proximity heuristics, token-only reports) never confirms anything.
"""
import pytest

from backend.trust.config import DEFAULT_WEIGHTS, SEVERITY_POINTS
from backend.trust.model import Auth, Factor, Kind, SignalRejected, State
from tests.trust.helpers import T0, engine, evidence, healthy, run, sensor, sig, tamper, visual

INTERFERENCE = (Kind.CAMERA_OBSTRUCTED, Kind.CAMERA_FROZEN, Kind.CAMERA_VIEW_CHANGED)
WEAK_CAMERA = (Kind.CAMERA_SOURCE_LOST, Kind.CAMERA_DEGRADED)


def cam(kind, t, auth=Auth.SIGNER_MLDSA, **kw):
    return sig(kind, t, auth=auth, **kw)


def near(t, reason="subject_too_close", c=0.9, auth=Auth.SIGNER_MLDSA, **kw):
    return sig(Kind.SUBJECT_PROXIMITY, t, auth=auth, confidence=c, value={"reason": reason, "object": "person"}, **kw)


def visual_weight():
    """Effective visual weight after healthy(): identity, physical, network and visual are available."""
    avail = (Factor.IDENTITY, Factor.PHYSICAL, Factor.NETWORK, Factor.VISUAL)
    return DEFAULT_WEIGHTS[Factor.VISUAL] / sum(DEFAULT_WEIGHTS[f] for f in avail)


def expected(points):
    return int(100 - points * visual_weight() + 0.5)


# ---------------------------------------------------------------- anomaly pressure, alone
@pytest.mark.parametrize("kind,severity", [(Kind.CAMERA_OBSTRUCTED, "HIGH"), (Kind.CAMERA_FROZEN, "HIGH"),
                                           (Kind.CAMERA_VIEW_CHANGED, "HIGH"), (Kind.CAMERA_DEGRADED, "MEDIUM"),
                                           (Kind.CAMERA_SOURCE_LOST, "MEDIUM")])
def test_each_camera_problem_alone_lowers_trust_by_its_severity_and_never_quarantines(kind, severity):
    e = engine()
    t = healthy(e)
    c, _ = run(e, cam(kind, t + 1))
    assert c.new_score == expected(SEVERITY_POINTS[severity])
    assert c.new_state is State.TRUSTED and c.incident is None
    assert any(r.signal == kind.value and r.factor == "visual" for r in c.reasons)


def test_proximity_heuristic_is_low_and_scaled_by_authenticity():
    e = engine()
    t = healthy(e)
    c, _ = run(e, near(t + 1))
    assert c.new_score == expected(SEVERITY_POINTS["LOW"]) and c.new_state is State.TRUSTED
    e2 = engine()
    t2 = healthy(e2)
    c2, _ = run(e2, near(t2 + 1, auth=Auth.TOKEN_ONLY))
    assert c2.new_score == expected(SEVERITY_POINTS["LOW"] * 0.5)


def test_proximity_below_the_confidence_floor_has_no_impact():
    e = engine()
    t = healthy(e)
    before = e.snapshot("D1", t)["score"]
    run(e, near(t + 1, c=0.2))
    assert e.snapshot("D1", t + 1)["score"] == before
    assert any(d["reason"] == "below_confidence_floor_no_impact" for d in e.pop_diagnostics())


def test_every_camera_problem_at_once_still_cannot_quarantine():
    """A compromised vision key (or a camera that is really failing) alone: visual factor saturates, nothing more."""
    e = engine()
    t = healthy(e)
    for i, k in enumerate(INTERFERENCE + WEAK_CAMERA):
        run(e, cam(k, t + 1 + i))
    run(e, near(t + 10), near(t + 11, reason="rapid_approach"), visual(t + 12, 0.99))
    snap = e.snapshot("D1", t + 12)
    assert snap["incident"] is None and snap["state"] != "QUARANTINED"
    assert snap["score"] == expected(100)                        # the visual factor is clamped at 100: 79, SUSPICIOUS
    assert snap["score"] >= 50                                  # with full coverage it would be 85, still TRUSTED


# ---------------------------------------------------------------- correlation
@pytest.mark.parametrize("kind", INTERFERENCE)
def test_tamper_plus_signed_camera_interference_is_a_confirmed_incident(kind):
    e = engine()
    t = healthy(e)
    run(e, cam(kind, t + 1))
    c, _ = run(e, tamper(t + 20))
    assert c.incident["class"] == "confirmed_incident"
    assert c.incident["modalities"] == ["PHYSICAL", "VISUAL"]
    assert c.new_score <= 30 and c.new_state is State.QUARANTINED


def test_camera_interference_after_a_tamper_report_also_confirms():
    e = engine()
    t = healthy(e)
    run(e, tamper(t + 1))
    c, _ = run(e, cam(Kind.CAMERA_VIEW_CHANGED, t + 15))
    assert c.incident["class"] == "confirmed_incident" and c.new_state is State.QUARANTINED


def test_sensor_excursion_plus_camera_interference_is_correlated_not_confirmed():
    e = engine()
    t = healthy(e)
    run(e, sensor(t + 1))
    c, _ = run(e, cam(Kind.CAMERA_FROZEN, t + 5))
    assert c.incident["class"] == "correlated_incident"
    assert c.new_state is State.SUSPICIOUS and c.new_score <= 55


def test_tamper_plus_signed_rule_violation_still_confirms():
    e = engine()
    t = healthy(e)
    run(e, visual(t + 1, 0.9))
    c, _ = run(e, tamper(t + 10))
    assert c.incident["class"] == "confirmed_incident" and c.new_state is State.QUARANTINED


def test_camera_interference_and_a_rule_violation_are_one_modality():
    """The same camera and the same signer cannot corroborate themselves."""
    e = engine()
    t = healthy(e)
    run(e, cam(Kind.CAMERA_OBSTRUCTED, t + 1), visual(t + 2, 0.95), cam(Kind.CAMERA_VIEW_CHANGED, t + 3))
    snap = e.snapshot("D1", t + 3)
    assert snap["incident"] is None and snap["state"] != "QUARANTINED"


@pytest.mark.parametrize("weak", ["token_only", "source_lost", "degraded", "proximity", "low_confidence_rule"])
def test_weak_evidence_plus_tamper_never_confirms(weak):
    e = engine()
    t = healthy(e)
    s = {"token_only": cam(Kind.CAMERA_OBSTRUCTED, t + 1, auth=Auth.TOKEN_ONLY),
         "source_lost": cam(Kind.CAMERA_SOURCE_LOST, t + 1),
         "degraded": cam(Kind.CAMERA_DEGRADED, t + 1),
         "proximity": near(t + 1),
         "low_confidence_rule": visual(t + 1, 0.45)}[weak]
    run(e, s)
    c, _ = run(e, tamper(t + 10))
    assert c.incident is None
    assert c.new_state is State.SUSPICIOUS and c.new_score == 55          # the tamper's own cap, nothing more


def test_interference_outside_the_correlation_window_does_not_correlate():
    e = engine()
    t = healthy(e)
    run(e, tamper(t + 1), tamper(t + 2, False))                          # reported and cleared
    for i in range(1, 8):
        run(e, evidence(t + 2 + 10 * i), tamper(t + 2 + 10 * i, False))
    run(e, cam(Kind.CAMERA_OBSTRUCTED, t + 2 + 61))
    assert e.snapshot("D1", t + 63)["incident"] is None             # the tamper's own cap may still hold; no incident


# ---------------------------------------------------------------- repetition and recovery
def test_repeated_reports_in_one_episode_count_once_and_a_new_episode_counts_again():
    e = engine()
    t = healthy(e)
    c1, _ = run(e, cam(Kind.CAMERA_VIEW_CHANGED, t + 1))
    run(e, cam(Kind.CAMERA_VIEW_CHANGED, t + 6), cam(Kind.CAMERA_VIEW_CHANGED, t + 11))
    assert e.snapshot("D1", t + 11)["score"] == c1.new_score              # same episode: no extra penalty
    run(e, cam(Kind.CAMERA_OK, t + 12))
    c2, _ = run(e, cam(Kind.CAMERA_VIEW_CHANGED, t + 14))                 # moved again after it was restored
    assert c2.new_score < c1.new_score


def test_trust_recovers_after_the_camera_problem_clears():
    e = engine()
    t = healthy(e)
    low, _ = run(e, cam(Kind.CAMERA_OBSTRUCTED, t + 1))
    run(e, cam(Kind.CAMERA_OK, t + 30))
    scores = []
    for i in range(1, 121):                                               # 40 min of clean reports every 20 s
        run(e, evidence(t + 30 + 20 * i), tamper(t + 30 + 20 * i, False))
        scores.append(e.snapshot("D1", t + 30 + 20 * i)["score"])
    assert scores == sorted(scores) and scores[-1] >= 95 > low.new_score
    assert e.snapshot("D1", scores and t + 30 + 20 * 120)["state"] == "TRUSTED"


def test_no_recovery_credit_while_the_camera_keeps_reporting_new_problems():
    """Each new camera episode is a violation: the interval containing it is not credited."""
    e = engine()
    t = healthy(e)
    run(e, cam(Kind.CAMERA_FROZEN, t + 1))
    credit_before = e.devices["D1"].credit_clock
    run(e, cam(Kind.CAMERA_OK, t + 10), cam(Kind.CAMERA_FROZEN, t + 12), evidence(t + 14))
    assert e.devices["D1"].credit_clock - credit_before == pytest.approx(2.0)   # only t+12 -> t+14 credited


# ---------------------------------------------------------------- recovery-state semantics (section 7.1)
def _recovering(e, t):
    run(e, visual(t + 1, 0.9), tamper(t + 2))
    run(e, tamper(t + 3, False))
    e.request_transition("D1", State.RECOVERING, "remediation started", "ev-1", t + 4)
    assert e.devices["D1"].state is State.RECOVERING
    return t + 5


@pytest.mark.parametrize("kind", [Kind.CAMERA_FROZEN, Kind.CAMERA_VIEW_CHANGED, Kind.CAMERA_OBSTRUCTED])
def test_signed_camera_interference_during_recovery_is_a_fault(kind):
    e = engine()
    t = _recovering(e, healthy(e))
    c, _ = run(e, cam(kind, t))
    assert c.new_state is State.QUARANTINED


@pytest.mark.parametrize("make", [lambda t: cam(Kind.CAMERA_DEGRADED, t), lambda t: near(t),
                                  lambda t: cam(Kind.CAMERA_VIEW_CHANGED, t, auth=Auth.TOKEN_ONLY)])
def test_weak_camera_evidence_during_recovery_is_not_a_fault(make):
    e = engine()
    t = _recovering(e, healthy(e))
    run(e, make(t))
    assert e.devices["D1"].state is State.RECOVERING


# ---------------------------------------------------------------- authentication boundary
@pytest.mark.parametrize("kind", [Kind.CAMERA_FROZEN, Kind.CAMERA_VIEW_CHANGED, Kind.CAMERA_DEGRADED])
def test_camera_kinds_cannot_arrive_unauthenticated_or_as_device_reports(kind):
    e = engine()
    t = healthy(e)
    for auth in (Auth.UNAUTHENTICATED, Auth.DEVICE_HMAC, Auth.GATEWAY_LOCAL):
        with pytest.raises(SignalRejected):
            e.apply(cam(kind, t + 1, auth=auth))


def test_proximity_needs_a_confidence():
    e = engine()
    t = healthy(e)
    with pytest.raises(SignalRejected):
        e.apply(sig(Kind.SUBJECT_PROXIMITY, t + 1, auth=Auth.SIGNER_MLDSA, value={"reason": "rapid_approach"}))


def test_adapter_maps_every_camera_state_and_the_proximity_reasons():
    import json

    from backend.trust.adapters import from_observation
    from backend.trust.config import TrustConfig
    from datetime import datetime, timezone

    cfg = TrustConfig()
    iso = datetime.fromtimestamp(T0, timezone.utc).isoformat()

    def row(body):
        return {"body": json.dumps({"device_id": "D1", "observation_id": "o1", "timestamp": iso, **body}),
                "auth": "ML-DSA-65:vision-1", "received_at": T0}
    for state, kind in [("ok", Kind.CAMERA_OK), ("obstructed", Kind.CAMERA_OBSTRUCTED), ("source_lost", Kind.CAMERA_SOURCE_LOST),
                        ("frozen", Kind.CAMERA_FROZEN), ("view_changed", Kind.CAMERA_VIEW_CHANGED), ("degraded", Kind.CAMERA_DEGRADED)]:
        (s,) = from_observation(row({"event_type": "camera_health", "details": {"state": state}}), cfg).signals
        assert s.kind is kind and s.auth is Auth.SIGNER_MLDSA
    for reason in ("subject_too_close", "rapid_approach"):
        (s,) = from_observation(row({"event_type": "visual_observation", "anomaly": True, "anomaly_reason": reason,
                                     "confidence": 0.8, "object": "person"}), cfg).signals
        assert s.kind is Kind.SUBJECT_PROXIMITY and s.value["reason"] == reason
    (s,) = from_observation(row({"event_type": "visual_observation", "anomaly": True, "confidence": 0.8, "object": "person",
                                 "anomaly_reason": "restricted_class_in_restricted_zone", "zone": "z"}), cfg).signals
    assert s.kind is Kind.VISUAL_RULE_VIOLATION
    a = from_observation(row({"event_type": "camera_health", "details": {"state": "melted"}}), cfg)
    assert a.signals == [] and "unknown_camera_state" in a.note                      # fail closed: no score change
