"""Phase 6-9 gateway routes: recovery channel (device HMAC), security control channel (operator token),
digital twin and evidence chain. Kept out of app.py so the Phase 1-4 gateway stays readable."""
from __future__ import annotations

from fastapi import Body, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.protocol.envelope import MSG_RECOVERY, Envelope
from backend.recovery.orchestrator import RecoveryError
from backend.security.enforcement import NORMAL, RECOVERY, decide
from backend.trust.model import IllegalTransition, State
from backend.twin.twin import TwinError
from backend.security.operators import ROLES, OperatorError


class RecoveryReport(BaseModel):
    """Recovery-channel report: the same self-reported telemetry fields as normal telemetry, plus the acknowledgement
    of a remediation command. Sensor fields are None when absent (never 0)."""
    model_config = ConfigDict(extra="forbid")
    temperature_c: float | None = None
    humidity_pct: float | None = None
    pressure_hpa: float | None = None
    vibration_g: float | None = None
    rssi_dbm: float | None = None
    tamper: bool
    fw_version: str | None = None
    cfg_hash: str | None = None
    ack_command_id: str | None = Field(default=None, max_length=64)


class ReasonBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=200)


class OperatorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operator_id: str = Field(min_length=2, max_length=64)
    display_name: str = Field(min_length=1, max_length=80)
    role: str = Field(pattern="^(" + "|".join(ROLES) + ")$")
    ttl_s: float | None = Field(default=None, gt=0)


def register_security_routes(app, *, store, clock, require_operator, handle, trust, twin, evidence, recorder, recovery,
                             require_actor=None, require_admin=None, operators=None):
    require_actor = require_actor or require_operator
    require_admin = require_admin or require_operator

    def audit(request: Request, action: str, device_id: str | None, result: str, reason: str | None = None, **detail):
        """One attributable record per operator action (success AND refusal): security event + evidence entry.
        operator_id comes only from the authenticated identity on request.state, never from the request body."""
        op = request.state.operator
        rec = {"operator_id": op.operator_id, "operator_role": op.role, "bootstrap_identity": op.bootstrap,
               "action": action, "device_id": device_id, "reason": reason, "result": result, **detail}
        now = clock()
        store.add_event(now, device_id, "operator_action", "low" if result == "success" else "medium", rec)
        if recorder is not None:
            recorder.record("operator_action", rec, ts=now, device_id=device_id, source=f"operator:{op.operator_id}")

    def attempt(request: Request, action: str, device_id: str | None, reason: str | None, status: int, fn, **detail):
        try:
            out = fn()
        except (RecoveryError, IllegalTransition, TwinError, OperatorError) as e:
            audit(request, action, device_id, "refused", reason, error=str(e), **detail)
            raise HTTPException(status, str(e)) from None
        except HTTPException as e:
            audit(request, action, device_id, "refused", reason, error=str(e.detail), **detail)
            raise
        audit(request, action, device_id, "success", reason, **detail)
        return out
    def need(obj, name):
        if obj is None:
            raise HTTPException(503, f"{name}_not_configured")
        return obj

    def known(device_id: str):
        if store.get_device(device_id) is None:
            raise HTTPException(404, "not_found")

    # ------------------------------------------------------------------ recovery channel (device HMAC)
    @app.post("/api/v1/recovery/report")
    def recovery_report(env: Envelope):
        _, p, now = handle(env, MSG_RECOVERY, RecoveryReport, channel=RECOVERY)
        data = p.model_dump()
        telemetry = {k: v for k, v in data.items() if k != "ack_command_id"}
        store.add_telemetry(env.device_id, now, env.counter, telemetry)
        store.touch(env.device_id, now, telemetry=data, message_kind="recovery")
        if twin is not None:
            twin.observe(env.device_id, now, telemetry=telemetry)
        cmd = recovery.pending_command(env.device_id) if recovery is not None else None
        return {"status": "accepted", "channel": RECOVERY, "command": cmd}

    # ------------------------------------------------------------------ access view + manual quarantine (control)
    @app.get("/api/v1/devices/{device_id}/access", dependencies=[require_operator])
    def access(device_id: str):
        known(device_id)
        state = need(trust, "trust").state_of(device_id)
        return {"device_id": device_id, "trust_state": state.value if state else None,
                "normal": decide(NORMAL, state).__dict__, "recovery": decide(RECOVERY, state).__dict__}

    @app.post("/api/v1/devices/{device_id}/quarantine", dependencies=[require_actor])
    def quarantine(device_id: str, body: ReasonBody, request: Request):
        known(device_id)
        t = need(trust, "trust")
        op = request.state.operator.operator_id
        changes = attempt(request, "QUARANTINE", device_id, body.reason, 409, lambda: t.request_transition(
            device_id, State.QUARANTINED, f"operator {op}: {body.reason}", "operator-quarantine"))
        return {"device_id": device_id, "state": changes[-1].new_state.value, "operator_id": op}

    # ------------------------------------------------------------------ recovery (control)
    @app.post("/api/v1/devices/{device_id}/recovery/start", dependencies=[require_actor])
    def recovery_start(device_id: str, body: ReasonBody, request: Request):
        known(device_id)
        rc, op = need(recovery, "recovery"), request.state.operator.operator_id
        return attempt(request, "START_RECOVERY", device_id, body.reason, 409,
                       lambda: rc.start(device_id, body.reason, requested_by=op))

    @app.post("/api/v1/devices/{device_id}/recovery/abort", dependencies=[require_actor])
    def recovery_abort(device_id: str, body: ReasonBody, request: Request):
        known(device_id)
        rc, op = need(recovery, "recovery"), request.state.operator.operator_id
        return attempt(request, "ABORT_RECOVERY", device_id, body.reason, 409,
                       lambda: rc.abort(device_id, f"{body.reason} (by {op})"))

    @app.get("/api/v1/devices/{device_id}/recovery", dependencies=[require_operator])
    def recovery_get(device_id: str):
        known(device_id)
        r = need(recovery, "recovery")
        r.tick()
        return {"current": r.latest(device_id), "history": r.history(device_id)}

    # ------------------------------------------------------------------ digital twin (control)
    @app.put("/api/v1/devices/{device_id}/twin/expected", dependencies=[require_actor])
    def twin_set(device_id: str, request: Request, expected: dict = Body(...)):
        known(device_id)
        tw, op = need(twin, "twin"), request.state.operator.operator_id

        def do():
            if recovery is not None and recovery.active(device_id):
                # The known-good state is the yardstick of the running health checks: moving it mid-recovery would
                # let the operator (or a stolen operator token) redefine "clean" for a device being verified.
                raise HTTPException(409, "recovery_active: expected state is frozen until the recovery ends (abort first)")
            if not any(expected.get(k) for k in ("fw_version", "cfg_hash")):
                raise HTTPException(422, "expected state must define fw_version and/or cfg_hash")
            return tw.set_expected(device_id, expected, clock())

        exp = attempt(request, "SET_EXPECTED_STATE", device_id, None, 422, do)
        now = clock()
        store.add_event(now, device_id, "twin_expected_updated", "low", {"expected": exp, "operator_id": op})
        if recorder is not None:
            recorder.record("twin_expected_updated", {"expected": exp, "operator_id": op}, ts=now, device_id=device_id,
                            source=f"operator:{op}")
        return {"device_id": device_id, "expected": exp}

    @app.get("/api/v1/devices/{device_id}/twin", dependencies=[require_operator])
    def twin_get(device_id: str):
        known(device_id)
        t = need(twin, "twin")
        return {"expected": t.expected(device_id), "observed": t.observed(device_id),
                "comparison": t.compare(device_id).to_dict()}

    # ------------------------------------------------------------------ operator identity / management
    @app.get("/api/v1/operators/me", dependencies=[require_operator])
    def operator_me(request: Request):
        return request.state.operator.public()

    @app.get("/api/v1/operators", dependencies=[require_admin])
    def operator_list():
        return need(operators, "operators").list()

    @app.post("/api/v1/operators", dependencies=[require_admin])
    def operator_create(body: OperatorCreate, request: Request):
        ops = need(operators, "operators")
        op, token = attempt(request, "CREATE_OPERATOR", None, None, 409, lambda: ops.create(
            body.operator_id, body.display_name, body.role, clock(), created_by=request.state.operator.operator_id,
            ttl_s=body.ttl_s), target_operator=body.operator_id, target_role=body.role)
        # The only time the token is ever returned: it is stored as a hash only and never audited.
        return {**op.public(), "token": token}

    @app.post("/api/v1/operators/{operator_id}/revoke", dependencies=[require_admin])
    def operator_revoke(operator_id: str, body: ReasonBody, request: Request):
        ops = need(operators, "operators")
        return attempt(request, "REVOKE_OPERATOR", None, body.reason, 409, lambda: ops.revoke(
            operator_id, clock(), by=request.state.operator.operator_id), target_operator=operator_id).public()

    # ------------------------------------------------------------------ evidence chain (control, read-only)
    @app.get("/api/v1/evidence", dependencies=[require_operator])
    def evidence_list(after_seq: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
        return need(evidence, "evidence").get_events(limit, after_seq)

    @app.get("/api/v1/evidence/verify", dependencies=[require_operator])
    def evidence_verify():
        ev = need(evidence, "evidence")
        return {**ev.verify_chain().to_dict(), "head": ev.head()}

    @app.get("/api/v1/evidence/device/{device_id}", dependencies=[require_operator])
    def evidence_device(device_id: str, limit: int = Query(200, ge=1, le=1000)):
        return need(evidence, "evidence").get_device_timeline(device_id, limit)

    @app.get("/api/v1/evidence/event/{event_id}", dependencies=[require_operator])
    def evidence_event(event_id: str):
        ev = need(evidence, "evidence")
        e = ev.get_event(event_id)
        if e is None:
            raise HTTPException(404, "not_found")
        return {"event": e, "self_consistent": ev.verify_event(e) is None}
