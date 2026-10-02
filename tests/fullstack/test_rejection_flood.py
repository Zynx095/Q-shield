"""Rejected-traffic floods: storage stays bounded, forensic records survive, trust decisions do not change.

backend/security/rejections.py samples routine (unauthenticated) rejections per window, coalesces the rest into a
representative row and prunes old routine rows the trust engine has already consumed. High-value events always pass.
"""
import json
import secrets
from types import SimpleNamespace

from fastapi.testclient import TestClient

from attack_simulation import AttackSimulator, SignerHandle
from backend.api.app import create_app
from backend.config import Settings
from backend.devices.store import Store
from backend.protocol.envelope import AUTH_HMAC, MSG_TELEMETRY, build_hmac_envelope
from backend.security.credentials import EncryptedCredentialStore
from backend.security.pqc_gateway import PqcGateway
from backend.security.rejections import is_routine
from backend.trust.config import TrustConfig
from backend.trust.service import TrustService
from backend.twin.twin import DigitalTwin
from device_agent.agent import DeviceAgent
from tests.conftest import INGEST_TOKEN, MASTER_KEY, OPERATOR_TOKEN, FakeClock
from tests.fullstack.conftest import EXPECTED
from tests.pqc_helpers import signed_env

DEV = "DEVICE-001"


def build(pqc_world_src, pqc_backend, **limits):
    """A gateway with trust + twin over its own store, sharing the session's PQC keys."""
    clock = FakeClock()
    store = Store(":memory:")
    creds = EncryptedCredentialStore(store, MASTER_KEY)
    secret = secrets.token_bytes(32)
    store.enroll_device(DEV, AUTH_HMAC, clock())
    creds.put(DEV, secret)
    for sid in ("vision-1",):
        rec = pqc_world_src.ks.load_public(sid)
        store.add_signer(sid, rec.algorithm, rec.public_key, "usb_webcam", [DEV], clock())
    gw_pqc = PqcGateway.from_keystore(store, pqc_backend, pqc_world_src.ks, MASTER_KEY, ["gateway-kem-1"], clock=clock)
    twin = DigitalTwin(store)
    trust = TrustService(store, TrustConfig(), clock=clock, twin=twin)
    app = create_app(Settings(db_path=":memory:", **limits), clock=clock, store=store, creds=creds,
                     operator_token=OPERATOR_TOKEN, ingest_token=INGEST_TOKEN, pqc=gw_pqc, trust=trust, twin=twin)
    gw, op = TestClient(app), TestClient(app, headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"})
    agent = DeviceAgent(DEV, secret, gw)
    s = SimpleNamespace(store=store, clock=clock, trust=trust, gw=gw, op=op, agent=agent, secret=secret, app=app,
                        sim=AttackSimulator(gw, op, DEV, agent=agent,
                                            signer=SignerHandle(pqc_backend, pqc_world_src.signers["vision-1"], "vision-1"),
                                            clock=clock))
    assert op.put(f"/api/v1/devices/{DEV}/twin/expected", json=EXPECTED).status_code == 200
    agent.cfg_hash = "cfg-good-1"
    assert agent.register().status_code == 200 and agent.telemetry().status_code == 200
    return s


def forged(s, world):
    env = signed_env(world, s.clock)
    body = json.loads(env["payload"])
    body["anomaly"] = False
    env["payload"] = json.dumps(body, sort_keys=True)
    return env


def rows(s, event_type):
    return [e for e in s.store.list_events(10_000) if e["event_type"] == event_type]


def flood(s, world, n, step=0.05):
    env = forged(s, world)
    for _ in range(n):
        s.clock.advance(step)
        assert s.gw.post("/api/v1/observations/signed", json=env).status_code == 401


def test_flood_of_forged_signatures_is_sampled_and_coalesced(pqc_world, pqc_backend):
    s = build(pqc_world, pqc_backend)
    flood(s, pqc_world, 300)                                       # 15 s of flood: two windows
    s.op.get("/api/v1/events?limit=5")                            # an operator read flushes coalesced counts
    stored = rows(s, "pqc_invalid_signature")
    sampled = [e for e in stored if "aggregated" not in e["details"]]
    coalesced = [e for e in stored if "aggregated" in e["details"]]
    assert len(sampled) == 6 and len(coalesced) == 2                # 3 per window + one representative per window
    assert sum(e["details"]["aggregated"] for e in coalesced) + len(sampled) == 300     # nothing is silently lost
    assert all(e["details"]["claimed_signer_id"] == "vision-1" for e in coalesced)     # still attributable
    t = s.op.get(f"/api/v1/trust/{DEV}").json()
    assert t["state"] in ("TRUSTED", "SUSPICIOUS") and t["score"] >= 75 and t["pressure"] <= 25   # bounded, never quarantine


def test_trust_decisions_match_one_row_per_rejection(pqc_world, pqc_backend):
    """The same flood + clean telemetry, with sampling (default) and with sampling effectively off: identical trust."""
    def scenario(s):
        for burst in range(3):
            flood(s, pqc_world, 80, step=0.1)
            s.clock.advance(1.0)
            assert s.agent.telemetry().status_code == 200
            s.clock.advance(5.0)
            assert s.agent.telemetry().status_code == 200
        dt = s.trust.engine.devices[DEV]
        return (dt.state, dt.score, round(dt.score_exact, 9), round(dt.pressure, 9), dt.last_violation_ts,
                round(dt.credit_clock, 9), sorted(dt.holds))
    sampled = build(pqc_world, pqc_backend)
    unsampled = build(pqc_world, pqc_backend, rejection_sample_per_key=10_000, rejection_window_cap=10_000)
    assert scenario(sampled) == scenario(unsampled)
    assert len(rows(sampled, "pqc_invalid_signature")) < len(rows(unsampled, "pqc_invalid_signature")) / 10


def test_repeated_replay_hold_still_triggers_under_sampling(pqc_world, pqc_backend):
    s = build(pqc_world, pqc_backend)
    env = signed_env(pqc_world, s.clock)
    assert s.gw.post("/api/v1/observations/signed", json=env).status_code == 200
    for _ in range(50):
        s.clock.advance(0.02)
        assert s.gw.post("/api/v1/observations/signed", json=env).status_code == 409
    assert "repeated_replay" in [c["name"] for c in s.op.get(f"/api/v1/trust/{DEV}").json()["caps"]]


def test_rotating_fake_identities_are_capped_per_window(pqc_world, pqc_backend):
    s = build(pqc_world, pqc_backend, rejection_window_cap=20)
    for i in range(500):
        s.clock.advance(0.01)
        env = build_hmac_envelope(secrets.token_bytes(32), MSG_TELEMETRY, f"ROGUE-{i:04d}", 1, json.dumps({"tamper": False}))
        assert s.gw.post("/api/v1/telemetry", json=env).status_code == 401
    s.op.get("/api/v1/events?limit=5")
    stored = rows(s, "unknown_device")
    assert len(stored) <= 20 + 1
    rep = [e for e in stored if "aggregated" in e["details"]]
    assert rep and rep[0]["device_id"] is None and len(rep[0]["details"]["claimed_sample"]) == 10
    assert "claimed_device_id" not in rep[0]["details"]           # an unattributed row never names one device
    assert sum(e["details"].get("aggregated", 0) for e in stored) + len([e for e in stored if "aggregated" not in e["details"]]) == 500


def test_high_value_events_are_never_sampled(pqc_world, pqc_backend):
    """A valid signer reporting for a device it is not authorised for is authenticated misbehaviour: every one kept."""
    s = build(pqc_world, pqc_backend)
    s.store.enroll_device("DEVICE-002", AUTH_HMAC, s.clock())
    from tests.pqc_helpers import make_obs
    for _ in range(25):
        s.clock.advance(0.01)
        env = signed_env(pqc_world, s.clock, obs=make_obs(s.clock, device_id="DEVICE-002"))
        assert s.gw.post("/api/v1/observations/signed", json=env).status_code == 401
    assert len(rows(s, "pqc_signer_not_authorised")) == 25
    assert not is_routine("pqc_signer_not_authorised") and not is_routine("malformed_payload")
    assert not is_routine("operator_action") and not is_routine("quarantine_access_blocked")
    assert not is_routine("some_future_event_type"), "unknown types are kept, never sampled"


def test_retention_keeps_storage_bounded_but_never_drops_unconsumed_rows(pqc_world, pqc_backend):
    s = build(pqc_world, pqc_backend, rejection_keep_rows=30)
    for minute in range(10):                                     # a sustained flood over 10 minutes of windows
        flood(s, pqc_world, 60, step=1.0)
        assert s.agent.telemetry().status_code == 200             # the trust engine consumes as it goes
    s.op.get("/api/v1/events?limit=5")
    assert s.store.count_events(routine=True) <= 30 + 12          # keep_rows + at most one window not yet pruned
    assert s.store.count_events(routine=False) >= 1                # high-value rows untouched
    flood(s, pqc_world, 10, step=0.01)                            # a last burst: its coalesced row is flushed by
    s.op.get("/api/v1/events?limit=5")                            # the operator read, after the engine last ran
    cursor = s.store.get_cursor("security_events")
    unconsumed = [e["id"] for e in s.store.list_events(10_000) if e["id"] > cursor]
    assert unconsumed                                              # the flush just wrote rows the engine has not read
    s.store.prune_routine_events(1, consumed_upto=cursor)          # aggressive retention...
    left = {e["id"] for e in s.store.list_events(10_000)}
    assert set(unconsumed) <= left                                 # ...still never deletes what the engine has not read
    assert s.store.count_events(routine=False) >= 1


def test_device_flood_of_forged_tags_keeps_quarantine_semantics(pqc_world, pqc_backend):
    """Unauthenticated device-path floods stay bounded pressure: never quarantine, whatever their volume."""
    s = build(pqc_world, pqc_backend)
    for i in range(400):
        s.clock.advance(0.02)
        env = build_hmac_envelope(secrets.token_bytes(32), MSG_TELEMETRY, DEV, 10**9 + i, json.dumps({"tamper": True}))
        assert s.gw.post("/api/v1/telemetry", json=env).status_code == 401
    t = s.op.get(f"/api/v1/trust/{DEV}").json()
    assert t["state"] != "QUARANTINED" and t["score"] >= 75 and not t["tamper_active"]
    assert len(rows(s, "invalid_tag")) < 20
