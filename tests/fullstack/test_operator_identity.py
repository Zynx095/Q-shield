"""Phase 13: per-operator identity, roles, lifecycle and attribution of every operator action."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config import Settings
from tests.conftest import INGEST_TOKEN, OPERATOR_TOKEN
from tests.fullstack.conftest import EXPECTED, quarantine_by_correlated_attack, state

DEV = "/api/v1/devices/DEVICE-001"
REASON = {"reason": "confirmed anomaly, remediating"}


def mk(s, oid, role="operator", **kw):
    r = s.op.post("/api/v1/operators", json={"operator_id": oid, "display_name": oid.title(), "role": role, **kw})
    assert r.status_code == 200, r.text
    return TestClient(s.app, headers={"Authorization": f"Bearer {r.json()['token']}"}), r.json()["token"]


def actions(s, **match):
    out = [e for e in s.store.list_events(1000) if e["event_type"] == "operator_action"]
    return [e for e in out if all(e["details"].get(k) == v for k, v in match.items())]


# ------------------------------------------------------------------ authentication
def test_named_operator_authenticates_and_sees_its_identity(stack):
    alice, _ = mk(stack, "alice")
    me = alice.get("/api/v1/operators/me").json()
    assert me == {"operator_id": "alice", "display_name": "Alice", "role": "operator", "status": "active",
                  "expires_at": None, "bootstrap": False}
    assert stack.op.get("/api/v1/operators/me").json()["operator_id"] == "bootstrap-admin"


@pytest.mark.parametrize("hdr", [None, "Bearer qso_" + "A" * 43, f"Bearer {INGEST_TOKEN}", "Bearer ", "Token x"])
def test_bad_credentials_rejected(stack, hdr):
    c = TestClient(stack.app, headers={"Authorization": hdr} if hdr else {})
    assert c.get("/api/v1/operators/me").status_code == 401
    assert c.post(f"{DEV}/recovery/start", json=REASON).status_code == 401


def test_device_secret_is_not_an_operator_credential(stack):
    c = TestClient(stack.app, headers={"Authorization": f"Bearer {stack.secret.hex()}"})
    assert c.get("/api/v1/devices").status_code == 401


def test_operator_token_is_not_an_ingest_credential(stack):
    _, tok = mk(stack, "alice", "admin")
    c = TestClient(stack.app, headers={"Authorization": f"Bearer {tok}"})
    assert c.post("/api/v1/observations", json={}).status_code == 401
    assert TestClient(stack.app, headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"}).post(
        "/api/v1/observations", json={}).status_code == 401


def test_revoked_operator_rejected_immediately(stack):
    alice, _ = mk(stack, "alice")
    assert alice.get("/api/v1/devices").status_code == 200
    assert stack.op.post("/api/v1/operators/alice/revoke", json={"reason": "left the team"}).status_code == 200
    assert alice.get("/api/v1/devices").status_code == 401
    assert stack.op.post("/api/v1/operators/alice/revoke", json={"reason": "again"}).status_code == 409
    assert actions(stack, action="REVOKE_OPERATOR", target_operator="alice", result="success")


def test_expired_operator_rejected(stack):
    bob, _ = mk(stack, "bob", ttl_s=60)
    assert bob.get("/api/v1/devices").status_code == 200
    stack.clock.advance(61)
    assert bob.get("/api/v1/devices").status_code == 401


def test_shared_token_can_be_disabled(stack):
    app = create_app(Settings(db_path=":memory:", allow_shared_operator_token=False), clock=stack.clock,
                     store=stack.store, creds=object(), operator_token=OPERATOR_TOKEN, ingest_token=INGEST_TOKEN)
    assert TestClient(app, headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"}).get("/api/v1/devices").status_code == 401
    _, tok = mk(stack, "carol")                       # same DB: named operators keep working
    assert TestClient(app, headers={"Authorization": f"Bearer {tok}"}).get("/api/v1/devices").status_code == 200


# ------------------------------------------------------------------ authorization
def test_viewer_can_read_but_not_act(stack):
    quarantine_by_correlated_attack(stack)
    v, _ = mk(stack, "viewer1", "viewer")
    assert v.get(f"{DEV}/recovery").status_code == 200
    for m, p, b in [("post", f"{DEV}/recovery/start", REASON), ("post", f"{DEV}/recovery/abort", REASON),
                    ("put", f"{DEV}/twin/expected", EXPECTED), ("post", f"{DEV}/quarantine", REASON),
                    ("post", "/api/v1/operators", {"operator_id": "x1", "display_name": "x", "role": "admin"})]:
        assert getattr(v, m)(p, json=b).status_code == 403
    assert state(stack) == "QUARANTINED"
    assert any(e["event_type"] == "operator_forbidden" and e["details"]["operator_id"] == "viewer1"
               for e in stack.store.list_events(500))


def test_operator_cannot_manage_operators_or_escalate(stack):
    alice, _ = mk(stack, "alice")
    assert alice.post("/api/v1/operators", json={"operator_id": "evil", "display_name": "E", "role": "admin"}).status_code == 403
    assert alice.get("/api/v1/operators").status_code == 403
    assert alice.post("/api/v1/operators/alice/revoke", json=REASON).status_code == 403
    assert stack.app.state.operators.get("evil") is None


def test_reserved_and_invalid_operator_ids_refused(stack):
    for body in [{"operator_id": "bootstrap-admin", "display_name": "x", "role": "admin"},
                 {"operator_id": "a b", "display_name": "x", "role": "operator"},
                 {"operator_id": "ok1", "display_name": "x", "role": "root"},
                 {"operator_id": "ok2", "display_name": "x", "role": "viewer", "token": "chosen"}]:
        assert stack.op.post("/api/v1/operators", json=body).status_code in (409, 422)
    mk(stack, "dup")
    assert stack.op.post("/api/v1/operators", json={"operator_id": "dup", "display_name": "d", "role": "viewer"}).status_code == 409


# ------------------------------------------------------------------ attribution
def test_actions_by_two_operators_are_attributed_to_each(stack):
    quarantine_by_correlated_attack(stack)
    alice, _ = mk(stack, "alice")
    bob, _ = mk(stack, "bob")
    r = alice.post(f"{DEV}/recovery/start", json=REASON)
    assert r.status_code == 200 and r.json()["requested_by"] == "alice" and state(stack) == "RECOVERING"
    r = bob.post(f"{DEV}/recovery/abort", json={"reason": "second opinion: not clean"})
    assert r.status_code == 200 and r.json()["failure_reason"].endswith("(by bob)") and state(stack) == "QUARANTINED"
    assert bob.put(f"{DEV}/twin/expected", json={**EXPECTED, "cfg_hash": "cfg-good-2"}).status_code == 200
    (a,) = actions(stack, action="START_RECOVERY", result="success")
    assert a["details"]["operator_id"] == "alice" and a["device_id"] == "DEVICE-001"
    assert a["details"]["reason"] == REASON["reason"]
    (b,) = actions(stack, action="ABORT_RECOVERY", result="success")
    assert b["details"]["operator_id"] == "bob"
    (c,) = actions(stack, action="SET_EXPECTED_STATE", result="success", operator_id="bob")   # setup used bootstrap
    assert c["details"]["operator_id"] == "bob"
    ev = [e for e in stack.op.get("/api/v1/evidence/device/DEVICE-001").json() if e["event_type"] == "operator_action"]
    pl = [e["payload"] if isinstance(e["payload"], dict) else json.loads(e["payload"]) for e in ev]
    assert {(p["operator_id"], p["action"]) for p in pl} >= {
        ("alice", "START_RECOVERY"), ("bob", "ABORT_RECOVERY"), ("bob", "SET_EXPECTED_STATE")}
    assert stack.op.get("/api/v1/evidence/verify").json()["ok"]


def test_refused_actions_are_attributed_too(stack):
    quarantine_by_correlated_attack(stack)
    alice, _ = mk(stack, "alice")
    assert alice.post(f"{DEV}/recovery/abort", json=REASON).status_code == 409
    (e,) = actions(stack, action="ABORT_RECOVERY")
    assert e["details"]["operator_id"] == "alice" and e["details"]["result"] == "refused"
    assert "no_active_recovery" in e["details"]["error"]


@pytest.mark.parametrize("extra", [{"operator_id": "mallory"}, {"requested_by": "mallory"}, {"actor": "mallory"}])
def test_identity_cannot_be_spoofed_from_the_body(stack, extra):
    quarantine_by_correlated_attack(stack)
    alice, _ = mk(stack, "alice")
    assert alice.post(f"{DEV}/recovery/start", json={**REASON, **extra}).status_code == 422
    assert alice.put(f"{DEV}/twin/expected", json={**EXPECTED, **extra}).status_code == 422
    assert not actions(stack, operator_id="mallory")
    assert alice.post(f"{DEV}/recovery/start", json=REASON).json()["requested_by"] == "alice"


def test_using_another_operators_token_acts_as_that_operator_only(stack):
    """A bearer token IS the identity: whoever holds bob's token is bob (documented; mitigated by TLS + revocation)."""
    quarantine_by_correlated_attack(stack)
    _, bob_tok = mk(stack, "bob")
    thief = TestClient(stack.app, headers={"Authorization": f"Bearer {bob_tok}"})
    thief.post(f"{DEV}/recovery/start", json=REASON)
    assert actions(stack, action="START_RECOVERY")[0]["details"]["operator_id"] == "bob"
    stack.op.post("/api/v1/operators/bob/revoke", json={"reason": "token leaked"})
    assert thief.post(f"{DEV}/recovery/abort", json=REASON).status_code == 401


# ------------------------------------------------------------------ token secrecy
def test_tokens_are_stored_hashed_and_never_returned_again(stack):
    _, tok = mk(stack, "alice", "admin")
    rows = stack.store.query("SELECT * FROM operators")
    assert all(tok not in str(dict(r)) for r in rows) and len(rows[0]["token_hash"]) == 64
    listing = stack.op.get("/api/v1/operators").json()
    assert "token" not in str(listing) and "token_hash" not in str(listing)
    assert tok not in str(stack.store.list_events(1000))
    assert tok not in str(stack.op.get("/api/v1/evidence").json())
    assert "token" not in stack.op.get("/api/v1/operators/me").json()


def test_recovery_and_timer_still_work_with_named_operator(stack):
    from backend.recovery.orchestrator import RecoveryTimer
    quarantine_by_correlated_attack(stack)
    alice, _ = mk(stack, "alice")
    assert alice.post(f"{DEV}/recovery/start", json=REASON).status_code == 200
    stack.clock.advance(1000)
    RecoveryTimer(stack.recovery, 1.0).run_once()
    assert stack.recovery.latest("DEVICE-001")["failure_reason"] == "deadline_exceeded_before_verification"
    assert state(stack) == "QUARANTINED"
