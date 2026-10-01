"""Phase 6-9 gateway routes: recovery channel (device HMAC), security control channel (operator token),
digital twin and evidence chain. Kept out of app.py so the Phase 1-4 gateway stays readable."""
from __future__ import annotations

from fastapi import Body, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.protocol.envelope import MSG_RECOVERY, Envelope
from backend.recovery.orchestrator import RecoveryError
from backend.security.enforcement import NORMAL, RECOVERY, decide
from backend.trust.model import IllegalTransition, State
from backend.twin.twin import TwinError


class RecoveryReport(BaseModel):
    """Recovery-channel report: the same self-reported telemetry fields as normal telemetry, plus the acknowledgement
    of a remediation command. Sensor fields are None when absent (never 0)."""
    model_config = ConfigDict(extra="forbid")
    temperature_c: float | None = None
    humidity_pct: float | None = None
    pressure_hpa: float | None = None
    vibration_g: float | None = None
    tamper: bool
    fw_version: str | None = None
    cfg_hash: str | None = None
    ack_command_id: str | None = Field(default=None, max_length=64)


class ReasonBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=200)


def register_security_routes(app, *, store, clock, require_operator, handle, trust, twin, evidence, recorder, recovery):
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

    @app.post("/api/v1/devices/{device_id}/quarantine", dependencies=[require_operator])
    def quarantine(device_id: str, body: ReasonBody):
        known(device_id)
        t = need(trust, "trust")
        try:
            changes = t.request_transition(device_id, State.QUARANTINED, f"operator: {body.reason}", "operator-quarantine")
        except IllegalTransition as e:
            raise HTTPException(409, str(e)) from None
        return {"device_id": device_id, "state": changes[-1].new_state.value}

    # ------------------------------------------------------------------ recovery (control)
    @app.post("/api/v1/devices/{device_id}/recovery/start", dependencies=[require_operator])
    def recovery_start(device_id: str, body: ReasonBody):
        known(device_id)
        try:
            return need(recovery, "recovery").start(device_id, body.reason)
        except RecoveryError as e:
            raise HTTPException(409, str(e)) from None

    @app.post("/api/v1/devices/{device_id}/recovery/abort", dependencies=[require_operator])
    def recovery_abort(device_id: str, body: ReasonBody):
        known(device_id)
        try:
            return need(recovery, "recovery").abort(device_id, body.reason)
        except RecoveryError as e:
            raise HTTPException(409, str(e)) from None

    @app.get("/api/v1/devices/{device_id}/recovery", dependencies=[require_operator])
    def recovery_get(device_id: str):
        known(device_id)
        r = need(recovery, "recovery")
        r.tick()
        return {"current": r.latest(device_id), "history": r.history(device_id)}

    # ------------------------------------------------------------------ digital twin (control)
    @app.put("/api/v1/devices/{device_id}/twin/expected", dependencies=[require_operator])
    def twin_set(device_id: str, expected: dict = Body(...)):
        known(device_id)
        now = clock()
        if recovery is not None and recovery.active(device_id):
            # The known-good state is the yardstick of the running health checks: moving it mid-recovery would let
            # the operator (or a stolen operator token) redefine "clean" for a device that is being verified.
            raise HTTPException(409, "recovery_active: expected state is frozen until the recovery ends (abort first)")
        if not any(expected.get(k) for k in ("fw_version", "cfg_hash")):
            raise HTTPException(422, "expected state must define fw_version and/or cfg_hash")
        try:
            exp = need(twin, "twin").set_expected(device_id, expected, now)
        except TwinError as e:
            raise HTTPException(422, str(e)) from None
        store.add_event(now, device_id, "twin_expected_updated", "low", {"expected": exp})
        if recorder is not None:
            recorder.record("twin_expected_updated", {"expected": exp}, ts=now, device_id=device_id, source="operator")
        return {"device_id": device_id, "expected": exp}

    @app.get("/api/v1/devices/{device_id}/twin", dependencies=[require_operator])
    def twin_get(device_id: str):
        known(device_id)
        t = need(twin, "twin")
        return {"expected": t.expected(device_id), "observed": t.observed(device_id),
                "comparison": t.compare(device_id).to_dict()}

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
