# Q-SHIELD: judge Q&A

Answers use only facts in `references/verified-facts.md`. Where the honest answer is "not implemented" or "not measured", say that. Status words are used strictly: **implemented** (code + automated tests or a recorded run), **designed** (written down only), **planned** (not started).

## Cryptography

**Why is the ESP32 not using PQC?**
We do not claim it until it is implemented and tested on the board. The ESP32 authenticates with a provisioned HMAC-SHA256 secret (symmetric, not post-quantum). Whether ML-DSA verification or ML-KEM decapsulation is practical on an ESP32 (RAM, time, randomness, side channels) is a separate feasibility experiment, R1, that has not run because no board has been connected yet. The architecture does not depend on its outcome.

**Why ML-KEM and ML-DSA?**
They are the NIST-standardised post-quantum key-establishment (FIPS 203) and signature (FIPS 204) schemes, so they are the defensible choice for a quantum-resilient design. We use ML-KEM-768 and ML-DSA-65 through a replaceable interface.

**Why not TLS?**
The observation path needed per-message authenticity that survives storage (the signed envelope is kept as evidence), and we wanted to demonstrate and test the ML-KEM property on our own path. The optional session is standard primitives (ML-KEM, HKDF-SHA256, AES-256-GCM) composed by us with a signed handshake and key confirmation. It is not TLS and has had no external review. For production, TLS with a post-quantum key exchange is the better route.

**How is this different from conventional IoT authentication?**
The common pattern authenticates a device (certificate, pre-shared key or token) and then trusts the session. Q-SHIELD treats authentication as one input and keeps collecting evidence (camera observations, telemetry, security events) that a trust engine will use to decide continuously. What is implemented today is the authenticated observation layer; the trust engine is next.

**Is the system actually quantum-safe?**
No system-wide claim. On the vision-service to gateway path, ML-DSA-65 authenticates observations and the optional ML-KEM-768 session encrypts them. The ESP32 uses HMAC-SHA256. The trust and recovery layers do not exist yet. We say "post-quantum security layer", never "quantum-safe" or "quantum-proof".

**What evidence do you have that PQC works?**
NIST ACVP known-answer vectors: 35 ML-KEM-768 decapsulation cases and 20 key-validity cases all agree; 15 ML-DSA-65 verification cases (3 valid, 12 invalid) all agree. An independent pure-Python implementation interoperates with our library in both directions. A real run verified 11 signed observations, and an altered payload was rejected (401). This is evidence of algorithm-level correctness, not certification: keygen/signing/encapsulation known-answer tests are impossible with this library's API, the library is unaudited by us, and no FIPS 140 validation is claimed.

**Which library, and can we trust it?**
`pqcrypto` 1.0.0 (Apache-2.0) wrapping Rust crates. We did not audit them and only tested on Windows x86-64. It sits behind a replaceable interface; `liboqs` is the fallback.

**Why is signing 9.4 ms but verifying 0.19 ms?**
That is what this library measured on an i7-13700HX laptop; signing is about 50x slower than verifying and we did not investigate why. It does not matter at our event rate. These are not ESP32 numbers.

**Replay?**
Devices: strictly increasing counters. Signed observations: unique observation ids plus a 300-second freshness window. An exact replay gets HTTP 409 inside the window and HTTP 401 (stale) after it. A genuine message can still be delayed inside the window.

**What if the master key is lost or stolen?**
Loss: the gateway KEM key and device credentials become unrecoverable (re-provision); already-issued signer key files and public signer records keep working. Theft: treat everything as compromised, revoke signers and rotate keys. There is no HSM; keys are files on one host.

## Trust, recovery and scope

**How is the trust score calculated?**
It is not calculated yet. Phase 4 starts with a written specification (inputs, formula, weights, caps, decay, state transitions, test matrix) and only then code. The commitments are that it will be deterministic and explainable, every change will carry machine-readable reasons, authenticity and AI confidence stay separate, and no weight or threshold is shown until it is justified.

**Doesn't a valid signature mean the device is fine?**
No. A valid ML-DSA signature proves the observation came, unaltered, from the holder of the signing key; a valid HMAC tag proves possession of the provisioned secret. Neither proves the device is uncompromised. Authentication is an input to trust, never the decision.

**What exactly is self-healing?**
A planned, checked recovery sequence for defined software and security compromise classes: revoke the session, preserve evidence, enter safe mode, verify state, restore known-good configuration, re-authenticate through the PQC layer, run health checks, and rebuild trust gradually. If any check fails the device stays quarantined; a reboot alone never marks it recovered. It is not physical repair, and it is designed in our decisions document but **not implemented**.

**What does the trust engine protect against, and what not?**
Not yet specified, so no protection is claimed. Known limits already: a stolen device credential used with plausible telemetry, a compromised gateway host, and sensor spoofing are not addressed by the current architecture.

**What happens if the gateway is compromised?**
The protections end: it holds the master key, database and verification logic. This is out of scope for the prototype (single-host trust domain) and stated as a limitation.

**What if the vision service is compromised?**
It can sign false observations with its valid key. The design limits the blast radius (one source, a listed device set, revocable signer) but cannot detect a compromised signer by itself.

## Vision and AI

**Why use YOLO?**
A lightweight, widely used object detector that runs on a laptop CPU (25.1 inference-only FPS at 640 input, 51.4 at 320). It sits behind a replaceable interface. Its AGPL-3.0 licence is disclosed and has not had legal review.

**How accurate is it?**
Not measured. We claim no accuracy, precision, recall or false-positive rate; the FPS figures are speed measurements, taken with no person in view.

**How do you prevent AI false positives?**
We do not claim to. The vision pipeline outputs observations with a confidence and a rule-based `anomaly` flag ("matched a configured rule"), not verdicts. The planned trust engine must treat such observations as uncertain (lower confidence, lower impact), correlate them with other signals, and never let detection confidence override cryptographic authenticity.

**Does YOLO decide whether a device is compromised?**
No. It reports what it sees; trust decisions are a separate, later component.

**Are video frames stored or sent?**
No. Frames stay inside the vision process; only observations leave it.

**Did you show a person in the restricted zone live?**
No. The recorded run had no person in view (detections were chairs and a plant, no anomaly flagged). The person-in-zone path is covered by automated tests with a fake detector only.

## Hardware and evidence

**Do you have a working ESP32?**
The device path (register, heartbeat, telemetry, HMAC verification, replay protection) is tested with a software device agent. The ESP32 firmware is a protocol-only skeleton that has never been compiled against a board or flashed; the exact board is not confirmed.

**Show me screenshots.**
We have none and will not fabricate any. We can show the recorded evidence file, the test run (347 passed) and a live run.

**How many devices does it scale to?**
Untested: one device, one camera. No scalability claim.

## Novelty

**What is novel here?**
Not the algorithms: ML-KEM, ML-DSA and YOLO are existing technologies, and anomaly detection, trust scoring and hash-chained logs are established ideas. The proposal is their integration into one closed loop for a small AIoT endpoint: continuous trust, cyber + visual (+ physical, planned) signals, PQC-backed software components, explainable decisions, tamper-evident evidence and a quarantine/recovery loop. Only the observation and PQC layer of that composition is built. We have not completed a prior-art survey, so we make no "first" claim.

## Process

**What was hardest / what did you change along the way?**
Keeping claims aligned with evidence. Examples: the `cryptography` package's ML-KEM/ML-DSA turned out to be unsupported on this machine so a different library was selected; a test caught numeric epoch timestamps being silently accepted by the observation schema; a replay older than the freshness window returns 401, not 409, which we document.

**Why is nothing committed?**
The work is staged and untracked locally; committing is the team's decision.
