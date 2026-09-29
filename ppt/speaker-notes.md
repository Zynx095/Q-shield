# Q-SHIELD: speaker notes

Generated with slide-content.md. Every slide: what it proves, what to say, likely questions, terminology, what to acknowledge.

## Slide 1: Q-SHIELD

```
[MIXED]  WHAT THIS SLIDE PROVES: Sets the frame: an architecture for continuous trust, with an honest boundary between what is built and what is next.

SAY:
- Q-SHIELD is about not trusting a device forever just because it authenticated once.
- Today we have built and tested the observation and post-quantum security layer; trust, quarantine and recovery are the next phase.

TERMINOLOGY: Say 'post-quantum cryptography' and 'prototype'. Never 'quantum-proof'.

ACKNOWLEDGE: State early that the ESP32 is not post-quantum and that trust/recovery are not implemented.

SOURCES: README.md
```

## Slide 2: Problem: authentication is not continuous trust

```
[CONTEXT]  WHAT THIS SLIDE PROVES: Motivation only. It makes no claim about the prototype.

SAY:
- A device that passed authentication at boot can still be tampered with, spoofed, or have its credential misused later.
- Cameras and sensors add physical and environmental signals that identity systems ignore.

LIKELY JUDGE QUESTIONS:
Q: Do you have statistics on IoT attacks?
A: No. We do not cite any figures in this deck because none are in our repository.

TERMINOLOGY: 'Harvest now, decrypt later' applies to confidentiality of long-lived data; say so if asked about quantum.

ACKNOWLEDGE: No market or attack statistics are presented.

SOURCES: docs/hackathon/problem-statement.md
```

## Slide 3: Why existing IoT security is fragmented

```
[CONTEXT]  WHAT THIS SLIDE PROVES: Frames the gap as missing integration, not missing components.

SAY:
- Each question is answered by a different system.
- What is missing is a loop where the answers together change trust and access.

LIKELY JUDGE QUESTIONS:
Q: Is there really nothing like this?
A: We say 'often fragmented'. We have not completed a prior-art survey, so we make no 'first' claim.

TERMINOLOGY: 'Often fragmented' is the wording; never 'nothing exists'.

ACKNOWLEDGE: docs/research/prior-art.md is empty: the survey is future work.

SOURCES: docs/hackathon/novelty.md; docs/implementation-roadmap.md (R2)
```

## Slide 4: 02 closed loop

```
[MIXED]  WHAT THIS SLIDE PROVES: The closed loop we are building. Green stages exist; amber stages are planned.

SAY:
- Observe, authenticate, analyze are built and tested.
- Trust, quarantine, recover, re-authenticate and restore are the next phases, and the trust-model specification comes before any code.

LIKELY JUDGE QUESTIONS:
Q: Why does the loop matter?
A: Detection alone does not change what a device may do; the loop connects evidence to action.

TERMINOLOGY: Dashed amber = planned. Use 'planned', not 'coming soon'.

ACKNOWLEDGE: Everything right of ANALYZE is not implemented.

SOURCES: ppt/diagrams/02_closed_loop.png; docs/implementation-roadmap.md
```

## Slide 5: Core innovation: integration, not a new algorithm

```
[MIXED]  WHAT THIS SLIDE PROVES: Where the contribution is, and that each element carries its own honest status.

SAY:
- None of the individual technologies is our invention.
- The proposed contribution is composing them into one loop for a small AIoT endpoint, with explainable decisions.

LIKELY JUDGE QUESTIONS:
Q: What is novel?
A: The integration and the closed loop, proposed. We have not surveyed prior art, so we do not claim it is the first such system.

TERMINOLOGY: 'Proposed integration', 'architectural composition'. Never 'novel algorithm'.

ACKNOWLEDGE: Six of the seven elements are not fully built; the slide labels each.

SOURCES: docs/hackathon/novelty.md; docs/technical-decisions.md
```

## Slide 6: 01 architecture

```
[MIXED]  WHAT THIS SLIDE PROVES: System architecture and what is built: laptop gateway, vision service, device path, observation store, security events.

SAY:
- The laptop is the compute hub: gateway, AI, PQC, database.
- The ESP32 is the physical endpoint; so far the device path has been exercised with a software device agent.
- Amber boxes are planned.

LIKELY JUDGE QUESTIONS:
Q: Why is the ESP32 not in the demo?
A: The firmware is an unvalidated skeleton and no board has been connected yet; we did not fake hardware results.

TERMINOLOGY: 'Gateway', 'vision service', 'software device agent'.

ACKNOWLEDGE: Single laptop hosts everything (single-host trust domain).

SOURCES: ppt/diagrams/01_architecture.png; backend/README.md
```

## Slide 7: Two different security profiles today

```
[MIXED]  WHAT THIS SLIDE PROVES: The two components have different, explicit security profiles; PQC is not applied to the ESP32.

SAY:
- The ESP32 uses HMAC-SHA256: symmetric, not post-quantum.
- The vision service has an ML-DSA-65 identity and can use an ML-KEM-768 session.
- The identity belongs to the software service, not to the webcam.

LIKELY JUDGE QUESTIONS:
Q: Is the ESP32 quantum-safe?
A: No. It uses HMAC-SHA256. ESP32-side PQC is an untested research question.

TERMINOLOGY: 'Symmetric authentication', 'ML-DSA-65 service identity'. Never 'the device is quantum-safe'.

ACKNOWLEDGE: Nothing cryptographically binds the webcam to the ESP32; the vision service is authenticated by its key, and the device_id is configuration.

SOURCES: pqc/README.md; backend/protocol/envelope.py
```

## Slide 8: 11 pqc session flow

```
[IMPLEMENTED]  WHAT THIS SLIDE PROVES: The ML-KEM-768 session is implemented: signed handshake, key confirmation, AES-256-GCM messages.

SAY:
- The client encapsulates to the pinned gateway key and signs the handshake with ML-DSA-65.
- The gateway verifies the signature before decapsulating.
- A key-confirmation tag lets the client detect a wrong gateway key or a corrupted ciphertext.

LIKELY JUDGE QUESTIONS:
Q: Why not TLS?
A: We built the property on our own path to test it; it is standard primitives composed by us and not externally reviewed. TLS with a post-quantum key exchange is the better production route.
Q: Why ML-KEM and ML-DSA?
A: They are the NIST-standardised (FIPS 203 / 204) post-quantum key-establishment and signature schemes.

TERMINOLOGY: 'ML-KEM-768 key establishment', 'implicit rejection', 'key confirmation'.

ACKNOWLEDGE: No external review of this protocol; session state is in memory; static gateway KEM key means no forward secrecy against its later compromise.

SOURCES: backend/security/session.py; pqc/README.md
```

## Slide 9: 12 observation auth flow

```
[IMPLEMENTED]  WHAT THIS SLIDE PROVES: Every observation is authenticated with a signature over unambiguous bytes, and eight ordered checks reject bad input.

SAY:
- We sign a length-prefixed encoding of the exact fields, not a JSON serialization.
- The signature is verified before the payload is parsed or the timestamp is trusted.
- Each rejection has its own reason code in the event log; the HTTP answer stays generic.

LIKELY JUDGE QUESTIONS:
Q: What stops a replay?
A: The unique observation id plus a 300-second freshness window: an exact replay is HTTP 409 inside the window and HTTP 401 (stale) after it.

TERMINOLOGY: 'Canonical length-prefixed encoding', 'freshness window'.

ACKNOWLEDGE: A genuine message can still be delayed within the window.

SOURCES: backend/protocol/signed_observation.py; backend/security/pqc_gateway.py
```

## Slide 10: 13 implementation status

```
[MIXED]  WHAT THIS SLIDE PROVES: Three separate categories: implemented, designed, planned.

SAY:
- Implemented means code plus automated tests or a recorded run.
- Designed means written down only, including an ESP32 firmware skeleton we have never run on a board.
- Planned means not started.

LIKELY JUDGE QUESTIONS:
Q: What can I see working today?
A: The webcam to signed-observation path, tamper and replay rejection, the tests, and the recorded evidence.

TERMINOLOGY: Keep 'implemented', 'designed', 'planned' distinct.

ACKNOWLEDGE: Trust engine, quarantine, recovery, evidence chain, digital twin, dashboard are not implemented.

SOURCES: ppt/references/verified-facts.md; docs/technical-decisions.md
```

## Slide 11: 03 signed observation flow

```
[MEASURED]  WHAT THIS SLIDE PROVES: A real run: webcam, YOLO11n, ML-DSA-signed observations in an ML-KEM session, verified by the gateway.

SAY:
- 11 observations were stored as ML-DSA-65:vision-1.
- An altered payload got HTTP 401; an exact replay got HTTP 409.
- We re-verified all 11 stored signatures offline and all 11 altered copies were rejected.

LIKELY JUDGE QUESTIONS:
Q: Where are the screenshots?
A: We have none and will not fabricate any. The evidence file is docs/results/live-run-phase3.json.
Q: Was a person in the restricted zone?
A: No. Nobody was in view; detections were chairs and a plant, no anomaly flagged. That path is covered by tests with a fake detector only.

TERMINOLOGY: 'Recorded run', 'controlled local run'.

ACKNOWLEDGE: The scene had no person; only one session and one tampered/replayed message were tried.

SOURCES: docs/results/live-run-phase3.json
```

## Slide 12: 05 pqc benchmark

```
[MEASURED]  WHAT THIS SLIDE PROVES: Measured cost of the PQC operations on a laptop.

SAY:
- ML-KEM-768: 0.060, 0.069 and 0.091 ms for keygen, encapsulate, decapsulate.
- ML-DSA-65: 0.232 ms keygen, 9.42 ms sign, 0.188 ms verify.
- Signature 3309 bytes; ciphertext 1088 bytes.

LIKELY JUDGE QUESTIONS:
Q: Is this ESP32 performance?
A: No. It is an Intel i7-13700HX laptop. We have no embedded measurements.
Q: Why is signing slow?
A: It is about 50 times slower than verifying in this library; we did not investigate the cause and it does not matter at our event rate.

TERMINOLOGY: 'Median latency, 300 calls x 5 rounds'.

ACKNOWLEDGE: Laptop only; Python bindings; no CPU pinning.

SOURCES: docs/results/pqc-benchmark.json
```

## Slide 13: 06 vision performance

```
[MEASURED]  WHAT THIS SLIDE PROVES: The vision pipeline runs at demo-usable speed on a laptop CPU.

SAY:
- At 640 input: 25.1 inference-only FPS and 21.0 end-to-end.
- At 320: 51.4 and 30.0.
- This is speed, not accuracy.

LIKELY JUDGE QUESTIONS:
Q: How accurate is it?
A: Not measured. We claim no accuracy, precision, recall or false-positive rate.
Q: Why YOLO?
A: A lightweight, widely used detector that runs on a laptop CPU; it is behind a replaceable interface and its AGPL-3.0 licence is disclosed.
Q: How do you prevent AI false positives?
A: We do not claim to. Observations carry confidence and are rules, not verdicts; the planned trust engine must treat them as uncertain and never let confidence override cryptographic authenticity.

TERMINOLOGY: 'Inference-only FPS', 'end-to-end FPS'. Never 'accuracy benchmark'.

ACKNOWLEDGE: No person was in view during the runs, so post-processing with detections is not represented; one run each.

SOURCES: ai/README.md
```

## Slide 14: 14 validation flow

```
[MEASURED]  WHAT THIS SLIDE PROVES: How the claims were checked, from standards vectors to a real run.

SAY:
- NIST vectors, an independent implementation, behaviour tests, protocol tests, a sabotage check, then the real run and offline re-verification.
- 347 of 347 tests pass; 182 pre-date Phase 3 and are unchanged.

LIKELY JUDGE QUESTIONS:
Q: What evidence do you have that PQC works?
A: NIST ACVP vectors agree (35 decapsulation cases, 20 key-validity cases, 15 ML-DSA verification cases), an independent implementation interoperates both ways, and the real run verified. That is evidence of algorithm-level correctness, not certification.

TERMINOLOGY: 'Known-answer tests', 'interoperability', 'sabotage check'.

ACKNOWLEDGE: No keygen/signing/encapsulation known-answer tests (library takes no seed); no FIPS 140; no audit.

SOURCES: pqc/README.md; tests/
```

## Slide 15: 07 nist conformance

```
[MEASURED]  WHAT THIS SLIDE PROVES: Agreement with NIST known-answer vectors for the two algorithms we use.

SAY:
- 35 ML-KEM-768 decapsulation cases and 20 key-validity cases; 15 ML-DSA-65 verification cases: 3 valid, 12 invalid.
- All agree with NIST ACVP; an independent pure-Python implementation interoperates in both directions.

LIKELY JUDGE QUESTIONS:
Q: Is it FIPS validated?
A: No. FIPS 140 validation is not claimed.

TERMINOLOGY: 'ACVP', 'known-answer test'. Never 'certified' or 'FIPS-validated'.

ACKNOWLEDGE: Library pqcrypto 1.0.0 (Apache-2.0), Rust crates not audited by us, verified on Windows x86-64 only.

SOURCES: tests/vectors/pqc/MANIFEST.json; pqc/README.md
```

## Slide 16: 15 trust engine next

```
[PLANNED]  WHAT THIS SLIDE PROVES: What the trust engine will take as input, and what exists today for each input. Nothing here is implemented.

SAY:
- Inputs are cryptographic authenticity, physical tamper, sensor consistency, visual anomalies, network behaviour, integrity state and recent security events.
- Green inputs already produce data; amber ones are schema fields or simulated; network behaviour is not collected.
- We have not chosen weights or thresholds: the specification comes first.

LIKELY JUDGE QUESTIONS:
Q: How is the trust score calculated?
A: It is not yet. We will specify inputs, formula, caps, decay and state transitions before writing code, and every change will carry machine-readable reasons.
Q: What if AI confidence is low?
A: Detection confidence and cryptographic authenticity are separate; low confidence reduces impact, and confidence can never bypass authenticity.

TERMINOLOGY: 'Phase 4, next implementation'. Never show a number or threshold.

ACKNOWLEDGE: Physical tamper, sensor and integrity signals need the real ESP32; self-reported hashes are not proof of firmware integrity.

SOURCES: docs/implementation-roadmap.md; docs/technical-decisions.md (TD-08)
```

## Slide 8: Self-healing architecture: roadmap

```
[PLANNED]  WHAT THIS SLIDE PROVES: The intended recovery model and its boundaries.

SAY:
- Self-healing here means recovering from defined software and security compromises, not repairing hardware.
- A reboot alone never marks a device recovered; failed checks leave it quarantined.

LIKELY JUDGE QUESTIONS:
Q: What exactly is self-healing?
A: A planned, checked sequence for compromise classes we define: revoke the session, preserve evidence, enter safe mode, verify state, restore known-good configuration, re-authenticate with the PQC layer, validate, then rebuild trust gradually. It is designed in our decisions document and not implemented.

TERMINOLOGY: 'Recovery for defined compromise classes'. Never 'the system heals itself'.

ACKNOWLEDGE: Firmware/config hashes reported by a compromised device are evidence, not proof.

SOURCES: docs/technical-decisions.md (TD-10)
```

## Slide 18: 16 esp32 status

```
[MIXED]  WHAT THIS SLIDE PROVES: Transparent ESP32 status.

SAY:
- Architecture is prepared and the gateway verifies the HMAC device profile, tested with a software agent.
- A firmware project exists but has never been validated on a board; the exact board is not confirmed.
- ESP32-side PQC is not claimed; the R1 feasibility experiment is pending.

LIKELY JUDGE QUESTIONS:
Q: Why is the ESP32 not using PQC?
A: We do not claim it until implemented and tested there. Whether ML-DSA verification is practical on an ESP32 is experiment R1, which has not run because no board is connected. The architecture stays the same either way.

TERMINOLOGY: 'Feasibility experiment R1'. Never imply the ESP32 does PQC.

ACKNOWLEDGE: PlatformIO is installed on the laptop but the toolchain is not downloaded and nothing has been flashed.

SOURCES: hardware/esp32/README.md; docs/implementation-roadmap.md (R1)
```

## Slide 19: Limitations

```
[MIXED]  WHAT THIS SLIDE PROVES: We know the boundaries of our claims.

SAY:
- These six matter most.
- More detail is in the appendix: the webcam is not cryptographically bound to the ESP32, tokens travel over plain HTTP on a trusted LAN, camera-obstruction thresholds are unvalidated, and only a software agent exercised the device path.

LIKELY JUDGE QUESTIONS:
Q: What happens if the gateway is compromised?
A: Then the protections end: it holds the master key, the database and the verification logic. That is out of scope for the prototype and we say so.
Q: Is the system actually quantum-safe?
A: No system-wide claim. Post-quantum cryptography is used on the vision-service to gateway path (ML-DSA-65 authenticates observations; the optional ML-KEM-768 session encrypts them); the ESP32 uses HMAC-SHA256; the trust and recovery layers do not exist yet.

TERMINOLOGY: 'Defined threat model', 'prototype'.

ACKNOWLEDGE: This whole slide.

SOURCES: pqc/README.md; ai/README.md; backend/README.md
```

## Slide 20: 17 roadmap

```
[PLANNED]  WHAT THIS SLIDE PROVES: Where the project goes next, in order.

SAY:
- Trust specification first, then the trust engine, attack simulation, quarantine, recovery, evidence chain, digital twin and dashboard.
- In parallel: confirm the ESP32 board, validate firmware, run experiment R1.

LIKELY JUDGE QUESTIONS:
Q: What will you do first?
A: Write the trust-model specification and its deterministic test matrix; nothing gets coded until it is consistent.

TERMINOLOGY: 'Planned' for every amber item.

ACKNOWLEDGE: Everything to the right is not started.

SOURCES: docs/implementation-roadmap.md
```

## Slide 21: Key takeaway

```
[MIXED]  WHAT THIS SLIDE PROVES: One-sentence thesis plus the honest split.

SAY:
- Authenticity tells you who said something; trust asks whether to believe and allow it.
- We built and measured the authenticated observation layer that a trust engine will consume.

TERMINOLOGY: Thesis: 'Continuous cyber-physical trust with post-quantum security and a planned recovery loop.'

ACKNOWLEDGE: Trust and recovery are next.

SOURCES: ppt/references/verified-facts.md
```

## Slide A1: 09 authenticity is not trust

```
[IMPLEMENTED]  WHAT THIS SLIDE PROVES: Authentication proves provenance, not device health.

SAY:
- A valid signature or HMAC tag does not prove the device is uncompromised.

LIKELY JUDGE QUESTIONS:
Q: Why keep authenticity separate from AI confidence?
A: So a confident detector can never bypass a failed signature, and a valid signature can never hide an anomaly.

TERMINOLOGY: 'Provenance', 'possession of the provisioned secret'.

ACKNOWLEDGE: The trust engine that uses this principle is not built.

SOURCES: ppt/diagrams/09_authenticity_is_not_trust.png
```

## Slide A2: 08 test summary

```
[MEASURED]  WHAT THIS SLIDE PROVES: Test counts by area.

SAY:
- 347 pass; the 182 tests that existed before Phase 3 are unchanged.

TERMINOLOGY: Counts are collected by pytest at build time.

ACKNOWLEDGE: Tests cover implemented behaviour only.

SOURCES: python -m pytest
```

## Slide A3: 04 security domains

```
[IMPLEMENTED]  WHAT THIS SLIDE PROVES: Security domains at a glance.

SAY:
- Operator and ingest tokens are classical and separate from device HMAC and from PQC signatures.

TERMINOLOGY: 'Token-only ingest path' is labelled ingest-token and can be disabled.

ACKNOWLEDGE: Tokens travel over plain HTTP on a trusted LAN.

SOURCES: docs/technical-decisions.md (TD-17)
```

## Slide A4: Threat model: what is established today

```
[MIXED]  WHAT THIS SLIDE PROVES: An honest threat model for the current milestone.

SAY:
- We list what the current architecture cannot establish.

LIKELY JUDGE QUESTIONS:
Q: Does the trust engine fix these?
A: Some it will help detect; others (gateway compromise) remain out of scope.

TERMINOLOGY: 'Defined threat model'.

ACKNOWLEDGE: The threat model for the trust engine is not yet written.

SOURCES: pqc/README.md; backend/README.md
```

## Slide A5: More limitations (detail)

```
[MIXED]  WHAT THIS SLIDE PROVES: The details behind the limitations slide.

SAY:
- Read only what a judge asks about.

ACKNOWLEDGE: All of it.

SOURCES: backend/README.md; ai/README.md; pqc/README.md
```
