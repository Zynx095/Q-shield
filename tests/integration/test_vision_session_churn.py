"""The vision client must not churn ML-KEM sessions: persistent rejections cannot exhaust the gateway's session table.

Real gateway app (in-process) where it matters; a scripted fake gateway for the pathological cases."""
from datetime import timedelta

from ai.vision.signed_sink import SignedHttpSink
from tests.pqc_helpers import make_obs, now_dt


class Mono:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def real_sink(client, world, clock, mono, **kw):
    return SignedHttpSink("http://test", world.backend, "vision-1", "usb_webcam:0", world.signers["vision-1"],
                          secure=True, gateway_key_id="gateway-kem-1", gateway_public_key=world.kem_rec.public_key,
                          client=client, now=kw.pop("now", lambda: now_dt(clock)), monotonic=mono, **kw)


def test_rejected_observations_do_not_open_new_sessions(pqc_client, pqc_operator, pqc_world, clock):
    """Every observation is refused (the signer is not authorised for DEVICE-002). Before, each 401 dropped the session
    and the next observation opened a new one: 30 refusals, 30 sessions. Now: one session, 30 counted rejections."""
    mono = Mono()
    s = real_sink(pqc_client, pqc_world, clock, mono)
    for _ in range(30):
        mono.t += 0.2
        s.emit(make_obs(clock, device_id="DEVICE-002"))
    assert len(pqc_world.gateway._sessions) == 1
    st = s.status()
    assert st["sessions_established"] == 1 and st["rejected"] == 30 and st["delivered"] == 0 and st["queued"] == 0
    assert st["last_error"] == "gateway refused an observation (HTTP 401 authentication_failed)"
    assert pqc_operator.get("/api/v1/observations").json() == []
    s.emit(make_obs(clock))                                          # an authorised observation still goes through
    assert s.status()["delivered"] == 1 and len(pqc_world.gateway._sessions) == 1


def test_skewed_clock_backs_off_instead_of_hammering_the_handshake(pqc_client, pqc_world, clock):
    """The vision host's clock is 10 minutes fast: the gateway refuses the handshake itself. The client backs off."""
    mono = Mono()
    s = real_sink(pqc_client, pqc_world, clock, mono, now=lambda: now_dt(clock) + timedelta(minutes=10))
    for _ in range(150):                                             # 30 s of frames at 5 fps
        mono.t += 0.2
        s.emit(make_obs(clock))
    st = s.status()
    assert st["handshakes_last_hour"] <= 5 and st["sessions_established"] == 0      # 1, 2, 4, 8, 16 s backoff
    assert st["last_error"] == "session establishment rejected (HTTP 401)" and st["queued"] == 150
    assert len(pqc_world.gateway._sessions) == 0


def test_expired_session_is_replaced_once_and_the_observation_still_arrives(pqc_client, pqc_operator, pqc_world, clock):
    mono = Mono()
    s = real_sink(pqc_client, pqc_world, clock, mono)
    s.emit(make_obs(clock))
    pqc_world.gateway._sessions.clear()                              # gateway restarted / session expired
    s.emit(make_obs(clock))
    assert s.status()["sessions_established"] == 2 and s.status()["delivered"] == 2
    assert len(pqc_operator.get("/api/v1/observations").json()) == 2


class Resp:
    def __init__(self, code, detail=None, body=None):
        self.status_code, self._body = code, body if body is not None else ({"detail": detail} if detail else {})

    def json(self):
        return self._body


class ScriptedGateway:
    """Answers handshakes and observation posts from scripts; records every call."""

    def __init__(self, handshake, observe):
        self.handshake, self.observe, self.calls = handshake, observe, []

    def post(self, path, json=None):
        self.calls.append(path)
        return self.handshake(json) if path.endswith("/pqc/session") else self.observe(json)


def sink_for(gw, world, clock, mono, **kw):
    return SignedHttpSink("http://test", world.backend, "vision-1", "usb_webcam:0", world.signers["vision-1"],
                          secure=True, gateway_key_id="gateway-kem-1", gateway_public_key=world.kem_rec.public_key,
                          client=gw, now=lambda: now_dt(clock), monotonic=mono, **kw)


def real_handshake(world):
    from backend.security.session import HandshakeInit
    return lambda init: Resp(200, body=world.gateway.establish_session(HandshakeInit(**init)).model_dump())


def test_failed_handshakes_back_off_exponentially(pqc_world, clock):
    mono = Mono()
    gw = ScriptedGateway(lambda init: Resp(401, "authentication_failed"), lambda env: Resp(200))
    s = sink_for(gw, pqc_world, clock, mono)
    s.emit(make_obs(clock))
    assert gw.calls.count("/api/v1/pqc/session") == 1
    for _ in range(20):                                              # 20 frames inside the 1 s backoff: no traffic
        mono.t += 0.04
        s.emit(make_obs(clock))
    assert gw.calls.count("/api/v1/pqc/session") == 1 and s.status()["queued"] == 21
    mono.t += 1.0
    s.emit(make_obs(clock))                                          # retry after 1 s, fails, now 2 s
    assert gw.calls.count("/api/v1/pqc/session") == 2 and 1.9 < s.status()["backoff_remaining_s"] <= 2.0
    for _ in range(10):                                              # keeps doubling, never above 60 s
        mono.t += 61
        s.emit(make_obs(clock))
    assert s.status()["backoff_remaining_s"] <= 60.0


def test_handshake_budget_caps_sessions_even_in_a_pathological_loop(pqc_world, clock):
    """A gateway that says 'session_expired' to every message: the client stops at its hourly handshake budget."""
    mono = Mono()
    gw = ScriptedGateway(real_handshake(pqc_world), lambda env: Resp(401, "session_expired"))
    s = sink_for(gw, pqc_world, clock, mono, session_budget=5)
    for _ in range(200):
        mono.t += 2.0
        s.emit(make_obs(clock))
    assert gw.calls.count("/api/v1/pqc/session") <= 5
    assert "session budget reached" in s.status()["last_error"]
    assert len(pqc_world.gateway._sessions) <= 5                      # far below the gateway's 64-session cap


def test_normal_path_is_one_handshake_and_no_waiting(pqc_world, clock):
    mono = Mono()
    gw = ScriptedGateway(real_handshake(pqc_world), lambda env: Resp(200))
    s = sink_for(gw, pqc_world, clock, mono)
    for _ in range(25):
        s.emit(make_obs(clock))                                      # same instant: no backoff anywhere
    assert gw.calls.count("/api/v1/pqc/session") == 1 and s.status()["delivered"] == 25
    assert s.status()["consecutive_failures"] == 0 and s.status()["last_error"] is None


def test_unreachable_gateway_queues_bounded_without_handshake_storm(pqc_world, clock):
    mono = Mono()

    class Down:
        calls = 0

        def post(self, *a, **k):
            Down.calls += 1
            raise ConnectionError("down")
    s = sink_for(Down(), pqc_world, clock, mono, max_queue=50)
    for _ in range(500):
        mono.t += 0.2                                                # 100 s of frames at 5 fps
        s.emit(make_obs(clock))
    assert Down.calls <= 12                                          # 1, 2, 4, ... 60 s backoff: a handful of tries
    assert s.status()["queued"] == 50 and s.status()["dropped_queue_full"] == 450
