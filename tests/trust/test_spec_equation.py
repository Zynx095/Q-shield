"""Phase 4.1: the exact scoring equation, coverage semantics and the worked examples printed in trust-engine.md section 4.7.

The reference function below is written from the specification text only (not from engine code) and is compared with the
engine's published numbers on hand-built and random histories."""
import math
import random

import pytest

from backend.trust.config import TrustConfig
from backend.trust.model import Auth, Kind, SignalRejected
from tests.trust.helpers import (
    T0, engine, evidence, healthy, integrity, run, sensor, sig, tamper, unauth, visual,
)

NOMINAL = TrustConfig().weights          # Factor -> weight
W = {f.value: w for f, w in NOMINAL.items()}


def reference_score(penalties: dict, pressure: float, cap_ceilings: list) -> tuple:
    """Spec section 4.7 steps 3-6. `penalties` maps AVAILABLE factor name -> p_i in [0,100]."""
    total = sum(W[f] for f in penalties)                       # = coverage
    raw = 100.0 - sum(W[f] / total * p for f, p in penalties.items())
    uncapped = min(100.0, max(0.0, raw - pressure))
    final = min([uncapped] + list(cap_ceilings))
    return raw, uncapped, final, int(math.floor(final + 0.5)), total


def all_six(e, t=T0):
    """Make all six factors available and clean."""
    e.apply(evidence(t))
    e.apply(tamper(t, False))
    e.apply(sensor(t, False))
    e.apply(integrity(t, False))
    e.apply(sig(Kind.VISUAL_CLEAR, t, auth=Auth.SIGNER_MLDSA, confidence=0.9))
    return t


# ------------------------------------------------------------------ worked examples (must equal the specification text)
def test_example_A_all_six_available_and_clean():
    e = engine()
    all_six(e)
    s = e.snapshot("D1", T0)
    assert s["coverage"] == pytest.approx(1.0) and s["unavailable"] == []
    assert s["score_exact"] == pytest.approx(100.0) and s["score"] == 100


def test_example_A2_all_six_available_one_signed_violation_c099():
    e = engine()
    all_six(e)
    e.apply(visual(T0 + 1, 0.99))
    s = e.snapshot("D1", T0 + 1)
    assert s["factors"]["visual"]["penalty"] == pytest.approx(98.01)
    assert s["score_exact"] == pytest.approx(100 - 0.15 * 98.01) == pytest.approx(85.2985)
    assert s["score"] == 85 and s["state"] == "TRUSTED"


def test_example_B0_identity_and_network_only_is_100_with_coverage_035():
    e = engine()
    e.apply(evidence(T0))
    s = e.snapshot("D1", T0)
    assert s["coverage"] == pytest.approx(0.35) and s["score"] == 100 and s["state"] == "TRUSTED"
    assert set(s["unavailable"]) == {"physical", "config_integrity", "sensor_consistency", "visual"}


def test_example_B_same_violation_at_partial_coverage_scores_lower():
    e = engine()
    e.apply(evidence(T0))
    e.apply(tamper(T0, False))
    e.apply(visual(T0 + 1, 0.99))                   # identity, network, physical, visual available: W = 0.70
    s = e.snapshot("D1", T0 + 1)
    assert s["coverage"] == pytest.approx(0.70)
    assert s["factors"]["visual"]["effective_weight"] == pytest.approx(0.15 / 0.70)
    assert s["score_exact"] == pytest.approx(100 - (0.15 / 0.70) * 98.01) == pytest.approx(78.9979, abs=1e-4)
    assert s["score"] == 79 and s["state"] == "SUSPICIOUS"      # full coverage (example A2) gives 85 / TRUSTED


def test_example_B2_identity_network_visual_only():
    e = engine()
    e.apply(evidence(T0))
    e.apply(visual(T0 + 1, 0.99))                   # W = 0.50
    s = e.snapshot("D1", T0 + 1)
    assert s["coverage"] == pytest.approx(0.50)
    assert s["score_exact"] == pytest.approx(100 - 0.30 * 98.01) == pytest.approx(70.597)
    assert s["score"] == 71 and s["state"] == "SUSPICIOUS"


def test_example_C1_single_tamper_cap_binds_over_weighted_sum():
    e = engine()
    e.apply(evidence(T0))
    e.apply(tamper(T0 + 1))                         # identity, network, physical: W = 0.55
    s = e.snapshot("D1", T0 + 1)
    assert s["raw"] == pytest.approx(100 - (0.20 / 0.55) * 100) == pytest.approx(63.6364, abs=1e-4)
    assert s["uncapped"] == pytest.approx(s["raw"])
    assert [c["name"] for c in s["caps"]] == ["physical_tamper"]
    assert s["score_exact"] == 55.0 and s["score"] == 55 and s["state"] == "SUSPICIOUS"


def test_example_C2_tamper_plus_signed_violation_plus_forged_tag():
    """Exactly the scenario printed in the specification (example C2)."""
    e = engine()
    e.apply(evidence(T0))
    e.apply(tamper(T0, False))                      # identity, network, physical available
    e.apply(visual(T0 + 10, 0.9))                   # signed rule violation, c = 0.9: p_visual = 81; visual becomes available (W = 0.70)
    e.apply(tamper(T0 + 12))                        # p_physical = 100; tamper + signed visual within 60 s -> confirmed incident
    e.apply(unauth(Kind.INVALID_TAG, T0 + 15))      # forged tag: pressure q = 10 (point 15 s after the last evidence: network p = 0)
    s = e.snapshot("D1", T0 + 15)
    assert s["incident"]["class"] == "confirmed_incident"
    assert s["factors"]["visual"]["penalty"] == pytest.approx(81.0) and s["factors"]["physical"]["penalty"] == 100.0
    assert s["factors"]["network"]["penalty"] == 0.0 and s["pressure"] == 10.0
    assert s["raw"] == pytest.approx(54.0714, abs=1e-4) and s["uncapped"] == pytest.approx(44.0714, abs=1e-4)
    assert sorted((c["name"], c["ceiling"]) for c in s["caps"]) == [("confirmed_incident", 30), ("physical_tamper", 55)]
    assert s["score_exact"] == 30.0 and s["score"] == 30 and s["state"] == "QUARANTINED"


def test_example_C3_hand_computed_c_values():
    """The numbers printed in the specification: p_phys = 100, p_vis = 81 (c = 0.9), q = 10, W = 0.70."""
    raw, uncapped, final, score, cov = reference_score({"identity_crypto": 0, "network": 0, "physical": 100, "visual": 81}, 10, [30, 55])
    assert cov == pytest.approx(0.70)
    assert raw == pytest.approx(54.0714, abs=1e-4) and uncapped == pytest.approx(44.0714, abs=1e-4)
    assert final == 30 and score == 30


def test_example_token_only_halves_the_impact():
    a, b = engine(), engine()
    for e, auth in ((a, Auth.SIGNER_MLDSA), (b, Auth.TOKEN_ONLY)):
        e.apply(evidence(T0))
        e.apply(tamper(T0, False))
        e.apply(visual(T0 + 1, 0.9, auth=auth))
    pa, pb = (x.snapshot("D1", T0 + 1)["factors"]["visual"]["penalty"] for x in (a, b))
    assert pa == pytest.approx(81.0) and pb == pytest.approx(40.5)


def test_example_decay_half_life():
    """A saturated physical penalty falls to 50 after 3600 credited seconds of clean authenticated evidence."""
    e = engine()
    healthy(e)
    e.apply(tamper(T0 + 100))
    e.apply(tamper(T0 + 101, False))
    assert e.snapshot("D1", T0 + 101)["factors"]["physical"]["penalty"] == 100.0
    t = T0 + 101
    credit0 = e.devices["D1"].credit_clock
    for _ in range(80):                              # 80 x 45 credited s = 3600
        t += 45
        e.apply(evidence(t))
    assert e.snapshot("D1", t)["factors"]["physical"]["penalty"] == pytest.approx(50.0, rel=1e-9)
    assert e.devices["D1"].credit_clock - credit0 == pytest.approx(3600.0)


def test_decay_is_applied_on_clean_evidence_not_by_reading_or_wall_clock():
    e = engine()
    healthy(e)
    e.apply(tamper(T0 + 100))
    e.apply(tamper(T0 + 101, False))
    before = e.snapshot("D1", T0 + 101)["factors"]["physical"]["penalty"]
    assert e.snapshot("D1", T0 + 10_000)["factors"]["physical"]["penalty"] == before


# ------------------------------------------------------------------ equation vs independent reference
def _check_snapshot(e, t):
    s = e.snapshot("D1", t)
    pens = {f: v["penalty"] for f, v in s["factors"].items() if v["available"]}
    ref = reference_score(pens, s["pressure"], [c["ceiling"] for c in s["caps"]])
    assert s["raw"] == pytest.approx(ref[0], abs=1e-9)
    assert s["uncapped"] == pytest.approx(ref[1], abs=1e-9)
    assert s["score_exact"] == pytest.approx(ref[2], abs=1e-9)
    assert s["score"] == ref[3] and 0 <= s["score"] <= 100
    assert s["coverage"] == pytest.approx(ref[4], abs=1e-12)
    assert sorted(s["unavailable"]) == sorted(f for f in W if f not in pens)
    for f, v in s["factors"].items():
        assert (v["effective_weight"] is not None) == v["available"]
        if v["available"]:
            assert v["effective_weight"] == pytest.approx(W[f] / ref[4])
    assert sum(v["effective_weight"] for v in s["factors"].values() if v["available"]) == pytest.approx(1.0)


def test_engine_matches_reference_equation_on_random_histories():
    r = random.Random(2024)
    for seed in range(12):
        e = engine()
        e.apply(evidence(T0))
        t = T0
        for i in range(120):
            t += r.uniform(0, 50)
            mk = r.choice([
                lambda: visual(t, r.random(), zone=str(i % 4), auth=r.choice([Auth.SIGNER_MLDSA, Auth.TOKEN_ONLY])),
                lambda: tamper(t, r.random() < .5), lambda: sensor(t, r.random() < .5), lambda: integrity(t, r.random() < .5),
                lambda: unauth(r.choice([Kind.INVALID_TAG, Kind.DEVICE_REPLAY]), t), lambda: evidence(t),
                lambda: sig(Kind.AUTH_MISBEHAVIOR, t, auth=Auth.SIGNER_MLDSA), lambda: sig(Kind.CAMERA_OBSTRUCTED, t, auth=Auth.SIGNER_MLDSA)])
            try:
                e.apply(mk())
            except SignalRejected:
                pass
            _check_snapshot(e, t + r.uniform(0, 30))


# ------------------------------------------------------------------ coverage semantics
def test_coverage_is_reported_and_only_affects_score_through_renormalisation():
    """Same evidence, different coverage: a clean device is 100 either way (coverage never adds or removes points),
    but one factor penalty weighs more when fewer factors are available."""
    low, high = engine(), engine()
    low.apply(evidence(T0)); low.apply(visual(T0 + 1, 0.99))
    all_six(high); high.apply(visual(T0 + 1, 0.99))
    assert low.snapshot("D1", T0 + 1)["coverage"] < high.snapshot("D1", T0 + 1)["coverage"]
    assert low.snapshot("D1", T0 + 1)["score"] < high.snapshot("D1", T0 + 1)["score"]
    clean_low, clean_high = engine(), engine()
    clean_low.apply(evidence(T0)); all_six(clean_high)
    assert clean_low.snapshot("D1", T0)["score"] == clean_high.snapshot("D1", T0)["score"] == 100


def test_low_coverage_can_yield_a_high_score_and_the_record_says_so():
    e = engine()
    e.apply(evidence(T0))
    s = e.snapshot("D1", T0)
    assert s["score"] == 100 and s["coverage"] == pytest.approx(0.35)
    assert "coverage" in s["notes"] and len(s["unavailable"]) == 4


def test_new_factor_becoming_available_is_a_reported_coverage_change_term():
    e = engine()
    e.apply(evidence(T0))
    e.apply(visual(T0 + 1, 0.99))
    e2 = engine()
    e2.apply(evidence(T0)); e2.apply(visual(T0 + 1, 0.99))
    before = e2.snapshot("D1", T0 + 1)["score_exact"]
    out = e2.apply(tamper(T0 + 2, False))
    assert out and any(r.signal == "coverage_change" for r in out[-1].reasons)
    assert abs(sum(r.impact for r in out[-1].reasons) - (out[-1].new_exact - before)) < 1e-9


def test_unavailable_factor_never_contributes_credit():
    e = engine()
    e.apply(evidence(T0))
    e.apply(visual(T0 + 1, 0.99))
    s = e.snapshot("D1", T0 + 1)
    for f in ("physical", "config_integrity", "sensor_consistency"):
        assert s["factors"][f]["penalty"] is None and s["factors"][f]["effective_weight"] is None
    assert s["score_exact"] == pytest.approx(100 - 0.30 * 98.01)     # not 100 - 0.15*98.01 (which would credit missing factors)


def test_weights_sum_to_one_and_score_never_exceeds_100():
    assert sum(W.values()) == pytest.approx(1.0)
    e = engine()
    for i in range(200):
        e.apply(evidence(T0 + i * 10))
        e.apply(sig(Kind.VISUAL_CLEAR, T0 + i * 10, auth=Auth.SIGNER_MLDSA, confidence=1.0))
    assert e.snapshot("D1", T0 + 2000)["score"] == 100


def test_visual_rule_violation_terminology_and_semantics():
    """The signal is a configured-rule match, not an anomaly-detector output."""
    assert Kind.VISUAL_RULE_VIOLATION.value == "visual_rule_violation"
    assert not hasattr(Kind, "VISUAL_ANOMALY")
