# Q-SHIELD Technical Decisions

Status: **approved 2026-09-24; Phase 0/1 implemented** (see amendments marked *Amended*). Each decision has an ID, the choice, the reasoning, the alternatives rejected, and what would make us revisit it. Decisions marked **OPEN** need input from the team before the affected phase starts.

Facts in this document marked *(verified)* were checked on the development laptop (Windows 11, Python 3.12.0, x86-64) during repository inspection. Anything not marked verified is an assumption.

---

## TD-01 — Device authentication tiers and what "PQC" means in this system

**The problem.** The project brief wants PQC-authenticated devices, but also forbids claiming the ESP32 runs ML-KEM/ML-DSA unless we implement and test it there. We have not. We must not blur these.

**Decision.** Protocol v1 defines two authentication profiles, declared per device at enrollment:

| Profile | Used by | Message authentication | Session key establishment |
|---|---|---|---|
| `hmac-sha256-psk` | ESP32 (Phase 1) | HMAC-SHA256 over the canonical message, keyed with a per-device 256-bit secret provisioned at enrollment; strictly increasing counter + nonce for replay defence | Session key derived by HKDF-SHA256 from the provisioned secret and gateway/device nonces. **Not PQC.** |
| `pqc-mldsa-mlkem` | Software device agents (laptop-side Python), attack simulator, gateway-signed artifacts, any future PQC-capable ESP32 | ML-DSA signature over the canonical message | ML-KEM encapsulation → shared secret → HKDF → AES-256-GCM session key |

Laptop-side PQC use that is real regardless of the ESP32: ML-KEM/ML-DSA for software-agent sessions, ML-DSA signatures on evidence-chain entries, and ML-DSA signatures on recovery commands / known-good configuration blobs the gateway sends to devices.

**Claims we may make:** "The gateway implements ML-KEM and ML-DSA (FIPS 203/204). The ESP32 endpoint authenticates with a provisioned 256-bit symmetric key (HMAC-SHA256); a PQC-capable ESP32 client is a research item (R1)."
**Claims we may not make:** that the ESP32 performs PQC; that ESP32 telemetry is "PQC-protected"; "quantum-proof".

**Why not put PQC on the ESP32 now.** Porting and validating ML-KEM/ML-DSA on an ESP32 (RAM, stack depth, RNG quality, timing, constant-time behaviour) is a research task, not a plumbing task, and would block the whole vertical slice. Verification-only ML-DSA on the device (to check gateway-signed commands) is the most plausible first step and is tracked as R1.

**Revisit if:** the R1 spike shows ML-DSA verify (and ideally ML-KEM decaps) is feasible on our ESP32 variant within acceptable memory/latency.

---

## TD-02 — PQC library

**Decision.** `pqcrypto` 1.0.0 (Backbone Technologies Ltd., PyPI, Apache-2.0), using `pqcrypto.kem.ml_kem_768` and `pqcrypto.sign.ml_dsa_65` by default (configurable), isolated behind a small `backend/security/pqc.py` interface so it can be replaced.

**Evidence.** *(verified)* On this machine `pip install pqcrypto` installs a prebuilt `cp39-abi3-win_amd64` wheel with no compiler. Minimal test: ML-KEM-768 encaps/decaps produced equal 32-byte shared secrets (1088-byte ciphertext); a corrupted ciphertext yielded a *different* secret (implicit rejection, as specified); ML-DSA-44 sign/verify succeeded on the original message and raised `InvalidSignatureError` on a modified message. Full detail in `pqc/README.md`.

**Alternatives rejected on this machine:**
- `cryptography` 47.0.0 (already installed) exposes `mlkem`/`mldsa` modules, but `MLKEM768PrivateKey.generate()` and `MLDSA44/65PrivateKey.generate()` raise `UnsupportedAlgorithm: … not supported by this backend` here *(verified)*. It also does not expose ML-KEM-512. Retain `cryptography` for AES-GCM/HKDF/HMAC, and re-test it as a possible primary if a later release/build supports the algorithms.
- `liboqs-python`: the wheel is a wrapper that needs the native liboqs; the machine has no cmake/gcc/MSVC on PATH *(verified)*, so it would have to be built. Highest install complexity; reject unless the other options fail.
- `kyber-py` / `dilithium-py` (pure Python): their own documentation says not for production/not constant-time. Acceptable only as an independent cross-check in tests.

**Standards conformance (updated in Phase 3: see `pqc/README.md`).** NIST ACVP known-answer tests now pass for decapsulation, key-validity checks and signature verification, and the library interoperates with independent reference implementations; keygen, signing and encapsulation KATs are not possible with this library's API. Original note: a successful round trip does not prove standards conformance. Phase 3 must include known-answer tests (NIST ACVP / official KAT vectors) against the library, or cross-verification against an independent implementation. Until that passes we say "implements ML-KEM/ML-DSA via library X", not "FIPS-validated". No FIPS 140 validation is claimed, ever, for this prototype.

**Known caveats:** vendor is small; independent audit status not verified; implementation is Rust (`backbone-ml-kem`, `backbone-ml-dsa`); only verified on Windows x86-64 so far; package METADATA declares `License-Expression: Apache-2.0` and ships LICENSE and NOTICE files.

**Parameter sets.** Default ML-KEM-768 / ML-DSA-65, configurable via env; `.env.example` updated in Phase 0. The abstraction is `backend/security/pqc.py` (`PqcBackend` interface, `PqcryptoBackend` implementation).

---

## TD-03 — ESP32 ↔ laptop transport

**Decision.** HTTP/1.1 over the local Wi-Fi LAN, device-initiated. The ESP32 `POST`s a signed JSON envelope to `/api/v1/telemetry` and `/api/v1/heartbeat`; the heartbeat *response* carries pending commands and the current device state (`TRUSTED`, `QUARANTINED`, …). No inbound connections to the ESP32.

**Why.** Simple (`HTTPClient` on ESP32, `httpx`/`fastapi` on laptop), debuggable with curl, no broker to install, avoids the fragile "laptop knows the ESP32 IP" assumption in `.env.example` (`ESP32_IP`; DHCP will break it — remove that variable), and device-initiated polling means quarantine is enforced *at the gateway* by refusing service, which does not depend on the device cooperating.

**Confidentiality on the wire.** Phase 1 provides integrity/authenticity/replay protection, not confidentiality. Telemetry encryption (AES-256-GCM with the session key) is added where the profile supports it. We do not add TLS on the ESP32 in v1 (certificate provisioning/time issues); this is a documented limitation, and the LAN is assumed untrusted for integrity but not a target for confidentiality in v1.

**Protocol versioning.** Every envelope carries `"proto": 1`. Gateway rejects unknown versions explicitly.

**Alternatives.** MQTT (extra broker dependency; revisit if we scale to many devices), WebSocket (stateful, more ESP32 code), UDP (unreliable, no).

---

## TD-04 — Message envelope and replay protection (*Amended in Phase 1*)

**Amendment.** The original proposal canonicalised the JSON payload. Phase 1 instead transmits `payload` as a JSON *string* and the tag covers those exact bytes, so ESP32 and gateway can never disagree on number/whitespace formatting. The per-message `nonce` was dropped: the strictly increasing counter is the replay defence; a nonce returns with AES-GCM sessions in Phase 3.

```json
{"proto": 1, "auth": "hmac-sha256-psk", "type": "telemetry", "device_id": "DEVICE-001",
 "counter": 1042, "payload": "{\"temperature_c\":27.4,\"vibration_g\":0.02,\"tamper\":false}", "tag": "<hex>"}
```

- **Signing input:** `"QSHIELD-V1
" + auth + "
" + type + "
" + device_id + "
" + counter + "
" + payload`. It binds profile, message type, device and counter, which blocks downgrade and cross-type/cross-device reuse. Tag = HMAC-SHA256, hex. Implemented in `backend/protocol/envelope.py`; shared vector in `tests/vectors/envelope_v1.json`.
- **Replay:** gateway stores the highest accepted counter per device and accepts a message only if its counter is strictly greater, updated atomically, and only *after* the tag verifies (an unauthenticated sender cannot burn a counter). The device persists its counter across resets (ESP32: NVS, reserving ahead so a power loss never reuses a value). A device that loses its counter must be re-enrolled.
- **Errors:** every authentication failure returns the same `401 authentication_failed`; the specific reason is recorded only as a security event.
- **Time:** the ESP32 has no trusted clock; the gateway stamps receipt time.
- **Confidentiality:** none in Phase 1 (integrity/authenticity only).

---

## TD-05 — Backend

**Decision.** Python 3.12 + FastAPI + Uvicorn + Pydantic v2 (all already installed: FastAPI 0.136.1, Uvicorn 0.30.6, Pydantic 2.13.5 *(verified)*). WebSocket endpoint for dashboard live updates. Modules: `backend/security/`, `trust/`, `recovery/`, `evidence/`, `digital_twin/`, `devices/`, `api/`.

**Why.** Python is where the AI and PQC libraries live; one language for gateway, AI, simulator and tests; typed models double as the schema.

**Pin dependencies** in `backend/requirements.txt` (pinned to the versions we tested against), including test-only `pytest`, `httpx`.

---

## TD-06 — Database

**Decision.** SQLite (WAL mode) via the stdlib `sqlite3` module and a thin repository layer. Tables: devices, sessions, telemetry, events (evidence chain), trust_history, recovery_runs, twin_snapshots.

**Why.** Zero install, single file, sufficient for one to a few devices; SQLAlchemy is installed but adds an ORM we do not need. Keep SQL in one module so a later swap is contained.

**Note.** `.env.example` `DATABASE_URL=sqlite:///./qshield.db` implies SQLAlchemy URL style; we will keep the variable but parse it ourselves. Add `*.db` to `.gitignore`.

---

## TD-07 — Event schema

Two normalized shapes, both Pydantic models, both JSON.

**Detection event** (output of AI, crypto verifier, tamper monitor, twin):
```json
{ "event_id": "uuid", "device_id": "DEVICE-001", "source": "camera|sensor|crypto|network|tamper|twin|config",
  "event_type": "person_in_zone|signature_invalid|replay_detected|tamper_open|sensor_out_of_range|…",
  "severity": "info|low|medium|high|critical", "confidence": 0.0, "observed_at": "ISO-8601",
  "details": { } }
```
**Trust change record:** `{ previous_trust, new_trust, reason, evidence_id, timestamp, factor_deltas }` as specified in the brief.

Every detection event is appended to the evidence chain (TD-09) and yields an `evidence_id`. Event-type vocabulary lives in one enum module; attack scenarios and trust rules reference the same enum.

---

## TD-08 — Trust model

**Decision.** Deterministic, table-driven, explainable. Full formula in `docs/architecture/trust-engine.md` (currently an empty stub, to be written in Phase 4 *before* the code). Proposed structure:

1. Six factor scores in [0, 100]: `identity_crypto`, `physical`, `config_integrity`, `sensor_consistency`, `network`, `ai_confidence`.
2. `raw = Σ wᵢ·fᵢ` with weights summing to 1. **Initial** weights (a design choice, not empirically derived; to be documented as such and tunable): identity_crypto 0.25, physical 0.20, config_integrity 0.15, sensor_consistency 0.15, ai_confidence 0.15, network 0.10.
3. Each security event applies a fixed, documented penalty to its factor(s); penalties **decay/recover** at a documented rate only while no new violating events occur.
4. **Hard caps:** certain events cap the final score regardless of the weighted sum (e.g. invalid signature on an authenticated device, active tamper), so one severe event is not diluted by five healthy factors. Cap values documented.
5. `trust = min(raw, all active caps)`, rounded to integer.
6. Thresholds (config): `≥80 TRUSTED`, `50–79 SUSPICIOUS`, `<50 QUARANTINE`. Hysteresis on the way up to avoid flapping.

The `97 → 61 → 27 → 14` sequence in the brief is illustrative; our demo numbers come out of the model and are reported as they are. No numbers are tuned to make a slide.

**Honesty rule:** the factor `identity_crypto` reflects what was actually verified (HMAC or ML-DSA per profile), and the dashboard labels which.

---

## TD-09 — Evidence chain

**Decision.** Append-only hash chain: each entry stores `seq`, `timestamp`, `event` (canonical JSON), `prev_hash`, `hash = SHA-256(prev_hash ‖ canonical(entry body))`, and an **ML-DSA signature by the gateway evidence key** over `hash`. Verification walks the chain recomputing hashes and checking signatures; any modified historical entry fails at that entry and every later one.

**Limitations to document:** an attacker with both DB write access *and* the gateway signing key can rewrite history; deleting the tail is detectable only if the latest head hash is anchored somewhere external (we will export head hash + signature on each recovery and to the dashboard; true external anchoring is out of scope). Timestamps come from the gateway clock and are not trusted-time.

Chain files go under `evidence/` (runtime output stays gitignored; test fixtures are generated, not committed).

---

## TD-10 — Device state machine and recovery model

**States:** `TRUSTED → SUSPICIOUS → QUARANTINED → RECOVERING → VERIFIED → RECOVERED` (→ `TRUSTED` after the trust-rebuild period). Transition table lives in code and in `docs/architecture/self-healing.md` (empty stub today, to be written before Phase 6).

**Access policy per state** (enforced in the gateway, not requested of the device):
- TRUSTED: telemetry + control accepted.
- SUSPICIOUS: accepted, sampling/monitoring intensified, sensitive commands need re-check.
- QUARANTINED: session revoked; telemetry stored as *untrusted* evidence only; no control; only re-enrollment/recovery endpoints reachable.
- RECOVERING: only recovery-protocol messages accepted.
- VERIFIED: health checks passed, trust ramp begins.

**Recovery scope (defined compromise classes only):** tamper/state anomaly, config drift or integrity mismatch, session/credential compromise, sensor-manipulation. We do not claim repair of physical damage, and we do not claim recovery from compromise of the gateway or of the device's provisioned secret without re-provisioning.

**Sequence:** revoke session → freeze/export evidence → command safe mode → compare device-reported fw/config hash to digital twin → push ML-DSA-signed known-good config → new session (ML-KEM for PQC profile, fresh HKDF nonces for HMAC profile) → health checks (N consecutive normal telemetry windows in expected ranges, network cadence, AI/camera clear) → trust ramps in fixed steps. **Any failed check ⇒ device stays QUARANTINED** with the failed check recorded. A reboot alone never marks recovery.

**Known limit:** firmware/config hashes are self-reported by a possibly compromised device; without ESP32 secure boot + remote attestation they are evidence, not proof. Documented, not hidden.

---

## TD-11 — AI stack (*Updated in Phase 2*)

**Vision (implemented).** Ultralytics YOLO11n (`yolo11n.pt`, ultralytics 8.4.50, PyTorch 2.13.0+cpu) behind a replaceable `Detector` interface, run on the laptop USB webcam. Output is normalized **observations** (`backend/protocol/observation.py`), never trust decisions; fusion happens in Phase 4. Full record in `ai/README.md`.

- **Licence, verified:** the `ultralytics` package metadata and the downloaded checkpoint both declare **AGPL-3.0** (Ultralytics also sells a commercial licence). Q-SHIELD is MIT; we do not vendor or commit the weights. Distributing a combined work or serving it over a network may carry AGPL obligations; this has not had legal review. Mitigation: disclosure, gitignored weights, swappable detector.
- **Weights:** 5,613,764 bytes, SHA-256 `0ebbc80d…644ee1`, from the official Ultralytics assets release v8.4.0.
- **Measured (this laptop, CPU, 640x480 webcam, no person in view):** inference 39.8 ms mean at `imgsz` 640 (25.1 FPS inference-only, 21.0 end-to-end); 19.5 ms at `imgsz` 320. Single runs; accuracy not measured.
- **Sensor anomaly (Phase 2 scope note):** ESP32 sensor anomaly detection is deferred until real ESP32 telemetry exists; design unchanged (deterministic range + rolling robust z-score against the digital twin; optional scikit-learn `IsolationForest` on recorded data only).
- No detection accuracy is claimed until measured on recorded data with a documented method.

**Observation ingestion boundary.** The vision process is a separate service that posts to `POST /api/v1/observations` with an *ingest* bearer token (TD-17). The backend stores observations as evidence; storing one changes no device status or trust.

---

## TD-12 — Camera source

**RESOLVED (2026-09-24): USB webcam on the laptop is the initial vision source; ESP32-CAM is not a dependency** and may be evaluated later only as an optional extension.

Rationale kept for the record: "Camera compatible with ESP32" is ambiguous: an ESP32-CAM (AI-Thinker) module *is* the ESP32 and exposes very few free GPIOs for BME280/MPU6050/reed/OLED, has no USB programmer on board, and has a flash-LED/SD conflict on pins. A USB webcam on the laptop has none of these problems.

**Proposed default:** a `FrameSource` interface with two implementations — laptop webcam (Phase 2, unblocks AI immediately) and ESP32-CAM MJPEG stream (later, possibly as a *second* board with its own device identity). Camera events are attributed to `DEVICE-001` via a configured mapping.

---

## TD-13 — ESP32 firmware toolchain

**Decision.** PlatformIO + Arduino-ESP32 framework, C++17, libraries: Adafruit BME280, an MPU6050 driver, Adafruit SSD1306, ArduinoJson; mbedTLS (bundled) for HMAC-SHA256/HKDF/AES-GCM. Config via a gitignored `secrets.h` generated by an enrollment script.

**Why.** Fastest path to working telemetry. **None of PlatformIO/cmake/ESP-IDF is currently installed** *(verified: no `pio`, `cmake`, `gcc`, `cl` on PATH)*; install is a Phase 1 prerequisite. ESP-IDF is the alternative if we need finer control for R1.

**Secure boot / flash encryption:** described as ESP32 platform mechanisms only, never as PQC. Enabling them burns eFuses irreversibly, so **not enabled during development**; documented as recommended hardening, and enabled only if we have a spare board and time.

**Board variant: still unidentified.** No ESP32 was connected in Phase 0/1. Decision (2026-09-24): generic Arduino-compatible target for now; identify the exact board from the connected hardware before any pin-specific firmware. The firmware skeleton is protocol-only and untested.

---

## TD-14 — Dashboard

**Decision.** Vite + React + TypeScript, hand-written CSS with design tokens, live data over WebSocket from the backend, custom SVG for the trust timeline (the hero visual). No component-library dependency. Built only in Phase 10, against the real backend API; before that, a read-only status page or `curl` suffices for acceptance.

**Alternative:** server-rendered single HTML page served by FastAPI (no build step) — the fallback if time runs short. Node v26.7.0 is installed *(verified)*.

---

## TD-15 — Key and credential management (*Updated after Phase 1 hardening*)

- **Device HMAC secrets:** cannot be hashed (the gateway must recompute tags). They are isolated behind the `CredentialStore` interface (`backend/security/credentials.py`); the implementation, `EncryptedCredentialStore`, stores each secret in SQLite as AES-256-GCM ciphertext (random 96-bit nonce per write, format-versioned) with the `device_id` as associated data, so a blob copied to another device fails to decrypt. The `devices` table no longer has a secret column.
- **Master key:** 32 random bytes from `QSHIELD_MASTER_KEY_HEX` or, by default, `keys/master.key` (created on first use, exclusive-create, mode 0600 on POSIX; on Windows it inherits the folder ACL). Gitignored; never logged.
- **Threat model.** *Protects against:* a leaked, backed-up or committed DB file on its own. *Does not protect against:* an attacker with both the DB and `keys/` (same host/user), a compromised gateway process (secrets are decrypted in memory), or master-key loss (every device must then be re-provisioned). No HSM/TPM/OS-keyring; no key rotation yet. The per-device plaintext copy in `keys/devices/<id>.secret` (needed by the agent/firmware provisioning) is equally sensitive.
- Existing Phase 1 databases (which had a plaintext `secret` column) are not migrated: re-create the DB and re-enroll (prototype).
- Gateway PQC keys (Phase 3): ML-DSA/ML-KEM private keys will be encrypted at rest under the same master-key mechanism; never logged, never in git.
- `SECRET_KEY` placeholder was removed from `.env.example`. Attack simulation uses throwaway keys and targets only local hosts.

---

## TD-17 — Operator and ingest API authentication (*Added in Phase 2 prep*)

Three separate mechanisms that never substitute for one another:

| Caller | Mechanism | Endpoints |
|---|---|---|
| Devices | per-device HMAC envelope (TD-01/TD-04) | `POST /api/v1/{register,heartbeat,telemetry}` |
| Operator (human/dashboard) | bearer token, scope `operator` | all `GET` device/telemetry/event/observation APIs and any future control APIs |
| Local vision/observer service | bearer token, scope `ingest` | `POST /api/v1/observations` |

Tokens: random 256-bit (`secrets.token_urlsafe(32)`) from `QSHIELD_OPERATOR_TOKEN` / `QSHIELD_INGEST_TOKEN` or a gitignored file under `keys/` created on first start; constant-time comparison; failures return `401` with no detail and are logged as throttled security events (one per 10 s) that never contain the token. `/api/v1/health` stays open. Deliberately no OAuth, sessions, roles or expiry; rotate by deleting the token file and restarting. **Limitations:** tokens travel in cleartext over HTTP (trusted LAN only until TLS), a single shared operator token (no per-user audit), no lockout.


**Update (Phase 13): per-operator identities and TLS.** The single operator token became the `bootstrap-admin` identity (can be disabled with `ALLOW_SHARED_OPERATOR_TOKEN=false`). Named operators have hashed (SHA-256) `qso_` tokens, the roles viewer/operator/admin, revocation and optional expiry. Every control action is attributed (an `operator_action` event plus an evidence entry; `operator_id` comes from the authenticated identity only). Optional TLS uses `QSHIELD_TLS_CERT`/`QSHIELD_TLS_KEY` (`QSHIELD_REQUIRE_TLS` to enforce), with a self-signed dev cert from `scripts/gen_dev_cert.py`. Still no MFA, lockout, per-device roles, PKI or mTLS. See IMPLEMENTATION_STATUS.

---

## TD-18 — PQC integration scope (*Phase 3*)

**Decision: option C, layered.** (A) ML-DSA-65 signed observations are the primary mechanism (authenticity, integrity, replay rejection, identity of the signing component). (B) An optional ML-KEM-768 session (client signs the handshake; server returns a key-confirmation tag; HKDF-SHA256; AES-256-GCM with counters) adds confidentiality and transport-level replay protection for the same signed envelopes. B never replaces A: the inner signature is always verified.

- **Identity:** the vision *software service* owns the ML-DSA identity, scoped to one source and a device list, registered by public key in the gateway DB. The USB webcam has no cryptographic identity, and nothing claims it does.
- **Signed bytes:** length-prefixed field encoding plus an ML-DSA context string; never a JSON serialization (`backend/protocol/canonical.py`).
- **Endpoints:** `GET /api/v1/pqc/gateway-key`, `POST /api/v1/pqc/session`, `POST /api/v1/observations/signed` (signature is the authentication), `POST /api/v1/observations/secure`. The Phase 2 token-only path stays for compatibility, is stored as `auth: ingest-token` and can be disabled with `REQUIRE_SIGNED_OBSERVATIONS=true`.
- **Keys:** sealed under HKDF subkeys of the master key; the vision service receives only its own key-encryption key (TD-15, `pqc/README.md`).
- **Domains unchanged:** ESP32 = HMAC-SHA256 (not PQC); PQC is not applied to any ESP32 path.
- **Not done / open:** dashboard visibility of `auth` labels, a persisted (non-in-memory) session store, TLS, throttling of failed-verification events, ESP32 PQC feasibility (R1). The session protocol is a composition of standard primitives and has had no external review.

---

## TD-19 — Dynamic trust engine (*Phase 4*)

**Decision:** a deterministic, rule-based, explainable engine specified in `docs/architecture/trust-engine.md`. That file was empty when Phase 4 began and was authored in this phase, so the specification itself needs review. It resolves the four TD-08 gaps: unavailable factors are excluded and reported (never assumed healthy); recovery is gated on authenticated device evidence in *credited* time; unauthenticated traffic acts only through a bounded pressure term (cap 25, so forged floods reach SUSPICIOUS at most); confidence scales AI-observation magnitude (`100*c^2`, floor 0.30, halved for token-only) but can never override authenticity.
- **Separation:** device identity (HMAC), vision-service identity / observation authenticity (ML-DSA), operator authentication and the ingest token stay separate; operator/ingest failures and gateway-side faults are not trust signals. The engine consumes gateway *records*, so trust computation lives outside the detector, camera, firmware and crypto code.
- **Architecture:** pull-based service with cursors in the DB (restart-safe, duplicate-safe) rather than an event bus; adapters are the only place that interprets records; the engine is pure logic.
- **Fail closed:** malformed, boundary-violating, non-finite or unknown input is rejected with a diagnostic and changes no score; a trust-engine fault never alters the gateway's authentication result.
- **Numbers:** weights, thresholds and hysteresis from TD-08; every other parameter is a documented design choice, not empirically derived.
- **TD-10 note:** the recovery states exist and transitions are validated, but nothing drives them; quarantine is *recommended*, not enforced (Phases 6-7).
- **Phase 4.1 review corrections:** (1) the exact score pipeline is normative in `trust-engine.md` section 4.7 (weights renormalised over available factors; coverage is reported only, so a high score can coexist with low coverage; worked examples are asserted in tests); (2) parameters are classified in section 16 as established project decisions (A), measured results (B), prototype design choices (C) and items needing empirical tuning (D); nothing was optimised or validated; (3) `RECOVERING` and `VERIFIED` are no longer dropped merely because the score is below 50 (that would have blocked Phase 7 remediation); they regress on revocation or a fresh authenticated fault report; VERIFIED → RECOVERED needs score ≥ 50 and RECOVERED → TRUSTED needs ≥ 85; (4) terminology: `visual_anomaly` is now `visual_rule_violation` (it is a configured-rule match, not an anomaly-detector output).
- **Open:** parameters need review and tuning against real data; whether TRUSTED should require a minimum coverage; Phase 6 must keep recording authenticated messages from quarantined/recovering devices so recovery can accrue credit; Phase 7 owns the recovery deadline.

---

## TD-20 — Phases 5–11 integration decisions (*continuous build*)

- **Attack simulation (Phase 5):** `attack_simulation/AttackSimulator` drives synthetic attacks over HTTP through the real gateway and reads the outcome back from the gateway's own security events, trust records and evidence chain; it asserts nothing itself. Credentialed attacks (tamper, sensor, config, malformed) model a compromised device that still holds its key. Every result is labelled `simulated`.
- **Enforcement boundary (Phase 6):** applied in the gateway *after* authentication (forged traffic can neither bypass nor trigger quarantine). QUARANTINED/RECOVERING/VERIFIED block the normal device channel (403) and open a separate HMAC-authenticated recovery channel whose reports are stored as trust evidence; RECOVERED restores normal access. Operator control actions use the operator token. Enforcement/control events are excluded from trust scoring (no feedback loop). On a trust-engine fault, enforcement uses the last in-memory state.
- **Recovery (Phase 7):** orchestrator around the existing state machine; requires a digital-twin expected state; remediation is a software "apply known-good configuration" command acknowledged by the device; health = N consecutive authenticated reports with tamper=false and twin MATCH; failure paths return to QUARANTINED (fault via the Phase 4.1 `recovery_fault`, deadline, revocation, ramp timeout). No physical repair, no firmware reflash, no attestation.
- **Evidence chain (Phase 8):** TD-09 design implemented locally: SHA-256 hash links + ML-DSA-65 signature per entry by a dedicated gateway evidence key (`gateway-evidence-1`, sealed under the master key). No external anchoring.
- **Digital twin (Phase 9):** minimal EXPECTED (operator) vs OBSERVED (authenticated self-reports) store; its expectations override the global trust config per device. Self-reported ≠ attested.
- **Dashboard (Phase 10), deviation from TD-14:** a static, no-build HTML/JS page served by the gateway at `/dashboard` instead of Vite+React+TS: nothing to install or build for a live demo, and it can only show what the operator API returns. All server strings are escaped (security events contain attacker-chosen values).
- **Demo (Phase 11):** `scripts/demo_full.py` runs the real gateway (uvicorn) on scratch state and tells the whole story over HTTP. The trust ramp needs ~40 min of clean evidence at the documented parameters; the demo advances the gateway clock and labels it TIME-LAPSE instead of changing parameters.
- **Engine correction found by the live demo:** see trust-engine.md §6.4 (out-of-order definition).

---

## TD-16 — Testing

`pytest` (installed 9.1.1) + `httpx`/FastAPI `TestClient`. Directory layout follows the existing `tests/` folders (`pqc`, `security`, `recovery`, `integration`, `end_to_end`) plus new `trust`, `evidence`, `digital_twin`, `ai`. ESP32 firmware is tested by (a) a shared canonical-JSON/HMAC test-vector file used by both firmware and gateway tests, and (b) a documented manual hardware checklist. A **software device agent** replays the ESP32 protocol so CI-style end-to-end tests run without hardware.

---

## Inconsistencies found in the existing repo (to fix, not yet changed)

1. `README.md` roadmap puts *Dashboard + mocked sensors* first; the brief puts ESP32↔backend first and dashboard last. The brief governs; update README roadmap when Phase 1 lands.
2. `.env.example`: `ML-KEM-512` (see TD-02), `ESP32_IP` (see TD-03), `SECRET_KEY` (TD-15). `EVIDENCE_LOG_DIR=evidence/sample/` combined with `.gitignore` `evidence/sample/*.json` is consistent but means evidence samples are never committed; fine, but note it.
3. `.gitignore` lacks `*.db`, `*.db-wal`, `*.pem`, `*.key`, `keys/`, `*.pt`, `*.pkl`, `*.onnx`, `secrets.h`, `.env` variants are present. Also duplicates (`build/`, `.vscode/`). Fix at the start of Phase 1.
4. README says "Vision models, anomaly detection, sensor data fusion" and lists ML-KEM/ML-DSA in the "PQC Module" without saying it is gateway-side; align with TD-01.
5. 20 of 30 tracked files are 0-byte stubs, including `trust-engine.md`, `self-healing.md`, `security-architecture.md`, `prior-art.md`, `pqc-notes.md`, `demo-plan.md`. The "read the architecture docs" step therefore yielded only `README.md` and `system-architecture.md`. These stubs are to be filled *before* the phase that depends on them.
6. `docs/architecture/system-architecture.md` shows the ESP32 sending telemetry "securely" into a "PQC Security Layer" and shows "Sensors / Camera" on the ESP32; both need qualifying per TD-01 and TD-12.
7. `docs/research/prior-art.md` is empty, so no novelty claim in `docs/hackathon/novelty.md` is currently backed by a survey. Do the survey before anything is called novel. "Unified application … is novel" in `novelty.md` should be softened to "we propose an integration of …".
8. The repo has no commits; 30 files are staged. Nothing was committed or altered by this session.
