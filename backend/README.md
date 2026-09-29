# Backend (gateway)

Status: Phase 0/1 (device slice) and the Phase 1 hardening (credential store, operator auth) **implemented and tested** with a software device agent; observation ingestion added for Phase 2. No real ESP32 has been exercised.

## Security terminology (do not blur)
- **Device authentication (ESP32 profile):** provisioned per-device HMAC-SHA256 secret. Symmetric. **Not post-quantum.**
- **PQC gateway security:** ML-KEM-768 (key establishment) and ML-DSA-65 (signatures), behind `backend/security/pqc.py`. Interface and working backend exist; using them for sessions, signed envelopes and evidence is Phase 3. The gateway does not yet use PQC on any device path, and `auth: pqc-mldsa-mlkem` is refused, not faked.
- **Symmetric session protection (AES-256-GCM):** Phase 3. Phase 1 traffic is authenticated but not encrypted.

## Layout
`config.py` settings/.env · `security/credentials.py` credential store · `security/tokens.py` operator/ingest tokens · `protocol/observation.py` observation schema · `protocol/envelope.py` wire format, signing · `security/auth.py` envelope authentication · `security/pqc.py` PQC abstraction · `devices/store.py` SQLite · `api/app.py` FastAPI app · `main.py` entry point. Companion: `device_agent/` (software device), `scripts/enroll_device.py`.

## Run
```
pip install -r backend/requirements.txt
cp .env.example .env                      # optional; defaults work
python scripts/enroll_device.py DEVICE-001   # creates keys/devices/DEVICE-001.secret (gitignored), stores it in the DB
python -m backend.main                       # gateway on :8000; creates keys/master.key, keys/operator.token, keys/ingest.token on first start
python -m device_agent --device-id DEVICE-001   # simulated device (labelled hw="software-agent")
curl -H "Authorization: Bearer $(cat keys/operator.token)" http://127.0.0.1:8000/api/v1/devices
python -m pytest
```

## API (v1) and authentication
| Caller | Auth | Endpoints |
|---|---|---|
| Device | per-device HMAC-SHA256 envelope (not PQC) | `POST /api/v1/{register,heartbeat,telemetry}` |
| Operator | `Authorization: Bearer <operator token>` | `GET /api/v1/devices[/{id}[/telemetry]]`, `GET /api/v1/events`, `GET /api/v1/observations` |
| Vision service (token-only, not PQC) | `Authorization: Bearer <ingest token>` | `POST /api/v1/observations` (stored as `auth: ingest-token`; disable with `REQUIRE_SIGNED_OBSERVATIONS=true`) |
| Vision service (PQC) | ML-DSA-65 signature in the envelope; optional ML-KEM-768 session | `POST /api/v1/observations/signed`, `POST /api/v1/pqc/session` + `POST /api/v1/observations/secure`, `GET /api/v1/pqc/gateway-key` |
| none | open | `GET /api/v1/health` |

The three mechanisms are independent: an operator token cannot ingest, an ingest token cannot read, and neither is accepted (or needed) on device endpoints. Details and limits: `docs/technical-decisions.md` TD-17. Device status: `ENROLLED`, `ONLINE`, `OFFLINE` (no authenticated message within `DEVICE_OFFLINE_TIMEOUT_S`). Observations are stored as evidence only; they never change device status.

## PQC setup (Phase 3)
```
python scripts/pqc_provision.py init-gateway                         # ML-KEM-768 gateway key (sealed under the master key)
python scripts/pqc_provision.py enroll-signer vision-1 --device DEVICE-001   # ML-DSA-65 signer for the vision service
python -m backend.main                                                # PQC_ENABLED=true by default; refuses to start if keys are missing
python -m ai.vision run --gateway http://127.0.0.1:8000 --signer-id vision-1 [--secure]
python scripts/bench_pqc.py                                           # measured latencies
```
Design, key management, conformance evidence and limitations: `pqc/README.md`. Set `PQC_ENABLED=false` to run without the PQC endpoints (they then return 503). ESP32 devices are unaffected: they use HMAC-SHA256, not PQC.

## Trust engine (Phase 4)
`backend/trust/` computes a deterministic, explainable 0-100 trust score and state per device from the gateway's own records (authenticated telemetry, observations with their authenticity label, security events). Specification: `docs/architecture/trust-engine.md`.
- Enabled by default in `python -m backend.main` (`TRUST_ENABLED=false` disables it; optional `TRUST_CONFIG_PATH` JSON with only `sensor_limits`, `expected_fw_version`, `expected_cfg_hash`, `offline_timeout_s`). In code: `create_app(..., trust=TrustService(store))`; without it there are no trust routes.
- Read-only, operator-token only: `GET /api/v1/trust`, `/api/v1/trust/{device_id}` (`NO_EVIDENCE` until authenticated evidence exists), `/api/v1/trust/{device_id}/history`, `/api/v1/trust/diagnostics`.
- Records state and *recommends* quarantine; it enforces nothing. Authentication is not trust: a valid signature never raises trust, and forged traffic can only apply a bounded pressure.
- Benchmark: `python scripts/bench_trust.py` (laptop numbers, not a real-time claim). Live evidence: `docs/results/trust-live-run-phase4.json`.

## Device secret storage (prototype)
HMAC secrets live behind `CredentialStore`; the implementation encrypts them (AES-256-GCM, device_id as associated data) under a local master key (`keys/master.key` or `QSHIELD_MASTER_KEY_HEX`). This protects a leaked DB file, **not** an attacker who also has `keys/` or code execution on the gateway. Master-key loss requires re-provisioning all devices. See TD-15.

## Acceptance (Phase 1)
Verified by `tests/integration/test_phase1_flow.py` and a manual live run (enroll → server → agent over HTTP): the API shows DEVICE-001 ONLINE with temperature, vibration, tamper and last_seen; forged, replayed, stale, unknown-device and revoked-device messages are rejected with a logged event.

## Known limitations
- Simulated data only; ESP32 firmware is an uncompiled skeleton (`hardware/esp32/`).
- Bearer tokens travel in cleartext over HTTP and the default bind is LAN-wide: trusted network only until TLS. One shared operator token, no expiry/lockout.
- Device secrets are encrypted at rest but the master key sits beside them on the same host (see above). Old Phase 1 DBs (plaintext secret column) are not migrated.
- No confidentiality, rate limiting, or payload-size enforcement beyond the envelope field limits.
- `security_events` is a plain table; tamper-evidence is Phase 8. Trust scoring exists (Phase 4, recommend-only); quarantine enforcement and recovery do not (Phases 6-7). The trust service assumes a single gateway process owns the DB.
- Tested on Windows 11 / Python 3.12 only.
