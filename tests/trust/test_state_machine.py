"""Phase 4: state machine legality, thresholds, hysteresis, sticky quarantine, explicit transitions."""
import itertools

import pytest

from backend.trust import state_machine as sm
from backend.trust.config import TrustConfig
from backend.trust.model import IllegalTransition, Kind, State
from tests.trust.helpers import T0, engine, evidence, healthy, run, tamper, integrity, sensor, unauth

ALL = list(State)
LEGAL = {(a, b) for a, bs in sm.TRANSITIONS.items() for b in bs}


@pytest.mark.parametrize("a,b", [(a, b) for a, b in itertools.product(ALL, ALL) if a != b])
def test_transition_table_is_exactly_the_specified_graph(a, b):
    assert sm.is_legal(a, b) == ((a, b) in LEGAL)
    if (a, b) not in LEGAL:
        with pytest.raises(IllegalTransition):
            sm.assert_legal(a, b)


def test_documented_paths():
    for a, b in [(State.QUARANTINED, State.RECOVERING), (State.RECOVERING, State.VERIFIED), (State.VERIFIED, State.RECOVERED),
                 (State.RECOVERED, State.TRUSTED)]:
        assert sm.is_legal(a, b)
    assert not sm.is_legal(State.QUARANTINED, State.TRUSTED)          # no shortcut out of quarantine
    assert not sm.is_legal(State.TRUSTED, State.RECOVERED)


@pytest.mark.parametrize("score,expect", [(100, State.TRUSTED), (80, State.TRUSTED), (79, State.SUSPICIOUS), (50, State.SUSPICIOUS),
                                          (49, State.QUARANTINED), (0, State.QUARANTINED)])
def test_thresholds_for_new_device(score, expect):
    assert sm.automatic_state(TrustConfig(), None, score, False) is expect


def test_hysteresis_between_80_and_85():
    c = TrustConfig()
    assert sm.automatic_state(c, State.SUSPICIOUS, 84, False) is State.SUSPICIOUS
    assert sm.automatic_state(c, State.SUSPICIOUS, 85, False) is State.TRUSTED
    assert sm.automatic_state(c, State.TRUSTED, 80, False) is State.TRUSTED
    assert sm.automatic_state(c, State.TRUSTED, 79, False) is State.SUSPICIOUS


def test_quarantine_is_sticky_and_revoked_always_quarantined():
    c = TrustConfig()
    assert sm.automatic_state(c, State.QUARANTINED, 100, False) is State.QUARANTINED
    assert sm.automatic_state(c, State.TRUSTED, 100, True) is State.QUARANTINED


def test_engine_only_emits_legal_transitions():
    import random
    r = random.Random(3)
    e = engine()
    healthy(e)
    t, seen = T0 + 20, []
    for i in range(300):
        t += r.uniform(0, 30)
        s = r.choice([tamper(t, r.random() < .5), sensor(t, r.random() < .5), integrity(t, r.random() < .5), evidence(t),
                      unauth(Kind.INVALID_TAG, t)])
        seen += e.apply(s)
    for c in seen:
        sm.assert_legal(c.previous_state, c.new_state)
    assert any(c.previous_state != c.new_state for c in seen)


def _quarantined():
    e = engine()
    healthy(e)
    run(e, tamper(T0 + 20), sensor(T0 + 20), integrity(T0 + 20))
    assert e.snapshot("D1", T0 + 20)["state"] == "QUARANTINED"
    return e


def test_explicit_transition_requires_reason_evidence_and_legality():
    e = _quarantined()
    with pytest.raises(IllegalTransition):
        e.request_transition("D1", State.TRUSTED, "because", "ev1", T0 + 30)
    with pytest.raises(IllegalTransition):
        e.request_transition("D1", State.RECOVERING, "", "ev1", T0 + 30)
    with pytest.raises(IllegalTransition):
        e.request_transition("D1", State.RECOVERING, "why", "", T0 + 30)
    with pytest.raises(IllegalTransition):
        e.request_transition("D1", "RECOVERING", "why", "ev1", T0 + 30)
    with pytest.raises(IllegalTransition):
        e.request_transition("NOPE", State.RECOVERING, "why", "ev1", T0 + 30)
    assert e.snapshot("D1", T0 + 30)["state"] == "QUARANTINED"      # rejected requests changed nothing
    ch = e.request_transition("D1", State.RECOVERING, "operator started recovery", "ev1", T0 + 30)[-1]
    assert ch.kind == "state_transition_request" and ch.previous_state is State.QUARANTINED and ch.new_state is State.RECOVERING
    assert ch.delta == 0 and ch.reasons[0].detail["evidence_id"] == "ev1"


def test_recovering_holds_while_score_is_still_below_50_without_a_new_fault():
    # Phase 4.1: supersedes the Phase 4 rule "RECOVERING regresses whenever score < 50" (see trust-engine.md section 7.1).
    e = _quarantined()
    e.request_transition("D1", State.RECOVERING, "r", "e1", T0 + 30)
    e.apply(evidence(T0 + 31))
    s = e.snapshot("D1", T0 + 31)
    assert s["score"] < 50 and s["state"] == "RECOVERING"


def test_later_phase_states_hold_while_score_is_healthy():
    e = _quarantined()
    cur = T0 + 20
    e.apply(tamper(cur, False)); e.apply(sensor(cur, False)); e.apply(integrity(cur, False))
    for _ in range(300):
        cur += 20
        e.apply(evidence(cur))
    assert e.snapshot("D1", cur)["score"] >= 85 and e.snapshot("D1", cur)["state"] == "QUARANTINED"
    for i, st in enumerate([State.RECOVERING, State.VERIFIED, State.RECOVERED, State.TRUSTED]):
        e.request_transition("D1", st, "r", f"e{i}", cur + i)
        assert e.snapshot("D1", cur + i)["state"] == st.value
    e.apply(evidence(cur + 10))
    assert e.snapshot("D1", cur + 10)["state"] == "TRUSTED"
