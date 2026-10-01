# Q-SHIELD — Implementation Status

Persistent project memory. Read together with `docs/BUILD_CHECKPOINT.md`.
Last updated: 2026-09-30.

## CURRENT PHASE
Phases 0–11 implemented, tested, and exercised by the integrated demo. Remaining work is listed under **WHAT IS LEFT**.

## TEST COUNT
**614 passed, 0 failed** (`python -m pytest -o addopts="" -q`, ~2 min). The baseline before the continuous build was 544.

## COMPLETED
| Phase | Feature | Status | Key code | Tests |
|---|---|---|---|---|
| 0–1 | Foundation; device↔gateway (HMAC-SHA256 envelope, replay counter, operator and ingest tokens) | VERIFIED | `backend/api/app.py`, `backend/security/auth.py` | `tests/security`, `tests/integration` |
| 2 | Vision: real webcam + YOLO11n, zones, camera health | VERIFIED (accuracy not measured) | `ai/vision/` | `tests/ai` |
| 3 | PQC: ML-KEM-768 / ML-DSA-65 (pqcrypto), signed observations, ML-KEM + AES-256-GCM session, ACVP vectors | VERIFIED | `backend/security/` | `tests/pqc`, `tests/security` |
| 4 / 4.1 | Dynamic trust engine: deterministic, explainable, caps, decay, state machine, recovery semantics | VERIFIED | `backend/trust/` | `tests/trust` |
| 5 | Attack simulation: 11 scenarios run through the real gateway; results are read back, not asserted | IMPLEMENTED + TESTED (traffic is SIMULATED and labelled) | `attack_simulation/simulator.py` | `tests/fullstack/test_attacks.py` |
| 6 | Quarantine **enforcement**: normal / recovery / control channels, applied after authentication | IMPLEMENTED + TESTED | `backend/security/enforcement.py`, `backend/api/app.py`, `backend/api/security_routes.py` | `tests/fullstack/test_quarantine.py` |
| 7 | Recovery orchestrator: remediation → health checks → VERIFIED → trust ramp → RECOVERED → TRUSTED; every failure path returns to QUARANTINED | IMPLEMENTED + TESTED | `backend/recovery/orchestrator.py` | `tests/fullstack/test_recovery.py` |
| 8 | Evidence chain: append-only, SHA-256-linked, ML-DSA-65-signed; tamper / delete / reorder / forged-signature detection | IMPLEMENTED + TESTED | `backend/evidence/chain.py` | `tests/evidence/test_chain.py` |
| 9 | Digital twin: expected vs observed state, MATCH / MISMATCH / UNKNOWN, feeds per-device trust expectations | IMPLEMENTED + TESTED | `backend/twin/twin.py` | `tests/twin/test_twin.py` |
| 10 | Dashboard ("Security Command Center"): static page served at `/dashboard`, operator API only | IMPLEMENTED (visually QA'd via headless Edge) | `dashboard/` | smoke test in `test_quarantine.py` |
| 11 | Integrated demo on a real uvicorn gateway: TRUSTED → SUSPICIOUS → QUARANTINED → RECOVERING → VERIFIED → RECOVERED → TRUSTED | IMPLEMENTED + TESTED | `scripts/demo_full.py` | `tests/end_to_end/test_demo_full.py`; transcript in `docs/results/demo-full-run.txt` |
| — | Production wiring: `python -m backend.main` builds trust + twin + signed evidence + recovery (evidence key auto-created, sealed under the master key) | IMPLEMENTED + TESTED + live-smoke-tested | `backend/main.py` | `tests/integration/test_main_services.py` |

## BUG FOUND AND FIXED DURING THE BUILD
Trust engine, out-of-order rule: with a real clock, a time-driven evaluation that ran between a message's receipt and
its processing (an enforcement check or a dashboard poll) made legitimate messages count as "out of order", so they
earned no recovery credit. Recovery was silently about 3× slower and nondeterministic. The frozen test clock could not
show this; the live demo did. The fix: out of order now means older than the last applied **signal**. Documented in
trust-engine.md §6.4 and covered by regression tests.

## OPERATOR CONTROLS (Phase 12)
- These use the existing operator API and its single shared operator bearer token. That token is authentication plus authorization. There is no RBAC and no per-operator identity yet (TD-17). The ingest token and device credentials are rejected with 401.
  - `POST /api/v1/devices/{id}/recovery/start` `{reason}`: goes through `RecoveryOrchestrator.start`. It needs QUARANTINED, not revoked, a twin expected state, and no recovery already active (otherwise 409). The body is `extra=forbid`, so no target state can be smuggled in (422). The operator cannot force any state.
  - `POST /api/v1/devices/{id}/recovery/abort` `{reason}`: the recovery is marked failed with `aborted: <reason>` and the device goes to QUARANTINED through the state machine. If no recovery is active, it returns 409.
  - `PUT /api/v1/devices/{id}/twin/expected`: the known-good fw_version/cfg_hash (and capabilities/sensor_ranges). It needs at least fw_version or cfg_hash (otherwise 422). It is **frozen while a recovery is active** (409), so the health-check yardstick cannot be moved mid-verification. Expected and observed state are stored and returned separately. Observed is self-reported evidence, not attestation.
  - Every action is recorded: `recovery_started` / `recovery_failed` / `twin_expected_updated` security events plus ML-DSA evidence-chain entries.
- Dashboard: the "Operator actions" card has a reason field, START/ABORT RECOVERY, and a known-good-state form. It shows loading, success, and refusal with the server's reason. Button enablement is only a hint, because the gateway re-checks everything. After every action the card re-renders from the API, so it reflects backend reality after a reload.
- Tests: `tests/fullstack/test_operator_controls.py` (28) and `tests/fullstack/test_dashboard_contract.py` (3, which check that the JS calls existing routes and replay the button request sequence).
- Not verified: no real browser click-through (no browser automation is installed here). The JS passes `node --check`, and its exact requests are replayed in the tests.
- Webcam: `python scripts/demo_full.py --webcam` was run with no camera attached. It prints `webcam step NOT run: cannot open camera source 0` and the rest of the demo completes (TRUSTED 85). The camera path itself is still unverified.

## OPERATOR IDENTITY + TLS (Phase 13)
**Implemented and tested:**
- **Named operators** (`backend/security/operators.py`, `operators` table): `operator_id`, `display_name`, `role`, `status` (active/revoked), optional `expires_at`, `created_by`, `revoked_by`. Tokens are `qso_` + 256-bit random. **Only SHA-256(token) is stored.** The token is returned once at creation and never appears in listings, events or the evidence chain. Revocation and expiry apply on the next request.
- **Roles:** `viewer` (read-only API), `operator` (+ start/abort recovery, set expected state, manual quarantine), `admin` (+ create/list/revoke operators). An authenticated caller without the required role gets 403, and a throttle-free `operator_forbidden` event is recorded.
- **Bootstrap:** the legacy shared token (`QSHIELD_OPERATOR_TOKEN` / `keys/operator.token`) authenticates as `bootstrap-admin` (role admin; flagged `bootstrap: true`; **not a person**) so the first operators can be created. Disable it with `ALLOW_SHARED_OPERATOR_TOKEN=false`. It is enabled by default for backward compatibility, and the gateway prints a startup note.
- **Auth boundaries unchanged:** the ingest token, device HMAC secrets and operator tokens never substitute for one another (tests both ways).
- **Attribution:** every operator action (START_RECOVERY, ABORT_RECOVERY, SET_EXPECTED_STATE, QUARANTINE, CREATE_OPERATOR, REVOKE_OPERATOR) writes one `operator_action` security event **and** one ML-DSA evidence-chain entry with `operator_id`, `operator_role`, `action`, `device_id`, `reason` and `result` (`success` or `refused` with the error). `operator_id` comes only from the authenticated identity. Request bodies are `extra=forbid`, so an `operator_id` in JSON is a 422. The recovery record stores `requested_by=<operator_id>`, and the abort reason carries `(by <operator_id>)`.
- **Operator management:** API `GET /api/v1/operators/me` (any operator), `GET|POST /api/v1/operators`, `POST /api/v1/operators/{id}/revoke` (admin), and the local CLI `python scripts/operators.py create|list|revoke`.
- **TLS** (`backend/security/tls.py`): `QSHIELD_TLS_CERT` + `QSHIELD_TLS_KEY` make uvicorn serve HTTPS. Half or invalid configuration (missing file, mismatched pair, garbage) fails at startup with a clear message. `QSHIELD_REQUIRE_TLS=true` refuses to start in HTTP mode. With neither set, the gateway stays in development HTTP mode and prints a CLEARTEXT warning. `python scripts/gen_dev_cert.py [--host <LAN IP>]` writes a **self-signed** ECDSA P-256 dev cert to `keys/tls/` (gitignored; key file owner-only, never overwritten). Tested against a real uvicorn HTTPS listener: a request pinned to the dev cert succeeds, the default client rejects the self-signed cert, and plain HTTP to the TLS port gets no API response.
- **Dashboard:** shows `Operator: <id> (<role>)` from `/operators/me`. Action buttons are disabled for `viewer`. 401 and 403 are shown as "token rejected/revoked/expired" and "role does not allow". The token is entered in a password field and kept in sessionStorage. It is never rendered.
- Tests: `tests/fullstack/test_operator_identity.py` (22), `tests/security/test_tls.py` (6). One Phase 12 assertion changed on purpose (the abort reason now ends with `(by bootstrap-admin)`), documented in the test.

**Security review (attempted bypasses):** the following all failed. Spoofing `operator_id`/`requested_by` in the body (422). Ingest token or device secret as operator (401). Revoked or expired token (401 on the next request). A viewer or operator calling admin/action routes (403, recorded). An operator creating an admin (403). Creating the reserved `bootstrap-admin` id or choosing your own token (refused). Tokens leaking through `/operators`, `/events` or the evidence chain (they don't).

**Prototype-only / production hardening required:**
- A bearer token *is* the identity: whoever holds it acts as that operator. There is no MFA, no session binding and no per-request replay protection (TLS is the protection on the wire). Over development HTTP, tokens are visible to anyone on the network.
- Roles are global, not per device. There is no lockout or rate limit on failed operator auth (only throttled logging).
- The shared bootstrap token is enabled by default. Production must create named admins and set `ALLOW_SHARED_OPERATOR_TOKEN=false` and `QSHIELD_REQUIRE_TLS=true`.
- The dev certificate is self-signed: no PKI, no rotation automation, no HTTP->HTTPS redirect, no mTLS. The ESP32 firmware has no TLS client (HMAC only).
- The `demo_full.py` script still uses the shared bootstrap token over local HTTP and prints a dashboard URL containing it (demo only).

## HOW TO RUN
```
python -m pytest -o addopts="" -q                   # full suite
python scripts/demo_full.py                         # full story on a real gateway (scratch state)
python scripts/demo_full.py --pace 2 --hold         # presentation pacing; keeps the gateway up for the dashboard
python scripts/demo_full.py --webcam                # adds the real webcam + YOLO11n step (needs a camera; USER TO RUN)
python scripts/gen_dev_cert.py                      # self-signed dev cert -> keys/tls/
QSHIELD_TLS_CERT=keys/tls/gateway.crt QSHIELD_TLS_KEY=keys/tls/gateway.key QSHIELD_REQUIRE_TLS=true python -m backend.main
python scripts/operators.py create alice "Alice" operator   # prints alice's token once
# dashboard: https://localhost:8000/dashboard/  -> paste the operator token -> header shows 'Operator: alice (operator)'
```
The demo prints the dashboard URL with the operator token.

## KNOWN LIMITATIONS (honest)
- All device data is SIMULATED (software agent). The ESP32 firmware has never been compiled or flashed, and its path is HMAC-SHA256 only (not PQC).
- No physical tamper test was ever performed.
- The webcam step of the new demo was **not** re-run live this session because no camera was attached. The vision pipeline was live-verified in Phases 3–4.
- Twin observed state is self-reported: it is evidence, not attestation.
- The trust ramp takes about 40 minutes of clean evidence at the documented parameters. The demo uses a clearly labelled TIME-LAPSE clock and does not change parameters.
- Trust parameters are design choices and have not been calibrated against data (trust-engine.md §16).
- The custom ML-KEM session protocol has had no external review. TLS is optional (self-signed dev cert); in the default development HTTP mode tokens travel in cleartext.
- The evidence chain has no external anchoring. Anyone holding both the DB and the evidence key can rewrite history.
- Recovery deadlines are evaluated by a background `RecoveryTimer` (every `RECOVERY_TICK_S`, default 5 s; 0 disables) as well as on each request.
- The service is single-process and single-gateway (SQLite).

## WHAT IS LEFT
| Priority | Item | Notes |
|---|---|---|
| High | Run `demo_full.py --webcam` live with a camera attached | Code path exists; not re-verified this session |
| High | Real ESP32: compile, flash, wire the tamper switch and sensors, replace the software agent | Biggest credibility gap |
| Done | Background timer for recovery deadlines | `RecoveryTimer` in `backend/recovery/orchestrator.py`, started/stopped with the gateway; tests in `tests/fullstack/test_recovery_timer.py` |
| Done | Dashboard operator actions | See "OPERATOR CONTROLS" below |
| Done (prototype) | TLS for the gateway; per-operator tokens | Phase 13; see above |
| Medium | Update the audit PDF and the PPT to reflect Phases 5–11 | Both still describe Phases 5–10 as planned |
| Low | External anchoring of the evidence head; key rotation | TD-09, TD-15 |
| Research | Calibrate trust parameters; measure vision accuracy; external review of the session protocol | trust-engine.md §16 |
