# Q-SHIELD Implementation Roadmap

Status: **plan only, no implementation yet** (2026-09-24). Companion: `docs/technical-decisions.md` (decision IDs `TD-nn` referenced below).

## 1. Architecture overview

Closed loop: OBSERVE → DETECT → VERIFY → DYNAMIC TRUST → QUARANTINE → RECOVER → RE-AUTHENTICATE → VALIDATE → RESTORE TRUST.

```
ESP32 (physical endpoint)                Laptop (gateway / hub)
 BME280, MPU6050, reed switch            ┌────────────────────────────────────────────┐
 OLED / LED / buzzer                     │ API (FastAPI) ── auth/verify (security/)    │
 device state, tamper, counters          │   │                 │ HMAC or ML-DSA        │
        │  HTTP+JSON, signed envelope    │   ▼                 ▼                       │
        └───────────────────────────────►│ ingest → detectors (sensor, camera AI)      │
        ◄─ state + commands in response ─│   │                                         │
                                         │   ▼                                         │
 Camera (webcam first, TD-12) ──────────►│ trust engine ◄──► digital twin              │
                                         │   │      │                                  │
                                         │   ▼      ▼                                  │
                                         │ state machine ─► recovery orchestrator      │
                                         │   │                                         │
                                         │   ▼                                         │
                                         │ evidence chain (SHA-256 + ML-DSA) + SQLite  │
                                         │ WebSocket ──► dashboard (Phase 10)          │
                                         └────────────────────────────────────────────┘
 Attack simulator + software device agent: local only, talk to the same API.
```

### What runs where

| ESP32 | Laptop |
|---|---|
| Sensor acquisition (BME280, MPU6050, reed switch) | Backend API, SQLite |
| Telemetry + heartbeat, monotonic counter | HMAC and ML-DSA verification, ML-KEM sessions (real, gateway side) |
| HMAC-SHA256 message authentication (TD-01) | AI: camera detection, sensor anomaly detection |
| Tamper flag, device state, config/firmware hash reporting | Trust engine, digital twin, state machine |
| Local indication (LED, OLED, buzzer) reflecting gateway-issued state | Evidence chain, recovery orchestration |
| Safe-mode behaviour on command; apply signed config | Attack simulator, tests, dashboard |
| **Not:** ML-KEM/ML-DSA (research item R1) | Camera processing (unless ESP32-CAM is used, TD-12) |

## 2. Repository inspection summary

- 30 tracked files, all staged, **no commits yet**. 20 are 0-byte stubs; only `README.md`, `.env.example`, `.gitignore`, `LICENSE`, `system-architecture.md`, `problem-statement.md`, `novelty.md`, `bill-of-materials.md`, `ppt/README.md` have content.
- Directories exist for backend/ai/pqc/dashboard/attack_simulation/evidence/config/scripts/hardware; `tests/` has five empty subfolders (`pqc`, `security`, `recovery`, `integration`, `end_to_end`); no code anywhere.
- Empty and required before their phase: `trust-engine.md`, `self-healing.md`, `security-architecture.md`, `prior-art.md`, `pqc-notes.md`, `ai-security-notes.md`, `demo-plan.md`, `hardware-architecture.md`, `wiring-plan.md`.
- Inconsistencies: listed at the end of `docs/technical-decisions.md`.
- Environment *(verified)*: Python 3.12.0; FastAPI, Uvicorn, Pydantic, SQLAlchemy, pytest, httpx, numpy, scikit-learn, OpenCV, torch (CPU), ultralytics, `cryptography` already installed; Node 26.7.0; `pqcrypto` installable and working (see `pqc/README.md`). **Not installed:** PlatformIO/cmake/compiler, so ESP32 tooling must be installed in Phase 1. No ESP32 or sensors have been tested from this session.

## 3. Phases

Each phase ends with: code, tests, docs, how-to-run, acceptance criteria, known limitations. Order follows the brief; a **Phase 0** is added.

### Phase 0 — Foundations (½–1 day)
- Fix `.gitignore` and `.env.example` (see decisions doc), add `backend/requirements.txt` (pinned), package skeleton (`backend/{api,security,trust,recovery,evidence,digital_twin,devices,config}`), `pytest` config, shared enums/schemas (TD-07).
- Write the canonical-JSON + HMAC test-vector file used by firmware and gateway (TD-04).
- Install PlatformIO; blink/serial test on the ESP32.
- *Acceptance:* `pytest` runs (empty-green); ESP32 flashes and prints serial output.

### Phase 1 — ESP32 ↔ laptop vertical slice
- Gateway: enrollment script, `/api/v1/{register,heartbeat,telemetry}`, HMAC verify, counter/replay check, device table, `GET /api/v1/devices`.
- Firmware: Wi-Fi, HMAC-signed telemetry (temperature, vibration magnitude, reed tamper), heartbeat, counter persisted across resets, state returned in responses.
- Software device agent implementing the same protocol (enables hardware-free tests).
- *Acceptance:* `GET /api/v1/devices` shows `DEVICE-001`, `ONLINE`, temperature, vibration, tamper, `last_seen`; going offline flips to `OFFLINE` after a configured timeout; a modified or replayed packet is rejected and logged (crypto foundation for Phase 3).
- *Tests:* canonical-JSON vectors, valid/modified/replayed/unknown-device envelopes, online/offline transitions, plus a manual hardware checklist.

### Phase 2 — Camera + AI
- `FrameSource` (webcam → later ESP32-CAM), zone config (YAML/JSON), YOLO-nano person/object detector behind `Detector`, sensor anomaly detectors (range + rolling robust z-score), normalized events (TD-07).
- *Acceptance:* a person entering the configured zone produces a `person_in_zone` event with confidence and timestamp; a hand-warmed BME280 or a tap on the MPU6050 produces a sensor anomaly event; both appear via API.
- *Tests:* detector interface with recorded frames/series; no accuracy claims. Any measured metrics come from a documented recorded dataset.

### Phase 3 — PQC security
- `security/pqc.py` wrapper, key lifecycle (generate, encrypted-at-rest, rotate, revoke), ML-KEM session establishment + HKDF + AES-256-GCM, ML-DSA signed envelopes for the `pqc-mldsa-mlkem` profile, gateway-signed commands.
- KAT/ACVP conformance tests for the library.
- *Acceptance tests (required):* valid message accepted; modified message rejected; invalid signature rejected; unknown device rejected; invalid/corrupted KEM ciphertext yields no usable session; revoked session rejected.

### Phase 4 — Dynamic trust engine
- Write `docs/architecture/trust-engine.md` first (formula, weights, penalties, caps, decay, hysteresis), then implement TD-08. Every change stored as `{previous_trust, new_trust, reason, evidence_id, timestamp}` with per-factor deltas.
- *Acceptance:* baseline trust with no events; tamper, AI anomaly, signature failure each apply their documented penalty; recovery ramp works; threshold transitions incl. hysteresis. Deterministic: same event sequence ⇒ same scores (tested).

### Phase 5 — Attack simulation
Local-only (`127.0.0.1` allow-list). Each scenario is a file with **trigger, expected detection, expected trust impact, expected response, test**:

| # | Scenario | Expected detection |
|---|---|---|
| 1 | Packet tampering (27.4 → 97.4) | HMAC/ML-DSA verification fails, packet rejected, event, trust penalty |
| 2 | Invalid signature | same path, distinct event type |
| 3 | Replay | counter/nonce check |
| 4 | Rogue device | unknown `device_id` / unenrolled key, access denied |
| 5 | Physical tamper | reed switch event from real ESP32 (or agent) |
| 6 | Abnormal sensor behaviour | anomaly detector + twin range violation |
| 7 | Camera anomaly | AI event |
| 8 | Config integrity failure | reported `cfg_hash` ≠ twin expected |

Expected trust impacts are read from the trust model's tables, never hand-written into the scenario.

### Phase 6 — Quarantine
State machine (TD-10) with policy-enforced access per state; session revocation; transitions logged to evidence. *Tests:* every legal transition, illegal transitions rejected, access matrix per state.

### Phase 7 — Recovery
Write `docs/architecture/self-healing.md` first. Implement the sequence in TD-10 including the failure path (**stays QUARANTINED**), re-authentication, health checks over a configured window, gradual trust ramp. *Tests:* success, each individual check failing, recovery attempted with attack still active, reboot alone does not recover.

### Phase 8 — Evidence chain
TD-09 with verification tool `scripts/verify_evidence`. *Tests:* valid chain → VALID; altered historical event → INVALID at the correct sequence number; deleted middle entry → INVALID; bad signature → INVALID; tail truncation behaviour documented and tested against anchored head hash.

### Phase 9 — Digital twin
Per-device expected firmware/config hash, telemetry ranges, cadence, security state, last known healthy snapshot; `diff(expected, observed)` producing typed deviations that feed the trust engine. *Tests:* each deviation type.

### Phase 10 — Dashboard
Vite/React/TS per TD-14 against the real API. Trust timeline hero with reason for every change, plus the panels listed in the brief. Screenshots for the PPT are taken from real runs only.

### Phase 11 — End-to-end + demo hardening
One command runs NORMAL → ATTACK → DETECTION → QUARANTINE → RECOVERY → VERIFIED → RECOVERED against the software agent (CI-able) and, separately, against the real ESP32 (manual). Write `docs/hackathon/demo-plan.md` from what actually works. Record results and only then produce the PPT (`ppt/README.md` rules).

## 4. Dependencies

| Dependency | Needed by | Status |
|---|---|---|
| ESP32 board (variant unknown), USB cable, Wi-Fi | Phase 1 | Owned; variant **OPEN** |
| BME280, MPU6050, reed switch, OLED, LED, buzzer | Phase 1–2, 6–7 | Not yet acquired per BOM; Phase 1 can start with reed switch + on-board/temporary sensors, or the software agent |
| PlatformIO | Phase 0–1 | Not installed |
| `pqcrypto` | Phase 3 | Installs and works here |
| YOLO weights (network download once) | Phase 2 | Not downloaded |
| Camera decision (TD-12) | Phase 2 | **OPEN** |
| Router/hotspot where laptop and ESP32 share a LAN with client isolation off | Phase 1, demo | Unverified; hackathon Wi-Fi often blocks device-to-device traffic. Plan a phone hotspot or travel router as fallback. |

## 5. Risks

| # | Risk | Likelihood / impact | Mitigation |
|---|---|---|---|
| 1 | Judges read "PQC" as "ESP32 does PQC" | High / High (credibility) | TD-01 wording everywhere; dashboard labels HMAC vs ML-DSA sessions; R1 spike reported honestly whichever way it goes |
| 2 | PQC library correctness/maturity | Med / High | KAT tests; `liboqs-python` fallback; no FIPS claims |
| 3 | Sensors not yet in hand; ESP32-CAM pin/RAM limits | High / Med | Software device agent; webcam first; phased BOM |
| 4 | Venue Wi-Fi client isolation | Med / High for demo | Own hotspot/router; demo works over loopback with agent as fallback |
| 5 | Scope: 11 phases for a hackathon | High / High | Vertical slice first; Phases 6+7+8 minimal versions before polishing 2 and 10; cut order: ESP32-CAM, IsolationForest, servo, OLED |
| 6 | Trust score looks arbitrary | Med / High | Formula documented before code; weights disclosed as design choices; deterministic tests; no tuning for slides |
| 7 | Self-reported firmware/config hash from a compromised device is not proof | Certain / Med | State as limitation; secure boot only described, not enabled (irreversible eFuses) |
| 8 | False positives from camera/sensor detectors trigger quarantine mid-demo | Med / High | Corroboration rules (single low-confidence AI event cannot alone cross quarantine threshold), tested |
| 9 | AGPL Ultralytics licence | Low–Med / Med | Disclose; detector is swappable |
| 10 | Novelty claims unsupported (prior-art empty) | Med / Med | Do the survey; wording "proposed integration"; never "first" |
| 11 | Windows-only verification of tooling | Med / Low–Med | Note platform on every result; test on the demo machine |
| 12 | Gateway is a single point of trust (key + DB on one laptop) | Certain / Med | Documented in security architecture; out of scope for prototype |

## 6. Testing strategy

- **Unit** (`pytest`): canonical JSON, envelope verify, PQC wrapper (+KAT), trust rules, state machine, evidence chain, twin diff, detectors on recorded fixtures.
- **Required security tests** are the ones in the brief (valid / modified / invalid signature / unknown device; replay; trust; recovery; evidence).
- **Integration:** FastAPI `TestClient` with the software device agent: telemetry → detection → trust → quarantine → recovery.
- **End-to-end:** the full attack-to-recovery scenario, deterministic seeds, evidence chain verified at the end.
- **Hardware:** manual checklist per firmware release (reed open/close, vibration tap, heat, power-cycle counter persistence, Wi-Fi drop and reconnect). Results are recorded with date and firmware hash; unrecorded results are not cited.
- No benchmark or accuracy figure is published without the dataset, method and raw output kept in the repo.

## 7. Demo strategy

Two runnable modes from one script set: **(a) software-agent mode** (no hardware, deterministic, used in CI and as fallback) and **(b) hardware mode** (real ESP32, real reed switch/sensors, real camera). Sequence per the brief: baseline TRUSTED → open enclosure (tamper) → abnormal camera/sensor → modified telemetry rejected → rogue device denied → trust crosses quarantine threshold → session revoked, evidence preserved → recovery steps → trust ramps → RECOVERED, then verify the evidence chain live, and show a deliberately corrupted copy failing verification. Reset script returns to a clean baseline. Trust numbers displayed are whatever the model outputs.

## 8. Research questions

- **R1:** Can ML-DSA verification (and ML-KEM decapsulation) run on our ESP32 variant with acceptable RAM/time, using an audited embedded implementation (e.g. PQClean/mlkem-native-style C)? What RNG quality and side-channel caveats apply? Outcome determines whether "PQC-authenticated ESP32" can ever be claimed.
- **R2:** Prior-art survey (fill `docs/research/prior-art.md`): PQC for IoT, zero-trust/continuous-trust IoT, IoT digital twins for security, self-healing IoT, tamper-evident logging. Every citation checked at source.
- **R3:** Which current authoritative sources define the parameter choices (FIPS 203/204) and any IoT PQC guidance; verify against NIST publications before quoting.
- **R4:** Is `pqcrypto` conformant (KAT) and does it work on the demo OS?
- **R5:** Trust weights/penalties: what evidence supports the initial values? Plan: sensitivity analysis on recorded runs, reported as such.
- **R6:** ESP32 anti-rollback/attestation options for making `fw_hash` trustworthy.
- **R7:** ESP32-CAM viability alongside the sensors (TD-12).

## 9. Global acceptance criteria (prototype "done")

1. Real ESP32 telemetry visible end to end (Phase 1 acceptance).
2. Real ML-KEM/ML-DSA operations in the gateway with the four required negative tests passing.
3. Trust engine deterministic and documented, every change carrying a reason and evidence ID.
4. All eight attack scenarios have trigger/detection/trust/response/test, and tests pass.
5. Quarantine and recovery run through the state machine; failed recovery stays quarantined (tested).
6. Evidence chain verifies, and detects a modified event (tested).
7. Dashboard shows the required panels from live data.
8. Full scenario reproducible from a single documented command sequence.
9. README/docs state limitations and the ESP32-vs-gateway PQC split.

## 10. Recommended first step

**Phase 0 then Phase 1**, starting with the software device agent plus gateway (works today with no hardware) in parallel with installing PlatformIO and flashing the ESP32. Two things to settle first: the camera type (TD-12) and the ESP32 board variant (TD-13).
