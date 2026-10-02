"""FastAPI gateway application (Phase 1: register, heartbeat, telemetry, read-only device views).

Three separate authentication mechanisms, never interchangeable:
  * devices   : per-device HMAC envelope on register/heartbeat/telemetry
  * operator  : bearer token on read/control APIs (dashboard, humans)
  * ingest    : bearer token for the local vision/observer service posting observations
/health is open. The default bind is LAN-wide so a device can reach the gateway, and bearer
tokens travel in cleartext over HTTP: use only on a trusted network until TLS is added.
"""
from __future__ import annotations

import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, ValidationError

from backend.config import Settings
from backend.devices.store import DeviceRecord, Store
from backend.protocol.envelope import (
    MSG_HEARTBEAT, MSG_REGISTER, MSG_TELEMETRY, Envelope,
)
import base64
import json

from backend.protocol.observation import Observation
from backend.protocol.signed_observation import SignedObservationEnvelope
from backend.security.pqc_gateway import PqcGateway, PqcRejection
from backend.security.session import HandshakeInit, SealedMessage
from backend.security.auth import AuthError, authenticate
from backend.security.enforcement import NORMAL, decide
from backend.evidence.chain import EvidenceRecorder
from backend.api.security_routes import register_security_routes
from backend.security.credentials import CredentialStore, EncryptedCredentialStore, load_or_create_master_key
from backend.security.tokens import bearer_from_header, load_or_create_token, token_matches
from backend.security.operators import BOOTSTRAP, OperatorStore
from backend.security.rejections import RejectionRecorder

DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "dashboard"
AUTH_FAIL_LOG_INTERVAL_S = 10.0  # throttle so unauthenticated callers cannot flood the event table
SESSION_GONE = frozenset({"unknown_session", "session_session_expired"})   # -> 401 "session_expired"


class RegisterPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fw_version: str
    hw: str  # e.g. "esp32" or "software-agent"; simulated devices must say so
    capabilities: list[str] = []


class HeartbeatPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uptime_ms: int


class TelemetryPayload(BaseModel):
    """Sensor fields are None when the sensor is absent. Absent is never reported as 0."""
    model_config = ConfigDict(extra="forbid")
    temperature_c: float | None = None
    humidity_pct: float | None = None
    pressure_hpa: float | None = None
    vibration_g: float | None = None
    rssi_dbm: float | None = None        # network telemetry: Wi-Fi signal strength (informational unless a range is set)
    tamper: bool
    fw_version: str | None = None
    cfg_hash: str | None = None


def _iso(ts: float | None) -> str | None:
    return None if ts is None else datetime.fromtimestamp(ts, timezone.utc).isoformat()


def device_view(d: DeviceRecord, now: float, offline_after: float) -> dict:
    if d.last_seen is None:
        status = "ENROLLED"  # enrolled but never heard from
    else:
        status = "ONLINE" if now - d.last_seen <= offline_after else "OFFLINE"
    t = d.last_telemetry
    return {
        "device_id": d.device_id,
        "status": status,
        "auth_profile": d.auth_profile,
        "revoked": d.revoked,
        "hw": d.info.get("hw"),
        "fw_version": d.info.get("fw_version"),
        "temperature_c": t.get("temperature_c"),
        "humidity_pct": t.get("humidity_pct"),
        "pressure_hpa": t.get("pressure_hpa"),
        "vibration_g": t.get("vibration_g"),
        "rssi_dbm": t.get("rssi_dbm"),
        "tamper": t.get("tamper"),
        "last_seen": _iso(d.last_seen),
    }


def create_app(settings: Settings | None = None, clock: Callable[[], float] = time.time,
               store: Store | None = None, creds: CredentialStore | None = None,
               operator_token: str | None = None, ingest_token: str | None = None,
               pqc: PqcGateway | None = None, trust=None, twin=None, evidence=None, recovery=None) -> FastAPI:
    """trust: TrustService; twin: DigitalTwin; evidence: EvidenceChain; recovery: RecoveryOrchestrator.
    All optional; without `trust` there is no enforcement (Phase 1-3 behaviour)."""
    settings = settings or Settings.load()
    store = store or Store(settings.db_path)
    if creds is None:
        creds = EncryptedCredentialStore(store, load_or_create_master_key(settings.keys_dir, settings.master_key_hex))
    operator_token = operator_token or load_or_create_token("operator", settings.keys_dir, settings.operator_token)
    ingest_token = ingest_token or load_or_create_token("ingest", settings.keys_dir, settings.ingest_token)
    app = FastAPI(title="Q-SHIELD Gateway", version="0.2.0")
    app.state.store = store
    app.state.settings = settings
    app.state.trust = trust
    recorder = EvidenceRecorder(evidence) if evidence is not None else None
    if trust is not None and recorder is not None and not any(
            getattr(getattr(f, "__self__", None), "chain", None) is evidence for f in trust.listeners):
        trust.listeners.append(recorder.on_trust_change)
    if recovery is not None and recorder is not None and recovery.recorder is None:
        recovery.recorder = recorder
    app.state.recovery_timer = None
    if recovery is not None and settings.recovery_tick_s > 0:
        from backend.recovery.orchestrator import RecoveryTimer
        timer = RecoveryTimer(recovery, settings.recovery_tick_s, on_error=lambda e: store.add_event(
            clock(), None, "recovery_timer_error", "high", {"error": type(e).__name__}))
        app.state.recovery_timer = timer
        app.router.on_startup.append(timer.start)
        app.router.on_shutdown.append(timer.stop)
    last_block_log: dict[str, float] = {}
    last_fail_log = {"t": -1e18}
    # Routine rejected traffic is sampled and coalesced so an unauthenticated flood cannot grow the event table without
    # bound; high-value events pass straight through (backend/security/rejections.py).
    rejections = RejectionRecorder(
        store, window_s=settings.rejection_window_s, sample_per_key=settings.rejection_sample_per_key,
        window_cap=settings.rejection_window_cap, keep_rows=settings.rejection_keep_rows,
        consumed_upto=(lambda: store.get_cursor("security_events")) if trust is not None else None)
    app.state.rejections = rejections

    def _auth_failed(scope: str, request: Request):
        now = clock()
        if now - last_fail_log["t"] >= AUTH_FAIL_LOG_INTERVAL_S:
            last_fail_log["t"] = now
            store.add_event(now, None, f"{scope}_auth_failed", "medium", {"path": request.url.path})
        raise HTTPException(401, "authentication_required", headers={"WWW-Authenticate": "Bearer"})

    def _token_guard(scope: str, expected: str):
        def guard(request: Request) -> None:
            if token_matches(bearer_from_header(request.headers.get("authorization")), expected):
                return
            _auth_failed(scope, request)
        return guard

    operators = OperatorStore(store)
    app.state.operators = operators

    def _operator_guard(role: str):
        """Authenticate a named operator (or the bootstrap shared token) and check its role. The identity is put on
        request.state.operator; it is the ONLY source of operator_id for attribution (never the request body)."""
        def guard(request: Request):
            presented = bearer_from_header(request.headers.get("authorization"))
            op = operators.authenticate(presented, clock())
            if op is None and settings.allow_shared_operator_token and token_matches(presented, operator_token):
                op = BOOTSTRAP
            if op is None:
                _auth_failed("operator", request)
            if not op.allows(role):
                store.add_event(clock(), None, "operator_forbidden", "medium",
                                {"operator_id": op.operator_id, "role": op.role, "required": role,
                                 "path": request.url.path, "method": request.method})
                raise HTTPException(403, f"forbidden: role {role} required")
            request.state.operator = op
            return op
        return guard

    require_operator = Depends(_operator_guard("viewer"))       # read-only operator API
    require_actor = Depends(_operator_guard("operator"))        # security actions
    require_admin = Depends(_operator_guard("admin"))           # operator management
    require_ingest = Depends(_token_guard("ingest", ingest_token))

    def enforce(device_id: str, channel: str, now: float) -> None:
        """Phase 6: apply the access policy for this AUTHENTICATED device message. Throttled logging."""
        if trust is None:
            return
        try:
            state = trust.state_of(device_id)
        except Exception:  # noqa: BLE001
            # Trust-engine fault: enforce the last state already held in memory. A device known to be quarantined stays
            # blocked; an engine bug does not lock out every healthy device (and never changes authentication).
            store.add_event(now, device_id, "trust_engine_error", "high", {"during": "enforcement"})
            dt = trust.engine.devices.get(device_id)
            state = dt.state if dt is not None and dt.started else None
        d = decide(channel, state)
        if d.allowed:
            return
        event = "quarantine_access_blocked" if channel == NORMAL else "recovery_channel_denied"
        key = f"{device_id}:{event}"
        if now - last_block_log.get(key, -1e18) >= AUTH_FAIL_LOG_INTERVAL_S:
            last_block_log[key] = now
            store.add_event(now, device_id, event, "high" if channel == NORMAL else "low",
                            {"channel": channel, "trust_state": d.state, "reason": d.reason})
            if recorder is not None:
                recorder.record(event, {"channel": channel, "reason": d.reason}, ts=now, device_id=device_id,
                                source="gateway_enforcement", trust_state=d.state, trust_score=trust.score_of(device_id))
        raise HTTPException(403, d.reason)

    def handle(env: Envelope, expected_type: str, payload_model: type[BaseModel], channel: str = NORMAL):
        now = clock()
        try:
            auth = authenticate(store, creds, env, expected_type)
        except AuthError as e:
            known = store.get_device(env.device_id) is not None
            rejections.record(now, env.device_id if known else None, e.reason, e.severity,
                              {"claimed_device_id": env.device_id, "type": env.type, "counter": env.counter})
            raise HTTPException(status_code=401, detail="authentication_failed")
        # Authenticated: write any coalesced rejections first, so the trust engine sees the last violation BEFORE this
        # message (credited recovery time is measured from it, exactly as with one row per rejected message).
        rejections.flush(now)
        try:
            payload = payload_model.model_validate_json(env.payload)
        except ValidationError:
            store.add_event(now, env.device_id, "malformed_payload", "low", {"type": env.type})
            raise HTTPException(status_code=422, detail="malformed_payload")
        enforce(env.device_id, channel, now)
        return auth, payload, now

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "proto": 1}

    @app.post("/api/v1/register")
    def register(env: Envelope):
        auth, p, now = handle(env, MSG_REGISTER, RegisterPayload)
        store.touch(env.device_id, now, info=p.model_dump(), registered=True, message_kind="register")
        if twin is not None:
            twin.observe(env.device_id, now, info=p.model_dump())
        return {"status": "registered", "server_time": _iso(now),
                "offline_timeout_s": settings.device_offline_timeout_s}

    @app.post("/api/v1/heartbeat")
    def heartbeat(env: Envelope):
        _, _, now = handle(env, MSG_HEARTBEAT, HeartbeatPayload)
        store.touch(env.device_id, now, message_kind="heartbeat")
        return {"status": "ok", "server_time": _iso(now)}

    @app.post("/api/v1/telemetry")
    def telemetry(env: Envelope):
        _, p, now = handle(env, MSG_TELEMETRY, TelemetryPayload)
        data = p.model_dump()
        store.add_telemetry(env.device_id, now, env.counter, data)
        store.touch(env.device_id, now, telemetry=data, message_kind="telemetry")
        if twin is not None:
            twin.observe(env.device_id, now, telemetry=data)
        return {"status": "accepted", "server_time": _iso(now)}

    @app.get("/api/v1/devices", dependencies=[require_operator])
    def devices():
        now = clock()
        return [device_view(d, now, settings.device_offline_timeout_s) for d in store.list_devices()]

    @app.get("/api/v1/devices/{device_id}", dependencies=[require_operator])
    def device(device_id: str):
        d = store.get_device(device_id)
        if d is None:
            raise HTTPException(404, "not_found")
        return device_view(d, clock(), settings.device_offline_timeout_s)

    @app.get("/api/v1/devices/{device_id}/telemetry", dependencies=[require_operator])
    def device_telemetry(device_id: str, limit: int = Query(50, ge=1, le=500)):
        if store.get_device(device_id) is None:
            raise HTTPException(404, "not_found")
        return store.recent_telemetry(device_id, limit)

    @app.get("/api/v1/events", dependencies=[require_operator])
    def events(limit: int = Query(100, ge=1, le=500)):
        rejections.flush(clock())                       # an operator reading the log sees coalesced counts too
        return store.list_events(limit)

    # ---------------- PQC: signed observations and ML-KEM sessions ----------------
    def _need_pqc() -> PqcGateway:
        if pqc is None:
            raise HTTPException(503, "pqc_not_configured")
        return pqc

    def _reject(e: PqcRejection, via: str, signer_id: str | None, observation_id: str | None = None):
        dev = getattr(e, "device_id", None)
        rejections.record(clock(), dev, f"pqc_{e.reason}", e.severity,
                          {"via": via, "claimed_signer_id": signer_id, "observation_id": observation_id, "device_id": dev})
        detail = {401: "authentication_failed", 409: "replay_detected", 422: "malformed_request"}.get(e.status, "rejected")
        if e.reason in SESSION_GONE:
            # The only rejection a client must answer by opening a new ML-KEM session. Saying so reveals nothing about
            # signatures or keys (session ids are random), and it lets clients stop re-handshaking on every other 401.
            detail = "session_expired"
        raise HTTPException(e.status, detail)

    def _ingest_verified(env: SignedObservationEnvelope, via: str, expected_signer: str | None = None):
        gw = _need_pqc()
        now = clock()
        try:
            obs, signer = gw.verify_signed_observation(env, expected_signer=expected_signer)
        except PqcRejection as e:
            _reject(e, via, env.signer_id, env.observation_id)
        device = store.get_device(obs.device_id)
        if device is None or device.revoked:
            rejections.record(now, None, "pqc_observation_unknown_device", "low",
                              {"via": via, "claimed_device_id": obs.device_id, "signer_id": signer.signer_id})
            raise HTTPException(422, "unknown_or_revoked_device")
        auth = f"{env.algorithm}:{signer.signer_id}"
        if not store.add_observation(now, obs.to_wire(), auth=auth, envelope=env.model_dump_json(), transport=via):
            _reject(PqcRejection("observation_replay", "medium", 409, device_id=obs.device_id), via, env.signer_id, env.observation_id)
        return {"status": "accepted", "observation_id": obs.observation_id, "auth": auth}

    @app.get("/api/v1/pqc/gateway-key")
    def pqc_gateway_key():
        """Public KEM key. Clients must compare the fingerprint with a copy pinned out of band."""
        rec = _need_pqc().gateway_public_key()
        return {"key_id": rec.key_id, "algorithm": rec.algorithm,
                "public_key": base64.b64encode(rec.public_key).decode(), "fingerprint_sha256": rec.fingerprint}

    @app.post("/api/v1/pqc/session")
    def pqc_session(init: HandshakeInit):
        try:
            return _need_pqc().establish_session(init)
        except PqcRejection as e:
            _reject(e, "session", init.signer_id)

    @app.post("/api/v1/observations/signed")
    def ingest_signed(env: SignedObservationEnvelope):
        """ML-DSA-signed observation. The signature is the authentication; no bearer token needed."""
        return _ingest_verified(env, "signed")

    @app.post("/api/v1/observations/secure")
    def ingest_secure(msg: SealedMessage):
        """Signed observation carried inside an ML-KEM-derived AES-256-GCM session."""
        gw = _need_pqc()
        try:
            env, session_signer = gw.open_secure(msg)
        except PqcRejection as e:
            _reject(e, "secure", None)
        return _ingest_verified(env, "secure", expected_signer=session_signer)

    @app.post("/api/v1/observations", dependencies=[require_ingest])
    def ingest_observation(obs: Observation):
        """Accept a normalized observation from a local observer (e.g. the vision service).
        Observations are stored as evidence for later fusion; they change no trust state."""
        now = clock()
        if settings.require_signed_observations:
            raise HTTPException(403, "signed_observations_required")
        device = store.get_device(obs.device_id)
        if device is None or device.revoked:
            rejections.record(now, None, "observation_rejected_device", "low", {"claimed_device_id": obs.device_id})
            raise HTTPException(422, "unknown_or_revoked_device")
        stored = store.add_observation(now, obs.to_wire())
        return {"status": "accepted" if stored else "duplicate", "observation_id": obs.observation_id}

    @app.get("/api/v1/observations", dependencies=[require_operator])
    def observations(device_id: str | None = None, limit: int = Query(100, ge=1, le=500),
                     anomalies_only: bool = False):
        return store.list_observations(device_id, limit, anomalies_only)

    if trust is not None:
        @app.middleware("http")
        async def _trust_update(request: Request, call_next):
            """After every gateway write, let the trust engine consume the new records. A trust-engine fault must never
            change the response or the authenticity verdict of the request that triggered it."""
            response = await call_next(request)
            if request.method == "POST" and request.url.path.startswith("/api/v1/"):
                try:
                    trust.process_pending()
                    if recovery is not None:
                        recovery.tick()
                except Exception:  # noqa: BLE001 - fail closed for trust, never for the gateway
                    store.add_event(clock(), None, "trust_engine_error", "high", {"path": request.url.path})
            return response

        @app.get("/api/v1/trust", dependencies=[require_operator])
        def trust_all():
            return trust.snapshot_all()

        @app.get("/api/v1/trust/diagnostics", dependencies=[require_operator])
        def trust_diag(limit: int = Query(100, ge=1, le=500)):
            return store.list_trust_diagnostics(limit)

        @app.get("/api/v1/trust/{device_id}", dependencies=[require_operator])
        def trust_one(device_id: str):
            if store.get_device(device_id) is None:
                raise HTTPException(404, "not_found")
            return trust.snapshot(device_id)

        @app.get("/api/v1/trust/{device_id}/history", dependencies=[require_operator])
        def trust_history(device_id: str, limit: int = Query(50, ge=1, le=500)):
            if store.get_device(device_id) is None:
                raise HTTPException(404, "not_found")
            trust.process_pending()
            return trust.history(device_id, limit)

    @app.get("/api/v1/system", dependencies=[require_operator])
    def system(request: Request):
        """Read-only description of how THIS gateway is configured, for the dashboard (no secrets, no private keys).
        server_time lets the UI show gateway-clock offsets honestly (e.g. the demo's announced TIME-LAPSE)."""
        out: dict = {"server_time": clock(), "transport": request.url.scheme,
                     "operator_auth": {"shared_token_enabled": settings.allow_shared_operator_token}}
        if pqc is not None:
            key = pqc.gateway_public_key()
            out["pqc"] = {"enabled": True, **pqc.backend.info(), "gateway_kem_key_id": key.key_id,
                          "gateway_kem_fingerprint_sha256": key.fingerprint,
                          "signers": [{"signer_id": s.signer_id, "algorithm": s.algorithm, "source": s.source,
                                       "allowed_devices": list(s.allowed_devices), "status": s.status}
                                      for s in store.list_signers()]}
        else:
            out["pqc"] = {"enabled": False}
        signer = getattr(evidence, "signer", None)
        out["evidence"] = {"enabled": evidence is not None, "signed": signer is not None,
                           "key_id": getattr(signer, "key_id", None),
                           "algorithm": getattr(getattr(signer, "backend", None), "sig_algorithm", None),
                           "hash": "SHA-256" if evidence is not None else None}
        if trust is not None:
            c = trust.cfg
            out["trust"] = {"enabled": True, "trusted_min": c.trusted_min, "quarantine_below": c.quarantine_below,
                            "trusted_reentry_min": c.trusted_reentry_min, "pressure_cap": c.pressure_cap,
                            "correlation_window_s": c.correlation_window_s, "offline_timeout_s": c.offline_timeout_s,
                            "weights": {f.value: w for f, w in c.weights.items()}}
        else:
            out["trust"] = {"enabled": False}
        if recovery is not None:
            rc = recovery.cfg
            out["recovery"] = {"enabled": True, "health_checks_required": rc.health_checks_required,
                               "deadline_s": rc.deadline_s, "ramp_timeout_s": rc.ramp_timeout_s,
                               "background_timer_s": settings.recovery_tick_s or None}
        else:
            out["recovery"] = {"enabled": False}
        return out

    register_security_routes(app, store=store, clock=clock, require_operator=require_operator, require_actor=require_actor,
                             require_admin=require_admin, operators=operators, handle=handle,
                             trust=trust, twin=twin, evidence=evidence, recorder=recorder, recovery=recovery)
    if (DASHBOARD_DIR / "index.html").is_file():
        # Static files only; every datum shown is fetched from the operator API with the operator token.
        app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
    return app
