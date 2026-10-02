# Q-SHIELD: final Quant-A-Maze 3.O deck, slide-by-slide plan

**Design authority.** The official template is `ppt/Quant-A-Maze.pptx`. Every slide keeps its chrome: the NITTE
logo, the QUANT-Λ-MAZE 3.0 logo, the Q-BITS logo, the orange band, the right-hand halftone strip, the bottom band
and the white background.

**Template mapping.**
- The six official section headings are kept word for word, and each opens its section: "1. Participant
  Information & Topic Name", "2. Problem Definition", "3. Proposed Solution & Execution Plan", "4. Technical
  Design", "5. Feasibility & Innovation", "6. Expected Outcome".
- Every other slide carries its section's heading as a small marker, so the official structure reads through the
  whole deck.
- The suggested 29-slide story is folded into 24 slides:
  - "why authentication is not enough" and the threat model share slide 3;
  - "session security" and quarantine share slides 12 and 17;
  - "device → gateway → trust engine" is part of slides 6 and 8.

**Numbers.** Every number is from the repository, with its source given in the speaker notes. Benchmarks are laptop
numbers. Nothing is claimed for the ESP32.

**Type and colour.**
- Titles: Bahnschrift SemiBold, 40 pt.
- Body: Segoe UI, 20 to 24 pt.
- Technical labels: Consolas, 16 to 18 pt.
- Smallest text: 15 pt. The canvas is 20 x 11.25 in, so 15 pt reads like 10 pt on a standard slide.
- Accent: the template's orange `#FF914D` for fills and lines. Orange text uses a darker `#C2410C`, for contrast on
  white.

---

## Section 1: Participant information

### 1. 1. Participant Information & Topic Name *(official heading)*
- **Objective:** identity and track at a glance; the template's own fields.
- **Bullets:**
  - Team name, team lead name, team lead contact: left as **[ to fill ]** (not supplied; never invented).
  - Selected track: **Post-Quantum Cryptography (PQC)**, highlighted. The other three tracks are listed, greyed.
  - Topic: **Q-SHIELD: continuous device trust with post-quantum-signed evidence.**
  - One line: "Authentication answers *who are you* once. Q-SHIELD keeps asking *can you still be trusted*."
- **Visual:** the template's watermark, kept. A small three-node strip on the right: device → gateway → trust.
- **Speaker emphasis:** the one-line idea.
- **Do not crowd:** no architecture here.

## Section 2: Problem definition

### 2. 2. Problem Definition *(official heading; sub-point: Problem Description)*
- **Objective:** authenticated does not mean trustworthy.
- **Bullets:**
  - A device passes authentication, then its enclosure is opened, its configuration changes, its camera is
    blinded, or its traffic is forged or replayed.
  - One-time authentication cannot see any of that. It keeps trusting.
  - Evidence recorded today must also survive "harvest now, decrypt later".
- **Diagram:** a timeline. Login ✓ at t0, then four compromise events after t0, each marked "authentication: still
  OK". An orange bracket marks "trust should change here".
- **Technical labels:** `t0 authenticate`, `enclosure opened`, `config drift`, `camera blinded`, `forged / replayed`.
- **Speaker emphasis:** "Who are you" versus "can you still be trusted".
- **Do not crowd:** at most four events.

### 3. Why authentication alone is not enough: threat model
- **Objective:** name the attacks and what answers each.
- **Table, three columns (threat | what authentication sees | what Q-SHIELD adds):**
  - Forged message: rejected, but the attempt goes unnoticed. Adds a security event plus bounded pressure (≤ 25).
  - Replayed message or observation: rejected. Adds pressure, and a repeated-replay cap (65) after 3 in 10 min.
  - Physical tamper (enclosure open): nothing. Adds a tamper signal (CRITICAL) and cap 55.
  - Camera covered, frozen or turned: nothing. Adds a signed camera-health report (HIGH on the visual factor).
  - Tamper plus visual evidence: nothing. Adds a confirmed incident: cap 30, **quarantine**.
  - Quantum adversary recording traffic: classical signatures are at risk. ML-DSA-65 signs the evidence; ML-KEM-768
    protects the session.
- **Speaker emphasis:** unauthenticated noise can never quarantine a device. Correlated authenticated evidence can.
- **Do not crowd:** six rows maximum, one line each.

### 4. Functional requirements and constraints *(sub-points: Functional Requirements, Constraints)*
- **Objective:** what the system must do, and what limits it.
- **Requirements:** continuous scoring from six evidence factors; cross-modal correlation; enforcement at the
  gateway; earned recovery; a tamper-evident evidence chain; post-quantum signatures on the evidence path.
- **Constraints:**
  - IoT-class devices: the device path is HMAC-SHA256 (not post-quantum).
  - No hardware attestation.
  - Laptop gateway (FastAPI and SQLite).
  - Physical hardware not yet available: device telemetry is simulated.
  - Trust parameters are design choices, not calibrated.
- **Visual:** two columns: requirements with orange checkmark nodes, constraints with grey nodes.
- **Speaker emphasis:** the constraints are stated up front, not hidden.

## Section 3: Proposed solution and execution plan

### 5. 3. Proposed Solution & Execution Plan *(official heading; sub-point: Solution Overview)*
- **Objective:** the core idea as a closed loop.
- **Diagram:** a ring of six nodes:
  - OBSERVE (device and camera)
  - VERIFY (HMAC, ML-DSA-65)
  - SCORE (trust engine)
  - ENFORCE (quarantine at the gateway)
  - RECOVER (verified, earned)
  - PROVE (signed evidence chain)

  The centre reads "continuous trust".
- **Execution strip, along the bottom:**
  - Phases 0-3: protocol and PQC;
  - Phase 4: trust engine;
  - Phases 5-11: attacks, quarantine, recovery, evidence, twin, demo;
  - Phases 12-17: operators, UI, hardening, the camera as a security boundary.
- **Speaker emphasis:** the novelty is the loop, not one algorithm.

### 6. Working principle: system architecture *(sub-point: Working Principle / Approach)*
- **Objective:** required diagram 1.
- **Diagram (top to bottom):**
  - ESP32 / DEVICE AGENT → IDENTITY (HMAC-SHA256 + counter)
  - VISION SERVICE → PQC SESSION (ML-KEM-768) → SIGNED OBSERVATIONS (ML-DSA-65)
  - both → GATEWAY → TRUST ENGINE → DECISION, which forks:
    - TRUSTED
    - QUARANTINE → RECOVERY → VERIFIED / TRUSTED
  - Side rail: digital twin and evidence chain.
- **Labels:** `HMAC-SHA256`, `ML-KEM-768`, `ML-DSA-65`, `AES-256-GCM`, `403 normal channel`.
- **Speaker emphasis:** the device path and the vision path authenticate differently and never interchangeably.

### 7. Core functionality: the six-factor trust model
- **Objective:** required diagram 2.
- **Diagram:** six factor nodes with weights:
  - identity_crypto 25%
  - physical 20%
  - config_integrity 15%
  - sensor_consistency 15%
  - visual 15%
  - network 10%

  They feed a weighted sum, then **− pressure (≤ 25)**, then **min(caps)**, giving the **score**.
- **Side note:** authenticity is a precondition, never a bonus. A perfect signature cannot raise trust.
- **Speaker emphasis:** every change lists the reasons that sum to it.

### 8. Continuous trust scoring: thresholds, caps, recovery
- **Objective:** how the score turns into a state.
- **Formula (Consolas):** `raw = 100 − Σ wᵢ·pᵢ` and `final = min(raw − pressure, caps)`.
- **State bar:** TRUSTED ≥ 80; SUSPICIOUS 50-79; QUARANTINED < 50; re-entry to TRUSTED at 85 (hysteresis).
- **Caps:** confirmed incident 30; tamper 55; correlated 55; repeated replay 65; integrity 65; stale 79.
- **Recovery:** only clean authenticated device evidence credits time; intervals with a violation earn nothing.
- **Speaker emphasis:** silence never heals a device.

## Section 4: Technical design

### 9. 4. Technical Design *(official heading; sub-point: Technologies / Algorithms)*: why PQC and where
- **Objective:** the cryptography map.
- **Chain:** WHY PQC → ML-KEM → SESSION → ML-DSA → SIGNED EVIDENCE → AES-GCM → CONTINUOUS TRUST.
- **Table (use | algorithm | standard):**
  - session key: ML-KEM-768, FIPS 203;
  - observation and evidence signatures: ML-DSA-65, FIPS 204;
  - key schedule: HKDF-SHA256;
  - session data: AES-256-GCM;
  - chain links: SHA-256;
  - device: HMAC-SHA256 (not PQC).
- **Numbers:** 70 NIST ACVP cases agree (35 ML-KEM decapsulation, 20 key checks, 15 ML-DSA verifications).
- **Speaker emphasis:** PQC protects the *evidence*. The device path is honest HMAC.

### 10. ML-KEM-768 handshake flow
- **Objective:** required diagram 3.
- **Diagram (two lanes, vision service | gateway):**
  - KEY GENERATION (gateway, provisioned)
  - → pinned public key (1184 B)
  - → ENCAPSULATION
  - → CIPHERTEXT (1088 B), in an init signed with ML-DSA-65
  - → DECAPSULATION
  - → SHARED SECRET (32 B)
  - → HKDF-SHA256 (salt: both nonces; info: transcript)
  - → key confirmation
  - → AES-256-GCM SESSION (per-direction keys, 64-bit counters, AAD = session ‖ direction ‖ counter)
- **Numbers (laptop, median):** encapsulate 0.069 ms, decapsulate 0.091 ms, full handshake 10.0 ms.
- **Speaker emphasis:** a wrong pinned key fails key confirmation; nothing is sent.

### 11. ML-DSA-65 signed observation flow
- **Objective:** required diagram 4.
- **Diagram:**
  - OBSERVATION
  - → CANONICAL ENCODING (length-prefixed, never JSON)
  - → ML-DSA-65 SIGN (context `qshield/signed-observation/v1`)
  - → SIGNATURE (3309 B)
  - → GATEWAY → VERIFY, which forks:
    - ACCEPT (200)
    - REJECT: 401 forged, 409 replayed, stale or future, unknown, retired or unauthorised signer
- **Numbers:** sign 9.42 ms, verify 0.188 ms (median, laptop).
- **Speaker emphasis:** the signature binds the signer to the source and device scope.

### 12. Session security and abuse resistance
- **Objective:** what an attacker can and cannot do to the transport.
- **Table (attack | control | evidence):**
  - Replayed handshake: one-use nonce, reserved atomically (tested).
  - Replayed or reordered session message: strict counters.
  - Gateway lost the session: `401 session_expired` → one re-handshake.
  - Persistent refusals: the observation is dropped and the session kept. 30 refusals now cost 1 session (was 30).
  - Session-table exhaustion: cap of 64, client budget of 20 handshakes per hour, backoff 1-60 s.
  - Rejection flood: 3 samples per sender per 10 s, then coalesced. 300 forged messages leave 8 rows, with the
    count kept.
- **Speaker emphasis:** a flood changes neither storage growth nor the trust decision.

### 13. AI vision security
- **Objective:** required diagram 6.
- **Diagram:** CAMERA → YOLO11n → OBJECT / CONFIDENCE / ZONE → CAMERA HEALTH → SIGNED OBSERVATION → TRUST ENGINE.
- **Bullets:**
  - The detector reports; it never decides trust.
  - A rule match is a policy match (restricted class in restricted zone), not an "AI verdict".
  - The webcam has no key: the vision service holds the ML-DSA identity.
- **Numbers:** live USB camera, about 5 frames/s on CPU (Phase 17 run). Detection accuracy is **not measured**.

### 14. Camera tamper and anomaly model
- **Objective:** required diagram 7. The camera is part of the boundary.
- **Diagram:** NORMAL → OCCLUDED → MOVED (viewpoint shift) → TOO CLOSE → VIEW CHANGED → CORRELATED INCIDENT, each
  with how it is measured and what trust does:
  - occluded: dark with no reference structure, flat, or overexposed, for ≥ 2 s; HIGH.
  - moved: phase-correlation shift, or similarity under 0.7 with detected people masked; HIGH.
  - frozen: identical frames; HIGH.
  - degraded: low light with the structure still present, or blur; MEDIUM.
  - too close: box over 35% of the frame. An image-space heuristic, **not a distance**; LOW.
  - with tamper inside 60 s: **confirmed incident → quarantine**.
- **Speaker emphasis:** a camera alone never quarantines. A blinded camera plus an opened enclosure does.
- **Do not crowd:** six states, one line each.

### 15. Digital twin
- **Objective:** required diagram 8.
- **Diagram:** EXPECTED | OBSERVED | verdict, one row each:
  - firmware: agent-0.1 vs agent-0.1, MATCH
  - configuration: cfg-good-1 vs cfg-tampered, MISMATCH
  - capabilities: MATCH
  - temperature: −20 to 60 °C vs 27.4, MATCH
  - tamper: closed vs open, MISMATCH
- **Bullets:** expectations are set by an operator; observations are authenticated self-reports; recovery judges
  each report on its own content.
- **Speaker emphasis:** a match is evidence, not attestation.

### 16. Evidence chain and forensics
- **Objective:** required diagram 5.
- **Diagram:**
  - EVENT N, hash
  - → EVENT N+1 (prev = hash N)
  - → EVENT N+2 (prev = hash N+1)
  - → ML-DSA-65 SIGNATURE on each entry (context `qshield/evidence/v1`)
  - → VERIFICATION: recompute every hash, check every signature
  - → detects edit, reorder, removal from the middle (tail truncation needs an external head copy)
- **Number:** the live demo ended with 26 entries, chain VERIFIED.
- **Speaker emphasis:** not anchored externally. Whoever holds the database *and* the key could rewrite it.

### 17. Quarantine enforcement
- **Objective:** what quarantine means on the wire.
- **Table (state × channel):**
  - TRUSTED, SUSPICIOUS, RECOVERED: normal allowed, recovery refused.
  - QUARANTINED, RECOVERING, VERIFIED: normal **403**, recovery allowed.
  - Forged "all clear": **401** before enforcement.
- **Speaker emphasis:** enforcement comes after authentication, so forged traffic can neither trigger nor bypass it.

### 18. Self-healing recovery
- **Objective:** required diagram 10.
- **Diagram:** QUARANTINE → RECOVERY AUTHORIZATION (operator) → REMEDIATION (known-good config, acknowledged) →
  HEALTH CHECKS (3, each report judged alone) → TWIN MATCH → VERIFIED → RECOVERED (≥ 50, normal channel back) →
  TRUSTED (≥ 85).
- **Failure rail:** any authenticated fault, the 15-min verification deadline or the 2-h ramp deadline →
  QUARANTINED.
- **Speaker emphasis:** trust is earned back, not granted. Software remediation only.

### 19. Technology stack
- **Objective:** required diagram 11.
- **Groups (technology: role):**
  - Cryptography: pqcrypto (ML-KEM-768, ML-DSA-65); `cryptography` (AES-256-GCM, HKDF); HMAC-SHA256.
  - AI / vision: OpenCV (capture), YOLO11n via ultralytics (detection), NumPy (camera-health statistics).
  - Backend: FastAPI and uvicorn (gateway), Pydantic (schemas), the trust engine (pure Python).
  - Frontend: vanilla ES modules, no build (dashboard, presentation mode).
  - Database: SQLite (events, observations, twin, evidence chain).
  - Deployment: a single laptop gateway, optional TLS.
  - Hardware: ESP32 firmware skeleton, BME280, MPU6050 and reed switch (planned).

## Section 5: Feasibility and innovation

### 20. 5. Feasibility & Innovation *(official heading; sub-point: Technical Feasibility)*
- **Objective:** what is real, and what is simulated.
- **Two-column ledger:**
  - REAL: ML-KEM-768, ML-DSA-65, AES-256-GCM, HKDF-SHA256, the SHA-256 chain, YOLO11n with a camera, trust engine,
    recovery engine, digital twin, dashboard, browser camera preview.
  - SIMULATED: device telemetry (software agent), attacks (attack simulation), the ESP32 deployment, physical
    sensors.
- **Speaker emphasis:** the hardware is an adapter step, not a redesign (same protocol, byte-exact vectors).

### 21. Performance and testing *(sub-point: Scalability / Performance)*
- **Objective:** verified numbers only.
- **Tests:** 785 Python passing, 40 JS passing. By area: trust 235, security 149, AI 135, full stack 111, PQC 74,
  integration 47.
- **PQC (median ms, i7-13700HX laptop):** ML-KEM-768 keygen 0.060, encapsulate 0.069, decapsulate 0.091; ML-DSA-65
  sign 9.42, verify 0.188; handshake 10.0.
- **Trust engine:** about 53 µs per signal (mean), about 0.7 ms per gateway record.
- **Scalability honestly:** a single gateway on SQLite; multi-gateway is not built.
- **Visual:** a horizontal bar chart of the PQC medians, on a log-free linear scale grouped by algorithm, plus test
  tiles.

### 22. Innovation / USP *(sub-point: Innovation / USP)*
- **Objective:** what is different.
- **Five points:**
  - Continuous, explainable trust: every change sums its reasons.
  - Authenticity is not trust: signatures gate the evidence and never add trust.
  - The camera as part of the security boundary: covered, frozen or turned is evidence.
  - Bounded griefing: forged traffic can never quarantine.
  - Earned recovery with post-quantum-signed evidence.
- **Visual:** five nodes on a circuit line.

## Section 6: Expected outcome

### 23. 6. Expected Outcome *(official heading; sub-point: Expected Results / Prototype)*: demo results
- **Objective:** required diagram 9, plus the measured run.
- **Attack story diagram:**
  - FORGED → REJECTED (401)
  - REPLAY → REJECTED (409)
  - PHYSICAL TAMPER + VISUAL EVIDENCE → CORRELATION → QUARANTINE
- **Measured score path (live run on the USB camera, 2026-10-02):**
  - 100 → 90: real detections
  - → 80: forged
  - → 72, SUSPICIOUS: replay
  - → 30, QUARANTINED: tamper plus signed visual evidence
  - → 80, RECOVERED, then 85, TRUSTED: in announced time-lapse
- **Speaker emphasis:** every step is real HTTP against the real gateway. The attacks are simulated and labelled.

### 24. Limitations, future scope and impact *(sub-points: Real-World Impact, Future Scope)*
- **Limitations:**
  - Device telemetry is simulated and the ESP32 has never been compiled.
  - The device path is HMAC.
  - No attestation.
  - Camera thresholds are unvalidated, and proximity is not a distance.
  - No external anchoring.
  - Single gateway.
  - Trust parameters are not calibrated.
- **Future, hardware:** compile and flash; check the test vectors; reed switch first, then BME280 and MPU6050;
  stage the camera tests; then calibrate.
- **Impact:** AIoT sites (labs, server rooms, critical infrastructure) get a device that has to keep earning trust,
  with evidence that survives quantum-era forgery.
- **Closing line:** "Authenticate once. Verify continuously. Recover only with evidence."

---

## Visual and diagram plan

| # | Diagram | Form | Accent use |
|---|---|---|---|
| 2 | Compromise timeline | Horizontal time axis with event nodes | Orange bracket on the "trust should change" span only |
| 5 | Closed loop | Ring of six nodes and a circuit arc | Orange node fill for ENFORCE and RECOVER |
| 6 | System architecture | Two input lanes into a vertical trunk, then a fork | Orange for the decision fork; grey for simulated |
| 7 | Six factors | Six weighted bars → Σ → minus pressure → min(caps) → score | Bar lengths proportional to weight |
| 8 | Score bands | One horizontal 0-100 bar with three bands and a hysteresis marker | Orange for SUSPICIOUS |
| 10 | ML-KEM handshake | Two-lane sequence with numbered arrows | Orange on the shared-secret and AES nodes |
| 11 | Signed observation | Left-to-right pipeline that forks into accept and reject | Reject branch outlined |
| 13 | Vision pipeline | Left-to-right pipeline | Signed node orange |
| 14 | Camera anomaly | Six state cards in a row, then a correlation node | Incident card orange |
| 15 | Digital twin | Three-column comparison table | MISMATCH cells orange |
| 16 | Evidence chain | Three linked blocks, a signature seal, a verifier | Hash arrows black, seal orange |
| 18 | Recovery | Eight-step stepper with a failure rail below | Failure rail dashed |
| 19 | Technology stack | Seven groups in a grid | Group labels only |
| 21 | Benchmarks | Native bar shapes, exact values printed | Single orange series |
| 23 | Attack story | Three rows of flow | Quarantine terminal orange |

**Rules applied on every slide:**
- At most about 40 words of body text, outside diagrams.
- No paragraphs, icons, gradients, 3D or stock imagery.
- Monospace only for protocol strings, formulas and sizes.
- Every diagram is native, editable PowerPoint shapes.
- The watermark is kept only on slide 1, where nothing overlaps it.
