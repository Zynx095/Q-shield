# Q-SHIELD: final Quant-A-Maze 3.O deck, slide-by-slide plan (12 slides)

**Limit.** At most 12 slides, PDF included. The deck has exactly 12; `build.py` refuses to write more.

**Design authority.** The official template is `ppt/Quant-A-Maze.pptx`. Every slide is a clone of one of its pages,
so the NITTE, QUANT-Λ-MAZE 3.0 and Q-BITS logos, the orange band, the halftone strip, the bottom band and the white
background stay. The template's two reference slides are removed, as it instructs.

**Template mapping.**
- The six official section headings are kept word for word, and each opens its section.
- Every other slide carries its section's heading as a small marker.
- Sections:
  - **1. Participant information:** slide 1.
  - **2. Problem definition:** slide 2.
  - **3. Proposed solution and execution plan:** slides 3 and 4.
  - **4. Technical design:** slides 5 to 9.
  - **5. Feasibility and innovation:** slides 10 and 11.
  - **6. Expected outcome:** slide 12.
- The suggested 29-slide story is merged into these 12. Every required diagram is still present.

**Numbers.** Every number is from the repository, with its source in the speaker notes and in
`ppt/references/verified-facts.md` section 0. Benchmarks are laptop numbers. Nothing is claimed for the ESP32.

**Type and colour.**
- Titles: Bahnschrift SemiBold, 36 to 40 pt.
- Body: Segoe UI, 15 to 21 pt.
- Technical strings: Consolas.
- Smallest text: 13 pt, for chart axis labels only. The canvas is 20 x 11.25 in.
- Accent: the template's orange `#FF914D`. Orange text uses a darker `#C2410C`, for contrast on white.

---

### 1. 1. Participant Information & Topic Name *(official heading)*
- **Fields:** team name, lead name and contact are `[ to fill ]` (not supplied; never invented).
- **Track:** Post-Quantum Cryptography, highlighted.
- **Topic:** Q-SHIELD: continuous device trust with post-quantum-signed evidence.
- **One line:** "Authentication answers *who are you* once. Q-SHIELD keeps asking *can you still be trusted*."
- **Visual:** the template watermark, kept, and a device → gateway → trust strip.

### 2. 2. Problem Definition *(official heading)*
- **Timeline:** t0 authenticate ✓, then enclosure opened, configuration drift, camera covered or turned, and
  forged or replayed traffic. Each is "still trusted". An orange bracket reads "trust should change here, but
  authentication never asks again".
- **Threat table (threat, authentication alone, what Q-SHIELD adds):**
  - forged or replayed: bounded pressure ≤ 25; the replay cap is 65;
  - enclosure opened: CRITICAL, cap 55;
  - camera covered, frozen or turned: signed report, HIGH;
  - **tamper + visual within 60 s: confirmed incident, score 30, quarantine**;
  - quantum adversary: ML-DSA-65 and ML-KEM-768.
- **Emphasis:** no single signal quarantines; two independent authenticated signals do.

### 3. 3. Proposed Solution & Execution Plan *(official heading)*: working principle
- **Loop, in the subtitle:** observe → verify → score → enforce → recover → prove.
- **Architecture diagram:**
  - ESP32 / device agent → Identity (HMAC-SHA256 + counter);
  - Vision service → PQC session (ML-KEM-768, AES-256-GCM) → signed observations (ML-DSA-65);
  - both → Gateway → Trust engine → Decision, which forks:
    - < 50: QUARANTINE (403) → Recovery → VERIFIED → TRUSTED;
    - ≥ 50: TRUSTED or SUSPICIOUS.
  - Side rail: digital twin, evidence chain.

### 4. Core functionality: continuous six-factor trust
- **Factors:** identity 25, physical 20, configuration 15, sensor 15, visual 15, network 10.
- **Pipeline:** weighted sum → − pressure (≤ 25) → min(caps) → score.
- **Caps:** incident 30, tamper 55, correlated 55, replay 65, integrity 65, stale 79.
- **State band:** QUARANTINED < 50, SUSPICIOUS 50-79, TRUSTED ≥ 80; re-entry at 85.
- **Recovery credit:** `Δc = clamp(t − max(t_prev, t_violation), 0, 45 s)`.
- **Note:** authenticity is not trust.

### 5. 4. Technical Design *(official heading)*: the post-quantum session
- **Chain:** Why PQC → ML-KEM → Session → ML-DSA → Signed evidence → AES-GCM → Continuous trust.
- **Handshake (two lanes):**
  1. key generation (provisioned; pinned key 1184 B);
  2. encapsulation;
  3. ciphertext 1088 B in an ML-DSA-65-signed init, verified, then decapsulated (32 B secret);
  4. HKDF-SHA256 on both sides;
  5. session id + server nonce + confirmation; a wrong key means nothing is sent;
  6. AES-256-GCM with per-direction keys, 64-bit counters and AAD.
- **Numbers (median, laptop):** encapsulate 0.069 ms, decapsulate 0.091 ms, handshake 10.0 ms.
- **Caveat on the slide:** not TLS, not externally reviewed.

### 6. ML-DSA-65 signed observations and evidence chain
- **Observation flow:**
  - Observation → Canonical encoding (length-prefixed, never JSON) → ML-DSA-65 sign (context
    `qshield/signed-observation/v1`) → Signature (3309 B) → Gateway verify.
  - The verify step forks: ACCEPT 200, or REJECT (401 forged, unknown, retired or stale; 409 replayed).
- **Numbers:** sign 9.42 ms, verify 0.188 ms.
- **Evidence chain:**
  - Event N, N+1 and N+2, each with prev_hash, event_hash and an ML-DSA-65 signature.
  - Live demo: 26 entries, VERIFIED.
  - Caveat: not anchored externally; tail truncation needs an outside copy of the head.

### 7. AI vision security: the camera is part of the boundary
- **Pipeline:** Camera → YOLO11n → object, confidence, zone → camera health → signed observation → trust engine.
- **Six state cards (how it is measured → effect):**
  - Normal: no report.
  - Occluded: dark, flat or blinded for 2 s → HIGH.
  - Moved: shift found, or similarity < 0.7 → HIGH.
  - Frozen: the same frame repeated → HIGH.
  - Degraded: low light or blur → MEDIUM.
  - Too close: box over 35% of the frame, not a distance → LOW.
- **Correlation:** tamper report + signed camera interference → confirmed incident (score 30) → QUARANTINE.
- **Notes:**
  - The camera alone never quarantines, and one signer is one modality.
  - The live USB webcam ran at about 5 frames/s; detection accuracy is not measured.

### 8. Quarantine, digital twin and self-healing recovery
- **Recovery stepper:** Quarantine → Authorize → Remediate → Health checks (3) → Twin match → Verified → Recovered
  (≥ 50) → Trusted (≥ 85).
- **Failure rail:** any failure → QUARANTINED (authenticated fault, 15-min deadline, 2-h deadline, revocation).
- **Twin table:**
  - firmware: MATCH
  - configuration: MISMATCH
  - capabilities: MATCH
  - temperature: MATCH
  - tamper: MISMATCH
- **Quarantine grid:**
  - trusted states: normal channel allowed, recovery not open;
  - quarantined states: 403 normal, recovery allowed;
  - forged messages: 401.

### 9. Technology stack and implementation plan
- **Stack, technology with its role:**
  - Cryptography: pqcrypto, cryptography, hashlib and hmac.
  - AI / vision: OpenCV, YOLO11n, NumPy.
  - Backend: FastAPI and uvicorn, Pydantic, the trust engine.
  - Frontend: ES modules, presentation mode.
  - Database: SQLite.
  - Deployment: laptop gateway.
  - Hardware: planned (ESP32, BME280, MPU6050, reed switch).
- **Implementation plan:** phases 0-3 → 4 → 5-11 → 12-17.

### 10. 5. Feasibility & Innovation *(official heading)*: feasibility and performance
- **Real and tested:** PQC primitives, evidence chain, YOLO11n on a USB webcam, the trust, quarantine and recovery
  engines, twin, dashboard and camera preview.
- **Simulated or not yet:**
  - device telemetry: a labelled software agent;
  - ESP32 never compiled, no physical sensors;
  - no attestation; camera thresholds unvalidated;
  - single gateway; chain not anchored.
- **PQC bars (median ms):** 0.060, 0.069, 0.091, 0.188, 9.42, 10.0.
- **Tiles:** 785 Python tests, 40 JS tests, 70 NIST ACVP vectors, 53 µs per trust update.

### 11. Innovation / USP
- **Five points:**
  - continuous, explainable trust;
  - authenticity is not trust;
  - the camera as a security boundary;
  - bounded griefing;
  - earned recovery with signed evidence.
- **Tested abuse results:**
  - replayed handshake: one session;
  - replayed or reordered message: rejected;
  - flood: 300 messages → 8 rows, trust unchanged;
  - persistent refusals: 30 → 1 session;
  - session exhaustion: budget holds;
  - forged "all clear": 401.
- **Note:** we claim an integration, not a new algorithm; no prior-art survey has been done.

### 12. 6. Expected Outcome *(official heading)*
- **Attack story:**
  - forged → REJECTED 401;
  - replayed → REJECTED 409;
  - tamper + visual → correlation → QUARANTINE (score 30).
- **Measured score path (live, 2026-10-02):** 100 → 90 → 80 → 72 → 30 → 30 → 80 → 85, with recovery in announced
  time-lapse.
- **Future scope, with hardware:** ESP32 and the test vectors; reed switch, BME280 and MPU6050; staged camera tests
  and calibration; external anchoring.
- **Impact:** devices must keep earning trust; every incident has a signed, explainable trail.
- **Closing line:** "Authenticate once. Verify continuously. Recover only with evidence."

---

## Visual and diagram plan

| Slide | Diagram | Form |
|---|---|---|
| 2 | Compromise timeline + threat model | Time axis with event nodes and a bracket; five-row table with the incident row marked |
| 3 | System architecture | Two input lanes → gateway → trust engine → decision fork → recovery loop |
| 4 | Six factors and scoring | Weight bars → bracket → vertical pipeline → score; caps bars; state band |
| 5 | ML-KEM-768 handshake | Two-lane sequence, six numbered steps, crypto chain above |
| 6 | Signed observation + evidence chain | Pipeline with an accept/reject fork; three linked blocks |
| 7 | Vision security + camera anomaly | Pipeline; six pictogram cards with severity chips; correlation row |
| 8 | Recovery + twin + quarantine | Eight-step stepper with a failure rail; comparison table; channel grid |
| 9 | Technology stack | Seven groups with roles; phase strip |
| 10 | Feasibility and performance | Real/simulated ledger; PQC bars with exact values; four tiles |
| 11 | USP + abuse results | Five nodes on a line; results table |
| 12 | Attack story + measured score path | Flow rows; line chart over state bands |

**Rules.**
- No paragraphs, icons, gradients, 3D or stock imagery.
- Every diagram is native, editable PowerPoint shapes.
- QA renders come from real PowerPoint over COM (`ppt/preview/quantamaze/`).
