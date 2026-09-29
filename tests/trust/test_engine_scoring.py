"""Phase 4: scoring, authenticity gates, confidence, physical, fusion, bounds, determinism, explainability."""
import json
import math

import pytest

from backend.trust.config import ConfigError, TrustConfig
from backend.trust.engine import TrustEngine
from backend.trust.model import Auth, Kind, SignalRejected, State
from tests.trust.helpers import (
    T0, engine, evidence, healthy, integrity, run, score, sensor, sig, tamper, unauth, visual,
)


def check_exact(changes):
    """Every change's reasons must sum to its exact delta (explainability invariant)."""
    for c in changes:
        assert abs(sum(r.impact for r in c.reasons) - (c.new_exact - c.previous_exact)) < 1e-6, c.to_dict()


# ---------------------------------------------------------------- baseline
def test_no_evidence_is_not_a_score():
    e = engine()
    assert e.snapshot("D1", T0) == {"device_id": "D1", "status": "NO_EVIDENCE"}


def test_healthy_device_scores_100_trusted():
    e = engine()
    healthy(e)
    s = e.snapshot("D1", T0 + 10)
    assert s["score"] == 100 and s["state"] == "TRUSTED"
    assert "visual" in s["unavailable"] and "config_integrity" in s["unavailable"] and "sensor_consistency" in s["unavailable"]
    assert 0 < s["coverage"] < 1


def test_first_change_is_created_at_100_and_serialisable():
    e = engine()
    _, out = run(e, evidence(T0))
    assert out[0].kind == "created" and out[0].new_score == 100 and out[0].new_state is State.TRUSTED
    json.dumps(out[0].to_dict())


def test_valid_signatures_do_not_raise_score_above_100_or_change_it():
    e = engine()
    healthy(e)
    for i in range(50):
        e.apply(evidence(T0 + 30 + i))
        e.apply(visual(T0 + 30 + i, 0.9).__class__(f"clear{i}", "D1", Kind.VISUAL_CLEAR, T0 + 30 + i, Auth.SIGNER_MLDSA, confidence=0.99))
    assert score(e, T0 + 80) == 100


# ---------------------------------------------------------------- confidence / visual
def test_confidence_scales_magnitude():
    lo, hi = engine(), engine()
    healthy(lo), healthy(hi)
    lo.apply(visual(T0 + 20, 0.51))
    hi.apply(visual(T0 + 20, 0.99))
    s_lo, s_hi = lo.snapshot("D1", T0 + 20), hi.snapshot("D1", T0 + 20)
    assert s_lo["score"] > s_hi["score"]
    assert s_lo["factors"]["visual"]["penalty"] == pytest.approx(100 * 0.51 ** 2)
    assert s_hi["factors"]["visual"]["penalty"] == pytest.approx(100 * 0.99 ** 2)


def test_below_confidence_floor_has_no_impact_but_is_noted():
    e = engine()
    healthy(e)
    before = score(e, T0 + 20)
    e.apply(visual(T0 + 20, 0.29))
    assert score(e, T0 + 20) == before
    assert any(d["reason"] == "below_confidence_floor_no_impact" for d in e.pop_diagnostics())


def test_token_only_visual_is_halved_and_never_correlates():
    a, b = engine(), engine()
    healthy(a), healthy(b)
    a.apply(visual(T0 + 20, 0.9, auth=Auth.SIGNER_MLDSA))
    b.apply(visual(T0 + 20, 0.9, auth=Auth.TOKEN_ONLY))
    assert b.snapshot("D1", T0 + 20)["factors"]["visual"]["penalty"] == pytest.approx(
        0.5 * a.snapshot("D1", T0 + 20)["factors"]["visual"]["penalty"])
    b.apply(tamper(T0 + 21))
    assert b.snapshot("D1", T0 + 21)["incident"] is None       # token-only visual is not a correlation modality


def test_high_confidence_visual_alone_cannot_quarantine():
    e = engine()
    healthy(e)
    for i in range(20):
        e.apply(visual(T0 + 20 + i * 100, 1.0, zone=f"z{i}"))
    assert e.snapshot("D1", T0 + 2100)["state"] != "QUARANTINED"


@pytest.mark.parametrize("bad", [-0.1, 1.01, float("nan"), float("inf"), "0.9", True])
def test_confidence_outside_unit_interval_rejected(bad):
    e = engine()
    healthy(e)
    with pytest.raises(SignalRejected):
        e.apply(visual(T0 + 20, bad))
    assert score(e, T0 + 20) == 100


def test_visual_rule_violation_without_confidence_rejected():
    e = engine()
    with pytest.raises(SignalRejected):
        e.apply(sig(Kind.VISUAL_RULE_VIOLATION, T0, auth=Auth.SIGNER_MLDSA, value={"zone": "z"}))


def test_visual_episode_counts_maximum_once():
    e = engine()
    healthy(e)
    for i, c in enumerate([0.6, 0.6, 0.6, 0.6]):
        e.apply(visual(T0 + 20 + i, c))
    assert e.snapshot("D1", T0 + 24)["factors"]["visual"]["penalty"] == pytest.approx(36.0)
    e.apply(visual(T0 + 25, 0.8))                               # higher in same episode adds only the difference
    assert e.snapshot("D1", T0 + 25)["factors"]["visual"]["penalty"] == pytest.approx(64.0)


# ---------------------------------------------------------------- authenticity boundary
def test_unauthenticated_cannot_emit_evidence_or_level_signals():
    e = engine()
    for k, v in ((Kind.DEVICE_EVIDENCE, {}), (Kind.PHYSICAL_TAMPER, {"active": True}), (Kind.SENSOR_OUT_OF_RANGE, {"active": True}),
                 (Kind.INTEGRITY_MISMATCH, {"mismatch": True})):
        with pytest.raises(SignalRejected):
            e.apply(sig(k, T0, auth=Auth.UNAUTHENTICATED, value=v))
    with pytest.raises(SignalRejected):
        e.apply(sig(Kind.VISUAL_RULE_VIOLATION, T0, auth=Auth.UNAUTHENTICATED, confidence=0.99, value={"zone": "z"}))
    with pytest.raises(SignalRejected):
        e.apply(sig(Kind.DEVICE_EVIDENCE, T0, auth=Auth.SIGNER_MLDSA))      # a signer cannot speak for the device
    with pytest.raises(SignalRejected):
        e.apply(sig(Kind.PHYSICAL_TAMPER, T0, auth=Auth.TOKEN_ONLY, value={"active": True}))


def test_hmac_device_cannot_report_visual_and_signer_cannot_report_tamper():
    e = engine()
    with pytest.raises(SignalRejected):
        e.apply(visual(T0, 0.9, auth=Auth.DEVICE_HMAC))
    with pytest.raises(SignalRejected):
        e.apply(tamper(T0, auth=Auth.SIGNER_MLDSA))


def test_confidence_cannot_override_authenticity():
    e = engine()
    healthy(e)
    with pytest.raises(SignalRejected):
        e.apply(sig(Kind.VISUAL_RULE_VIOLATION, T0 + 20, auth=Auth.UNAUTHENTICATED, confidence=1.0, value={"zone": "z"}))
    assert score(e, T0 + 20) == 100


def test_unknown_device_rejected_fail_closed():
    e = engine()
    with pytest.raises(SignalRejected):
        e.apply(evidence(T0, device="GHOST"))
    assert "GHOST" not in e.devices


@pytest.mark.parametrize("bad_ts", [0, -5, float("nan"), float("inf"), 1e12, "now", None])
def test_bad_timestamps_rejected(bad_ts):
    e = engine()
    with pytest.raises(SignalRejected):
        e.apply(sig(Kind.DEVICE_EVIDENCE, bad_ts))


def test_bad_ids_and_unknown_kind_rejected():
    e = engine()
    from backend.trust.model import Signal
    for bad in ("", None, "x" * 500):
        with pytest.raises(SignalRejected):
            e.apply(Signal(bad, "D1", Kind.DEVICE_EVIDENCE, T0, Auth.DEVICE_HMAC))
    with pytest.raises(SignalRejected):
        e.apply(Signal("k1", "D1", "not_a_kind", T0, Auth.DEVICE_HMAC))
    with pytest.raises(SignalRejected):
        e.apply(Signal("k2", "D1", Kind.DEVICE_EVIDENCE, T0, "root"))
    with pytest.raises(SignalRejected):
        e.apply(Signal("k3", "../etc", Kind.DEVICE_EVIDENCE, T0, Auth.DEVICE_HMAC))


def test_level_signal_without_boolean_rejected():
    e = engine()
    with pytest.raises(SignalRejected):
        e.apply(sig(Kind.PHYSICAL_TAMPER, T0, value={"active": "yes"}))
    with pytest.raises(SignalRejected):
        e.apply(sig(Kind.PHYSICAL_TAMPER, T0, value={}))


# ---------------------------------------------------------------- physical / caps
def test_tamper_caps_at_55_and_persists():
    e = engine()
    healthy(e)
    _, out = run(e, tamper(T0 + 20))
    check_exact(out)
    s = e.snapshot("D1", T0 + 20)
    assert s["score"] <= 55 and s["state"] == "SUSPICIOUS"
    assert any(c["name"] == "physical_tamper" for c in s["caps"])
    assert out[-1].reasons[0].signal in ("physical_tamper", "cap:physical_tamper")


def test_tamper_stop_does_not_restore_trust():
    e = engine()
    healthy(e)
    e.apply(tamper(T0 + 20))
    e.apply(tamper(T0 + 25, False))
    e.apply(evidence(T0 + 26))
    assert score(e, T0 + 26) <= 55                                # penalty and hold persist


def test_trust_recovers_only_with_credited_time_and_never_instantly():
    e = engine()
    t = healthy(e)
    e.apply(tamper(t + 5))
    e.apply(tamper(t + 6, False))
    scores = []
    cur = t + 6
    for _ in range(400):                                          # clean, authenticated evidence every 10 s
        cur += 10
        e.apply(evidence(cur))
        e.apply(tamper(cur, False))
        scores.append(score(e, cur))
    assert scores[0] < 80
    assert scores == sorted(scores)                                # monotone recovery
    assert scores[-1] > scores[0]


def test_quarantined_is_sticky_when_score_rises():
    e = engine()
    healthy(e)
    run(e, tamper(T0 + 20), sensor(T0 + 20), integrity(T0 + 20))
    assert e.snapshot("D1", T0 + 20)["state"] == "QUARANTINED"
    cur = T0 + 20
    e.apply(tamper(cur, False)); e.apply(sensor(cur, False)); e.apply(integrity(cur, False))
    for _ in range(600):
        cur += 20
        e.apply(evidence(cur))
    s = e.snapshot("D1", cur)
    assert s["score"] >= 85 and s["state"] == "QUARANTINED"        # only an explicit validated transition may leave


def test_integrity_mismatch_caps_while_active_and_clears_when_reported_ok():
    e = engine()
    healthy(e)
    e.apply(integrity(T0 + 20))
    assert any(c["name"] == "integrity_mismatch" for c in e.snapshot("D1", T0 + 20)["caps"])
    e.apply(integrity(T0 + 21, False))
    assert not any(c["name"] == "integrity_mismatch" for c in e.snapshot("D1", T0 + 21)["caps"])


# ---------------------------------------------------------------- fusion
def test_tamper_plus_signed_visual_is_confirmed_incident_cap_30_without_double_count():
    e = engine()
    healthy(e)
    e.apply(tamper(T0 + 20))
    only_tamper = e.snapshot("D1", T0 + 20)["factors"]
    _, out = run(e, visual(T0 + 25, 0.9))
    s = e.snapshot("D1", T0 + 25)
    assert s["incident"]["class"] == "confirmed_incident" and s["incident"]["modalities"] == ["PHYSICAL", "VISUAL"]
    assert s["score"] <= 30 and s["state"] == "QUARANTINED"
    assert s["factors"]["physical"]["penalty"] == only_tamper["physical"]["penalty"]   # penalised once
    assert any(c.incident and c.incident["id"].startswith("INC-D1") for c in out)
    check_exact(out)


def test_two_non_physical_modalities_are_correlated_cap_55():
    e = engine()
    healthy(e)
    run(e, sensor(T0 + 20), visual(T0 + 30, 0.9))
    s = e.snapshot("D1", T0 + 30)
    assert s["incident"]["class"] == "correlated_incident" and s["score"] <= 55


def test_correlation_window_expires():
    e = engine()
    healthy(e)
    run(e, visual(T0 + 20, 0.9), visual(T0 + 400, 0.9, zone="other"))
    assert e.snapshot("D1", T0 + 400)["incident"] is None


def test_low_confidence_visual_does_not_corroborate():
    e = engine()
    healthy(e)
    run(e, tamper(T0 + 20), visual(T0 + 25, 0.4))
    assert e.snapshot("D1", T0 + 25)["incident"] is None


def test_single_modality_is_not_an_incident():
    e = engine()
    healthy(e)
    run(e, visual(T0 + 20, 0.99), visual(T0 + 21, 0.99, zone="b"))
    assert e.snapshot("D1", T0 + 21)["incident"] is None


# ---------------------------------------------------------------- unauthenticated pressure (anti-griefing)
def test_forgery_flood_is_bounded_and_cannot_quarantine():
    e = engine()
    healthy(e)
    _, out = run(e, *[unauth(Kind.INVALID_TAG, T0 + 20 + i * 0.1) for i in range(500)])
    check_exact(out)
    s = e.snapshot("D1", T0 + 70)
    assert s["pressure"] <= 25 and s["score"] >= 50 and s["state"] != "QUARANTINED"


def test_pressure_decays_only_with_clean_evidence_and_replays_cap():
    e = engine()
    healthy(e)
    run(e, *[unauth(Kind.DEVICE_REPLAY, T0 + 20 + i) for i in range(3)])
    assert any(c["name"] == "repeated_replay" for c in e.snapshot("D1", T0 + 23)["caps"])
    p = e.snapshot("D1", T0 + 23)["pressure"]
    assert e.snapshot("D1", T0 + 300)["pressure"] == p           # wall time alone does not clear it


def test_stale_signed_observation_not_scored():
    e = engine()
    healthy(e)
    before = score(e, T0 + 20)
    e.apply(sig(Kind.STALE_OBSERVATION, T0 + 20, auth=Auth.SIGNER_MLDSA))
    assert score(e, T0 + 20) == before


def test_auth_misbehavior_caps_at_70_but_needs_verified_signature():
    e = engine()
    healthy(e)
    with pytest.raises(SignalRejected):
        e.apply(sig(Kind.AUTH_MISBEHAVIOR, T0 + 20, auth=Auth.UNAUTHENTICATED))
    e.apply(sig(Kind.AUTH_MISBEHAVIOR, T0 + 21, auth=Auth.SIGNER_MLDSA))
    assert score(e, T0 + 21) <= 70


# ---------------------------------------------------------------- revocation / staleness
def test_revocation_forces_zero_and_quarantine():
    e = engine()
    healthy(e)
    _, out = run(e, sig(Kind.DEVICE_REVOKED, T0 + 20, auth=Auth.GATEWAY_LOCAL))
    s = e.snapshot("D1", T0 + 20)
    assert s["score"] == 0 and s["state"] == "QUARANTINED" and s["revoked"]
    check_exact(out)


def test_revocation_cannot_be_asserted_by_network_parties():
    e = engine()
    for a in (Auth.UNAUTHENTICATED, Auth.DEVICE_HMAC, Auth.SIGNER_MLDSA, Auth.TOKEN_ONLY):
        with pytest.raises(SignalRejected):
            e.apply(sig(Kind.DEVICE_REVOKED, T0, auth=a))


def test_silence_reduces_trust_and_caps_below_80():
    e = engine()
    t = healthy(e)
    assert score(e, t + 10) == 100
    assert 79 >= score(e, t + 60)
    assert e.snapshot("D1", t + 60)["state"] in ("SUSPICIOUS", "TRUSTED")
    assert score(e, t + 400) <= 79
    changes = e.evaluate("D1", t + 60)
    assert changes and changes[0].kind == "time_driven" and changes[0].reasons
    check_exact(changes)


def test_fresh_evidence_ends_staleness_but_hysteresis_applies():
    e = engine()
    t = healthy(e)
    e.evaluate("D1", t + 100)
    assert e.snapshot("D1", t + 100)["state"] == "SUSPICIOUS"
    e.apply(evidence(t + 101))
    assert score(e, t + 101) == 100 and e.snapshot("D1", t + 101)["state"] == "TRUSTED"


# ---------------------------------------------------------------- determinism / bounds / duplicates / persistence
def _scenario(e):
    healthy(e)
    seq = [visual(T0 + 20, 0.7, sid="a"), unauth(Kind.INVALID_TAG, T0 + 21, sid="b"), tamper(T0 + 22, sid="c"),
           visual(T0 + 23, 0.95, zone="q", sid="d"), evidence(T0 + 60, sid="e")]
    out = []
    for s in seq:
        out += e.apply(s)
    return [c.to_dict() for c in out]


def test_deterministic_replay_gives_identical_events():
    a, b = engine(), engine()
    assert json.dumps(_scenario(a), sort_keys=True) == json.dumps(_scenario(b), sort_keys=True)


def test_scores_always_within_bounds_and_integers():
    e = engine()
    healthy(e)
    import random
    r = random.Random(7)
    t = T0 + 20
    for i in range(400):
        t += r.uniform(0, 40)
        k = r.choice(["v", "t", "s", "i", "u", "e", "r"])
        try:
            e.apply({"v": lambda: visual(t, r.random(), zone=str(i % 5)), "t": lambda: tamper(t, r.random() < .5),
                     "s": lambda: sensor(t, r.random() < .5), "i": lambda: integrity(t, r.random() < .5),
                     "u": lambda: unauth(r.choice([Kind.INVALID_TAG, Kind.DEVICE_REPLAY, Kind.INVALID_SIGNATURE]), t),
                     "e": lambda: evidence(t), "r": lambda: tamper(t - 100)}[k]())
        except SignalRejected:
            pass
        s = e.snapshot("D1", t)
        assert isinstance(s["score"], int) and 0 <= s["score"] <= 100 and math.isfinite(s["score_exact"])


def test_all_changes_in_random_run_are_exactly_explained():
    e = engine()
    healthy(e)
    import random
    r = random.Random(11)
    t, allc = T0 + 20, []
    for i in range(300):
        t += r.uniform(0, 30)
        s = r.choice([visual(t, r.random(), zone=str(i % 3)), tamper(t, r.random() < .5), sensor(t, r.random() < .5),
                      unauth(Kind.INVALID_TAG, t), evidence(t), integrity(t, r.random() < .5)])
        allc += e.apply(s)
    check_exact(allc)
    assert allc


def test_duplicate_signal_id_ignored_and_counted():
    e = engine()
    healthy(e)
    s = visual(T0 + 20, 0.9, sid="dup")
    e.apply(s)
    sc = score(e, T0 + 20)
    assert e.apply(s) == []
    assert score(e, T0 + 20) == sc and e.devices["D1"].duplicates == 1


def test_out_of_order_signal_processed_at_latest_time_and_never_credits():
    e = engine()
    healthy(e)
    e.apply(tamper(T0 + 100))
    before = e.devices["D1"].credit_clock
    e.apply(evidence(T0 + 50))
    assert e.devices["D1"].credit_clock == before
    assert any(d["reason"].startswith("out_of_order") for d in e.pop_diagnostics())


def test_state_round_trips_through_serialisation():
    e = engine()
    _scenario(e)
    snap = e.snapshot("D1", T0 + 100)
    e2 = TrustEngine()
    e2.import_state(json.loads(json.dumps(e.export_state())))
    assert e2.snapshot("D1", T0 + 100) == snap
    follow = evidence(T0 + 101, sid="after")
    assert [c.to_dict() for c in e.apply(follow)] == [c.to_dict() for c in e2.apply(follow)]


def test_event_model_fields():
    e = engine()
    healthy(e)
    c = e.apply(visual(T0 + 20, 0.8, sid="vv"))[-1].to_dict()
    for k in ("event_id", "device_id", "timestamp", "previous_score", "new_score", "delta", "previous_state", "new_state",
              "trigger_signals", "reasons", "caps_active", "coverage", "unavailable", "kind"):
        assert k in c
    assert c["trigger_signals"] == ["vv"] and c["delta"] == c["new_score"] - c["previous_score"]
    r = c["reasons"][0]
    assert {"signal", "impact"} <= set(r)
    assert r["confidence"] == 0.8 and r["authenticity"] == "SIGNER_MLDSA"


def test_unavailable_signals_are_reported_not_invented():
    e = engine()
    run(e, evidence(T0))
    s = e.snapshot("D1", T0)
    assert s["factors"]["physical"]["available"] is False and s["factors"]["physical"]["penalty"] is None
    assert set(s["unavailable"]) >= {"physical", "sensor_consistency", "config_integrity", "visual"}


# ---------------------------------------------------------------- config / spec consistency
def test_default_config_matches_specification():
    c = TrustConfig()
    assert sum(c.weights.values()) == pytest.approx(1.0)
    assert {f.value: w for f, w in c.weights.items()} == {"identity_crypto": .25, "physical": .20, "config_integrity": .15,
                                                          "sensor_consistency": .15, "visual": .15, "network": .10}
    assert (c.trusted_min, c.quarantine_below, c.trusted_reentry_min) == (80, 50, 85)
    assert {k: v[0] for k, v in c.caps.items()} == {"revoked_device": 0, "confirmed_incident": 30, "physical_tamper": 55,
                                                    "correlated_incident": 55, "repeated_replay": 65, "integrity_mismatch": 65,
                                                    "auth_violation": 70, "stale_device": 79}
    assert c.pressure_cap == 25 and c.confidence_floor == 0.30 and c.token_only_multiplier == 0.5


@pytest.mark.parametrize("kw", [dict(pressure_cap=60.0), dict(confidence_floor=2), dict(trusted_min=40), dict(token_only_multiplier=0)])
def test_invalid_config_rejected(kw):
    with pytest.raises(ConfigError):
        TrustConfig().with_(**kw)


def test_config_file_cannot_change_weights(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"weights": {}}))
    with pytest.raises(ConfigError):
        TrustConfig.load(p)
    p.write_text(json.dumps({"sensor_limits": {"temperature_c": [-10, 60]}, "expected_fw_version": "1"}))
    assert TrustConfig.load(p).sensor_limits["temperature_c"] == (-10, 60)


def test_routine_evidence_emits_no_event_but_later_events_stay_exact():
    e = engine()
    healthy(e)
    run(e, visual(T0 + 20, 0.6))
    quiet = []
    for i in range(1, 30):
        quiet += e.apply(evidence(T0 + 20 + i * 10))
    assert all(c.new_score != c.previous_score or c.new_state != c.previous_state or c.caps_active for c in quiet)
    later = e.apply(tamper(T0 + 400))
    check_exact(later)
    assert later and later[-1].new_score < later[-1].previous_score


def test_time_driven_evaluation_does_not_make_the_next_signal_out_of_order():
    """Phase 11 regression: with a real clock, an evaluation (enforcement check / dashboard poll) can run a few
    microseconds after a message's receipt time but before the message is applied. The message must still earn credit."""
    e = engine()
    healthy(e)
    e.apply(tamper(T0 + 20))
    e.apply(tamper(T0 + 21, False))
    e.apply(evidence(T0 + 30))
    credit = e.devices["D1"].credit_clock
    e.evaluate("D1", T0 + 70.000_5)                   # evaluation slightly AFTER the next record's receipt time
    out = e.apply(evidence(T0 + 70))
    assert e.devices["D1"].credit_clock - credit == pytest.approx(40.0)
    assert not any(d["reason"].startswith("out_of_order") for d in e.pop_diagnostics())
    assert all(c.timestamp >= T0 + 70.000_5 for c in out)       # published time never goes backwards


def test_signal_older_than_an_applied_signal_is_still_out_of_order():
    e = engine()
    healthy(e)
    e.apply(evidence(T0 + 100))
    credit = e.devices["D1"].credit_clock
    e.apply(evidence(T0 + 90))
    assert e.devices["D1"].credit_clock == credit


def test_last_signal_ts_survives_serialisation_and_old_states_load():
    e = engine()
    healthy(e)
    st = e.export_state()
    assert st["D1"]["last_signal_ts"] == e.devices["D1"].last_signal_ts
    del st["D1"]["last_signal_ts"]                              # state saved before this field existed
    e2 = TrustEngine()
    e2.import_state(json.loads(json.dumps(st)))
    assert e2.devices["D1"].last_signal_ts == e2.devices["D1"].last_ts
