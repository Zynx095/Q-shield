# Q-SHIELD: verified fact sheet for the presentation

## 0. Current figures (Phase 17, 2026-10-02), used in the final Quant-A-Maze deck

Sections 1 to 11 below are the **2026-09-24 snapshot** (Phases 0-3). They are kept because the earlier decks
were built from them. **Where they conflict with this section, this section wins.**

| Fact | Value | Source |
|---|---|---|
| Python tests | 785 passed, 0 failed | `python -m pytest -o addopts="" -q` (2026-10-02) |
| JavaScript tests | 40 passed | `node --test dashboard/tests/*.test.mjs` |
| Tests by area | trust 235, security 149, AI 135, full stack 111, PQC 74, integration 47, twin 18, evidence 15, end to end 1 | `pytest --collect-only`, `docs/testing.md` |
| NIST ACVP vectors | 70 agree (35 ML-KEM-768 decapsulation, 20 key checks, 15 ML-DSA-65 verifications) | `pqc/README.md`, section 4 below |
| PQC medians (ms, i7-13700HX laptop) | ML-KEM-768 keygen 0.060, encapsulate 0.069, decapsulate 0.091; ML-DSA-65 sign 9.42, verify 0.188; full handshake 10.0 | `docs/results/pqc-benchmark.json` |
| Sizes (B) | ML-KEM-768 public key 1184, ciphertext 1088, shared secret 32; ML-DSA-65 signature 3309 | same |
| Trust engine | 52.6 µs mean per update; about 0.7 ms per gateway record | `docs/results/trust_bench.json` |
| Live demo (USB webcam) | 100 → 90 (real detections) → 80 (forged) → 72 SUSPICIOUS (replay) → 30 QUARANTINED (tamper + signed visual) → VERIFIED 30 → RECOVERED 80 (30 min credited, time-lapse) → TRUSTED 85 (42 min); evidence chain 26 entries, VERIFIED | `docs/IMPLEMENTATION_STATUS.md`, Phase 17 |
| Live camera | USB webcam index 1, YOLO11n on CPU, about 5 frames/s (449 frames in 90 s), no failed reads, no false camera-health report in 2 x 90 s with a person moving | same |
| Rejection flood | 300 forged messages leave 8 rows (6 samples + 2 coalesced); trust decisions identical to unsampled | `tests/fullstack/test_rejection_flood.py` |
| Session churn | 30 refused observations: 1 session (was 30) | `tests/integration/test_vision_session_churn.py` |
| Device vectors | 7 byte-exact cases, accepted in order by a gateway | `tests/vectors/envelope_v1_cases.json` |

**Never claim:**
- hardware attestation;
- ESP32 validation (the firmware has never been compiled);
- a distance from the camera (proximity is image-space);
- external anchoring of the evidence chain;
- production readiness;
- detection accuracy;
- that the device path is post-quantum.

---

## Snapshot of 2026-09-24 (historical)

Everything on a slide must come from this file. Each number names the file it comes from. Verified against the repository on 2026-09-24 (`python -m pytest`: 347 passed). If a number is not here, it is not allowed on a slide.

## 1. Milestone

| Phase | State | Evidence |
|---|---|---|
| 0 foundation (config, credentials, protocol, test infrastructure) | complete | `backend/README.md`, `docs/technical-decisions.md` |
| 1 device slice (software device agent, gateway, HMAC auth, replay protection) | complete | `backend/README.md`, `tests/security/test_device_auth.py`, `tests/integration/test_phase1_flow.py` |
| Hardening (encrypted credential store, operator/ingest tokens) | complete | TD-15, TD-17 in `docs/technical-decisions.md` |
| 2 vision (webcam, YOLO11n, zones, observation schema) | complete | `ai/README.md` |
| 3 PQC (ML-KEM-768, ML-DSA-65, signed observations, sessions, keys) | complete | `pqc/README.md` |
| 4 trust engine | **specification not yet written; nothing implemented** | `docs/architecture/trust-engine.md` is empty |
| Quarantine, recovery, evidence chain, digital twin, attack simulation, dashboard | **not implemented** | roadmap only |
| ESP32 hardware | **firmware skeleton is untested; no board has been connected or flashed; board variant unknown** | `hardware/esp32/README.md` |

Nothing is committed to git yet (all files are staged or untracked).

## 2. Tests (`python -m pytest`, run 2026-09-24)

- **347 passed, 0 failed.**
- 182 tests existed before Phase 3 and are unchanged and passing (31 device slice + 28 hardening + 123 vision).
- 165 tests added in Phase 3 (65 PQC conformance/interop/behaviour + 100 signed observations/sessions/keystore/sink/provisioning).
- Chart: `ppt/assets/08_test_summary.png` (counts are collected by pytest when the chart is generated).
- The signature-rejection tests were confirmed to fail when verification is sabotaged to always return true (Phase 3 check).

## 3. Cryptography

| Item | Value | Source |
|---|---|---|
| ESP32 device authentication | HMAC-SHA256, provisioned per-device secret, counter replay protection. **Not post-quantum.** No confidentiality. | `backend/protocol/envelope.py`, `pqc/README.md` |
| Key establishment | ML-KEM-768 (FIPS 203) | `pqc/README.md` |
| Signatures | ML-DSA-65 (FIPS 204), context string for domain separation | `pqc/README.md` |
| Library | `pqcrypto` 1.0.0, Apache-2.0; Rust crates `backbone-ml-kem` 0.2.0 / `backbone-ml-dsa` 0.2.0; not audited by us; verified on Windows x86-64 only | `pqc/README.md` |
| Session encryption | AES-256-GCM, HKDF-SHA256, counters; composed from standard primitives, **not TLS, not externally reviewed** | `backend/security/session.py`, `pqc/README.md` |
| Sizes (bytes) | ML-DSA-65 signature 3309; ML-DSA-65 public key 1952, secret key 4032; ML-KEM-768 ciphertext 1088, public key 1184, secret key 2400, shared secret 32 | `docs/results/pqc-benchmark.json` |
| Where PQC is used | vision service (ML-DSA identity), gateway (verification, ML-KEM session endpoint). **Not on any ESP32 path.** | `pqc/README.md` |
| Vision-service identity | belongs to the vision **software service**, scoped to one source and a device list; the webcam has no cryptographic identity | `pqc/README.md` |

## 4. NIST conformance evidence

Source: NIST ACVP-Server, commit `975de31eb83d87039ec88934fdc47d8c312b892d`; vectors copied verbatim (`scripts/fetch_acvp_vectors.py`); source hashes in `tests/vectors/pqc/MANIFEST.json`.

| Check | Cases | Result |
|---|---|---|
| ML-KEM-768 decapsulation | **35** (10 decapsulation validation + 25 NIST ciphertexts from the encapsulation group) | all match |
| ML-KEM-768 key validity | **20** (10 encapsulation-key + 10 decapsulation-key checks; valid and invalid) | library agrees with NIST on all |
| ML-DSA-65 verification | **15** (**3 valid, 12 invalid**) | all agree |
| Interop | pure-Python `kyber-py` 1.2.0 / `dilithium-py` 1.4.0 pass the same vectors and interoperate with `pqcrypto` in both directions (test-only libraries) | pass |

Not covered and **not claimed**: keygen, signing and encapsulation known-answer tests (this library takes no seed), pre-hash mode, other parameter sets, side channels, independent audit. **No FIPS 140 validation.** Chart: `07_nist_conformance.png`.

## 5. PQC benchmarks (measured)

Machine: 13th Gen Intel Core i7-13700HX, Windows 11 x86-64, Python 3.12.0, pqcrypto 1.0.0. 300 calls x 5 rounds per operation after warm-up (`docs/results/pqc-benchmark.json`, `scripts/bench_pqc.py`). Laptop numbers only; nothing about ESP32.

| Operation | median ms |
|---|---|
| ML-KEM-768 keygen | 0.060 |
| ML-KEM-768 encapsulate | 0.069 |
| ML-KEM-768 decapsulate | 0.091 |
| ML-DSA-65 keygen | 0.232 |
| ML-DSA-65 sign | 9.42 |
| ML-DSA-65 verify | 0.188 |
| Full session handshake (client + server, in process) | 10.0 |

Signing is about 50x slower than verification in this library; cause not investigated. Chart: `05_pqc_benchmark.png`.

## 6. Vision

| Item | Value | Source |
|---|---|---|
| Model | YOLO11n, 5.6 MB checkpoint (5,613,764 bytes), weights sha256 `0ebbc80d...644ee1` | `ai/README.md` |
| License | **AGPL-3.0** (ultralytics package and checkpoint); repo is MIT; weights not committed; no legal review | `ai/README.md`, TD-11 |
| Input | 640x480 webcam, `imgsz` 640 configured | `ai/README.md` |
| Throughput at 640 | 25.1 inference-only FPS, 21.0 end-to-end FPS (inference 39.8 ms mean) | `ai/README.md` |
| Throughput at 320 | 51.4 inference-only FPS, 30.0 end-to-end FPS (inference 19.5 ms mean) | `ai/README.md` |
| Conditions | CPU only (no CUDA), 100 frames per run, one run each, **no person in view (0 detections)** | `ai/README.md` |
| Accuracy | **not measured; no accuracy, precision, recall or false-positive figure exists** | `ai/README.md` |
| Output | normalized observations (`visual_observation`, `camera_health`), zone rules, `anomaly` flag = "matched a configured rule", **not a trust decision** | `backend/protocol/observation.py` |
| Frames | never stored or transmitted; only observations leave the process | `ai/README.md` |

Chart: `06_vision_performance.png`. **Never call these accuracy benchmarks.**

## 7. Real run evidence (`docs/results/live-run-phase3.json`)

Real USB webcam + real YOLO11n + real gateway + ML-KEM session + ML-DSA-signed observations, 2026-09-24.
- **11 observations stored, all labelled `ML-DSA-65:vision-1`.** 1 session handshake (HTTP 200), 11 signed observations in the session (HTTP 200).
- **Modified payload: HTTP 401** (security event `pqc_invalid_signature`, severity high). **Exact replay: HTTP 409** (event `pqc_observation_replay`, severity medium).
- Offline re-verification of all 11 stored signatures: 11/11 valid; an altered copy of each: 11/11 rejected.
- Scene: **no person in view.** Detections were 8 chair and 3 potted plant observations (via a scratch config widening the object classes, confidence range 0.318-0.618 in the export), 0 anomalies flagged. The person-in-restricted-zone path has **not** been run live (it is covered by tests with a fake detector).
- Replay caveat: a replay older than the 300 s freshness window is rejected as stale (HTTP 401), not 409. Both are rejections.
- No screenshots exist. Do not present any as real. Use `03_signed_observation_flow.png` (generated from the evidence file).

## 8. Gateway and security behaviour that exists

- Device endpoints (`register`, `heartbeat`, `telemetry`): HMAC envelope; failures return a generic 401 and are logged with a reason code (`invalid_tag`, `unknown_device`, `replay_or_stale_counter`, `revoked_device`, ...).
- Operator APIs need an operator bearer token; observation ingest uses a separate ingest token or an ML-DSA signature. Three mechanisms, none substitutes for another.
- Device secrets are encrypted at rest (AES-256-GCM under a master key); PQC private keys are sealed under HKDF subkeys; provisioning, rotation and revocation via `scripts/pqc_provision.py`.
- Signed observations: fields are length-prefix encoded (never a JSON serialization), verified in a fixed order, replay and freshness enforced (+/-300 s).
- Observations are stored with an `auth` label (`ML-DSA-65:<signer>` or `ingest-token`); the token-only path can be disabled.

## 9. What does NOT exist yet (say so plainly)

Trust engine and any trust score; device state machine (TRUSTED/SUSPICIOUS/QUARANTINED/...); quarantine; session revocation on trust loss; recovery/self-healing; evidence chain; digital twin; attack-simulation suite; dashboard; ESP32 telemetry from real hardware; ESP32 PQC; prior-art survey (`docs/research/prior-art.md` is empty); scalability measurements (one device, one camera); accuracy measurements.

## 10. Limitations to state (short list)

Single laptop trust domain (gateway, keys, DB, vision service on one host); tokens travel over plain HTTP on a trusted LAN; session store in memory; signing latency ~9 ms; library audit status unknown and only Windows x86-64 tested; AGPL-3.0 model licence; camera-obstruction thresholds unvalidated; HMAC device path has no confidentiality and is not post-quantum; only a software device agent has exercised the device path.

## 11. Wording

**Say:** "quantum-resistant", "post-quantum cryptography", "ML-KEM-768 and ML-DSA-65", "prototype", "demonstrated in a controlled local run", "defined threat model", "proposed integration".
**Say for the ESP32:** "Q-SHIELD introduces a post-quantum security layer using ML-KEM-768 and ML-DSA-65 while retaining HMAC-SHA256 for the current ESP32 device-authentication prototype."
**Never say:** "quantum-proof", "unhackable", "100% secure", "the ESP32 is quantum-safe", "the device is secured against quantum attacks", "first", "novel algorithm", "self-healing works", "trust score" (as a built feature), "accuracy" for any FPS number, "FIPS validated".
