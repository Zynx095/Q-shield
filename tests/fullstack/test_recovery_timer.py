"""Background recovery-deadline timer: a silent device in RECOVERING times out with NO gateway request."""
import time

import pytest

from backend.recovery.orchestrator import RecoveryTimer
from tests.fullstack.conftest import quarantine_by_correlated_attack
from tests.fullstack.test_recovery import start


def _current(s):
    return s.recovery.store.query("SELECT status, body FROM recoveries ORDER BY started_at DESC LIMIT 1")[0]


def test_timer_fails_silent_recovery_without_any_request(stack):
    quarantine_by_correlated_attack(stack)
    start(stack)
    stack.clock.advance(1000)                      # past the 900 s deadline; no HTTP from here on
    assert _current(stack)["status"] == "active"
    RecoveryTimer(stack.recovery, 1.0).run_once()
    assert _current(stack)["status"] == "failed"
    assert "deadline_exceeded_before_verification" in _current(stack)["body"]
    assert stack.trust.state_of("DEVICE-001").name == "QUARANTINED"


def test_timer_thread_ticks_and_survives_errors():
    calls, errors = [], []

    class Boom:
        class trust:
            @staticmethod
            def process_pending():
                calls.append(1)
                raise RuntimeError("bad tick")

    t = RecoveryTimer(Boom, 0.01, on_error=errors.append)
    t.start()
    deadline = time.time() + 2
    while len(calls) < 3 and time.time() < deadline:
        time.sleep(0.01)
    t.stop()
    assert len(calls) >= 3 and len(errors) >= 3 and not t.running


def test_timer_rejects_non_positive_interval(stack):
    with pytest.raises(ValueError):
        RecoveryTimer(stack.recovery, 0)


def test_gateway_lifecycle_starts_and_stops_timer(stack):
    from fastapi.testclient import TestClient
    timer = stack.app.state.recovery_timer
    assert timer is not None and not timer.running
    with TestClient(stack.app):
        assert timer.running
    assert not timer.running
