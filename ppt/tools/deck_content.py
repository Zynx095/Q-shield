"""Single source of truth for the presentation content (full technical deck).

Status tags (never blurred):
  IMPLEMENTED = code exists and is covered by automated tests or a recorded real run
  MEASURED    = a real measurement or recorded result
  DESIGNED    = written down only (docs / decisions / unvalidated skeleton)
  PLANNED     = not started
  MIXED       = the slide shows more than one of the above (each element is labelled on the slide)
  CONTEXT     = motivation, not a claim about the prototype
Numbers come from ppt/references/verified-facts.md and the files it cites. Do not add numbers here that are not there.
"""

DIAG = "ppt/diagrams/"
ASSET = "ppt/assets/"

# kind: title | bullets | columns | table | figure | figure_text
FULL = [
    dict(id="E01", kind="title", tag="MIXED", title="Q-SHIELD",
         subtitle="Quantum-Resilient Self-Healing AIoT Security Architecture",
         line="Working prototype: Phases 0-3 implemented and tested (347/347). Trust engine, quarantine and recovery: next.",
         notes=dict(
             proves="Sets the frame: an architecture for continuous trust, with an honest boundary between what is built and what is next.",
             say=["Q-SHIELD is about not trusting a device forever just because it authenticated once.",
                  "Today we have built and tested the observation and post-quantum security layer; trust, quarantine and recovery are the next phase."],
             ask=[], terms="Say 'post-quantum cryptography' and 'prototype'. Never 'quantum-proof'.",
             acknowledge="State early that the ESP32 is not post-quantum and that trust/recovery are not implemented."),
         sources=["README.md"]),

    dict(id="E02", kind="bullets", tag="CONTEXT", title="Problem: authentication is not continuous trust",
         bullets=["Authentication establishes identity once, not that a device stays trustworthy",
                  "AIoT adds attack surface: physical tampering, sensor manipulation, abnormal behaviour",
                  "Visual and environmental anomalies, credential misuse, replay and tampering",
                  "Long-lived devices must plan for future quantum threats"],
         notes=dict(
             proves="Motivation only. It makes no claim about the prototype.",
             say=["A device that passed authentication at boot can still be tampered with, spoofed, or have its credential misused later.",
                  "Cameras and sensors add physical and environmental signals that identity systems ignore."],
             ask=[("Do you have statistics on IoT attacks?", "No. We do not cite any figures in this deck because none are in our repository.")],
             terms="'Harvest now, decrypt later' applies to confidentiality of long-lived data; say so if asked about quantum.",
             acknowledge="No market or attack statistics are presented."),
         sources=["docs/hackathon/problem-statement.md"]),

    dict(id="E03", kind="columns", tag="CONTEXT", title="Why existing IoT security is fragmented",
         columns=[("Identity", ["answers: who is this device?", "cannot tell if it was tampered with later"]),
                  ("Monitoring", ["answers: what is it doing?", "cannot tell if a message is authentic"]),
                  ("AI detection", ["answers: does the scene look wrong?", "cannot tell who produced the data"]),
                  ("Cryptography", ["answers: is the channel protected?", "cannot tell if the device behaves correctly"])],
         callout="Often separate tools, with no closed loop that changes what a device may do.",
         notes=dict(
             proves="Frames the gap as missing integration, not missing components.",
             say=["Each question is answered by a different system.", "What is missing is a loop where the answers together change trust and access."],
             ask=[("Is there really nothing like this?", "We say 'often fragmented'. We have not completed a prior-art survey, so we make no 'first' claim.")],
             terms="'Often fragmented' is the wording; never 'nothing exists'.",
             acknowledge="docs/research/prior-art.md is empty: the survey is future work."),
         sources=["docs/hackathon/novelty.md", "docs/implementation-roadmap.md (R2)"]),

    dict(id="E04", kind="figure", tag="MIXED", figure=DIAG + "02_closed_loop.png",
         notes=dict(
             proves="The closed loop we are building. Green stages exist; amber stages are planned.",
             say=["Observe, authenticate, analyze are built and tested.", "Trust, quarantine, recover, re-authenticate and restore are the next phases, and the trust-model specification comes before any code."],
             ask=[("Why does the loop matter?", "Detection alone does not change what a device may do; the loop connects evidence to action.")],
             terms="Dashed amber = planned. Use 'planned', not 'coming soon'.",
             acknowledge="Everything right of ANALYZE is not implemented."),
         sources=["ppt/diagrams/02_closed_loop.png", "docs/implementation-roadmap.md"]),

    dict(id="E05", kind="columns", tag="MIXED", title="Core innovation: integration, not a new algorithm",
         columns=[("Existing technologies (not our claim)", ["ML-KEM and ML-DSA (NIST FIPS 203 / 204)", "YOLO object detection", "Anomaly detection, trust scoring", "Hash-chained logs, digital twins"]),
                  ("Q-SHIELD's proposed composition", ["PLANNED: continuous trust, not one-time authentication", "BUILT: PQC-backed software security components",
                                                       "BUILT + PLANNED: cyber + visual signals now, physical/sensor next", "PLANNED: explainable trust decisions",
                                                       "DESIGNED: security-state model, tamper-evident evidence chain", "PLANNED: quarantine and recovery loop"])],
         callout="Only the observation + PQC layer of this composition is built today. No 'first' claim: prior-art survey not done.",
         notes=dict(
             proves="Where the contribution is, and that each element carries its own honest status.",
             say=["None of the individual technologies is our invention.", "The proposed contribution is composing them into one loop for a small AIoT endpoint, with explainable decisions."],
             ask=[("What is novel?", "The integration and the closed loop, proposed. We have not surveyed prior art, so we do not claim it is the first such system.")],
             terms="'Proposed integration', 'architectural composition'. Never 'novel algorithm'.",
             acknowledge="Six of the seven elements are not fully built; the slide labels each."),
         sources=["docs/hackathon/novelty.md", "docs/technical-decisions.md"]),

    dict(id="E06", kind="figure", tag="MIXED", figure=DIAG + "01_architecture.png",
         notes=dict(
             proves="System architecture and what is built: laptop gateway, vision service, device path, observation store, security events.",
             say=["The laptop is the compute hub: gateway, AI, PQC, database.", "The ESP32 is the physical endpoint; so far the device path has been exercised with a software device agent.",
                  "Amber boxes are planned."],
             ask=[("Why is the ESP32 not in the demo?", "The firmware is an unvalidated skeleton and no board has been connected yet; we did not fake hardware results.")],
             terms="'Gateway', 'vision service', 'software device agent'.",
             acknowledge="Single laptop hosts everything (single-host trust domain)."),
         sources=["ppt/diagrams/01_architecture.png", "backend/README.md"]),

    dict(id="E07", kind="table", tag="MIXED", title="Two different security profiles today",
         header=("", "ESP32 endpoint", "Vision service (software)"),
         rows=[("Identity", "provisioned per-device secret", "ML-DSA-65 key of the service (not the webcam)"),
               ("Authentication", "HMAC-SHA256 tag", "ML-DSA-65 signature"),
               ("Post-quantum?", "NO (symmetric)", "YES: ML-DSA-65; ML-KEM-768 session optional"),
               ("Confidentiality", "none", "AES-256-GCM in the optional session"),
               ("Replay protection", "strictly increasing counter", "freshness window + unique observation id"),
               ("Status", "gateway side tested (software agent); firmware unvalidated", "implemented, tested, real run")],
         callout="Q-SHIELD adds a post-quantum layer (ML-KEM-768, ML-DSA-65) while retaining HMAC-SHA256 for the current ESP32 prototype.",
         notes=dict(
             proves="The two components have different, explicit security profiles; PQC is not applied to the ESP32.",
             say=["The ESP32 uses HMAC-SHA256: symmetric, not post-quantum.", "The vision service has an ML-DSA-65 identity and can use an ML-KEM-768 session.",
                  "The identity belongs to the software service, not to the webcam."],
             ask=[("Is the ESP32 quantum-safe?", "No. It uses HMAC-SHA256. ESP32-side PQC is an untested research question.")],
             terms="'Symmetric authentication', 'ML-DSA-65 service identity'. Never 'the device is quantum-safe'.",
             acknowledge="Nothing cryptographically binds the webcam to the ESP32; the vision service is authenticated by its key, and the device_id is configuration."),
         sources=["pqc/README.md", "backend/protocol/envelope.py"]),

    dict(id="E08", kind="figure", tag="IMPLEMENTED", figure=DIAG + "11_pqc_session_flow.png",
         notes=dict(
             proves="The ML-KEM-768 session is implemented: signed handshake, key confirmation, AES-256-GCM messages.",
             say=["The client encapsulates to the pinned gateway key and signs the handshake with ML-DSA-65.", "The gateway verifies the signature before decapsulating.",
                  "A key-confirmation tag lets the client detect a wrong gateway key or a corrupted ciphertext."],
             ask=[("Why not TLS?", "We built the property on our own path to test it; it is standard primitives composed by us and not externally reviewed. TLS with a post-quantum key exchange is the better production route."),
                  ("Why ML-KEM and ML-DSA?", "They are the NIST-standardised (FIPS 203 / 204) post-quantum key-establishment and signature schemes.")],
             terms="'ML-KEM-768 key establishment', 'implicit rejection', 'key confirmation'.",
             acknowledge="No external review of this protocol; session state is in memory; static gateway KEM key means no forward secrecy against its later compromise."),
         sources=["backend/security/session.py", "pqc/README.md"]),

    dict(id="E09", kind="figure", tag="IMPLEMENTED", figure=DIAG + "12_observation_auth_flow.png",
         notes=dict(
             proves="Every observation is authenticated with a signature over unambiguous bytes, and eight ordered checks reject bad input.",
             say=["We sign a length-prefixed encoding of the exact fields, not a JSON serialization.", "The signature is verified before the payload is parsed or the timestamp is trusted.",
                  "Each rejection has its own reason code in the event log; the HTTP answer stays generic."],
             ask=[("What stops a replay?", "The unique observation id plus a 300-second freshness window: an exact replay is HTTP 409 inside the window and HTTP 401 (stale) after it.")],
             terms="'Canonical length-prefixed encoding', 'freshness window'.",
             acknowledge="A genuine message can still be delayed within the window."),
         sources=["backend/protocol/signed_observation.py", "backend/security/pqc_gateway.py"]),

    dict(id="E10", kind="figure", tag="MIXED", figure=DIAG + "13_implementation_status.png",
         notes=dict(
             proves="Three separate categories: implemented, designed, planned.",
             say=["Implemented means code plus automated tests or a recorded run.", "Designed means written down only, including an ESP32 firmware skeleton we have never run on a board.", "Planned means not started."],
             ask=[("What can I see working today?", "The webcam to signed-observation path, tamper and replay rejection, the tests, and the recorded evidence.")],
             terms="Keep 'implemented', 'designed', 'planned' distinct.",
             acknowledge="Trust engine, quarantine, recovery, evidence chain, digital twin, dashboard are not implemented."),
         sources=["ppt/references/verified-facts.md", "docs/technical-decisions.md"]),

    dict(id="E11", kind="figure", tag="MEASURED", figure=DIAG + "03_signed_observation_flow.png",
         notes=dict(
             proves="A real run: webcam, YOLO11n, ML-DSA-signed observations in an ML-KEM session, verified by the gateway.",
             say=["11 observations were stored as ML-DSA-65:vision-1.", "An altered payload got HTTP 401; an exact replay got HTTP 409.", "We re-verified all 11 stored signatures offline and all 11 altered copies were rejected."],
             ask=[("Where are the screenshots?", "We have none and will not fabricate any. The evidence file is docs/results/live-run-phase3.json."),
                  ("Was a person in the restricted zone?", "No. Nobody was in view; detections were chairs and a plant, no anomaly flagged. That path is covered by tests with a fake detector only.")],
             terms="'Recorded run', 'controlled local run'.",
             acknowledge="The scene had no person; only one session and one tampered/replayed message were tried."),
         sources=["docs/results/live-run-phase3.json"]),

    dict(id="E12", kind="figure", tag="MEASURED", figure=ASSET + "05_pqc_benchmark.png",
         notes=dict(
             proves="Measured cost of the PQC operations on a laptop.",
             say=["ML-KEM-768: 0.060, 0.069 and 0.091 ms for keygen, encapsulate, decapsulate.", "ML-DSA-65: 0.232 ms keygen, 9.42 ms sign, 0.188 ms verify.", "Signature 3309 bytes; ciphertext 1088 bytes."],
             ask=[("Is this ESP32 performance?", "No. It is an Intel i7-13700HX laptop. We have no embedded measurements."),
                  ("Why is signing slow?", "It is about 50 times slower than verifying in this library; we did not investigate the cause and it does not matter at our event rate.")],
             terms="'Median latency, 300 calls x 5 rounds'.",
             acknowledge="Laptop only; Python bindings; no CPU pinning."),
         sources=["docs/results/pqc-benchmark.json"]),

    dict(id="E13", kind="figure", tag="MEASURED", figure=ASSET + "06_vision_performance.png",
         notes=dict(
             proves="The vision pipeline runs at demo-usable speed on a laptop CPU.",
             say=["At 640 input: 25.1 inference-only FPS and 21.0 end-to-end.", "At 320: 51.4 and 30.0.", "This is speed, not accuracy."],
             ask=[("How accurate is it?", "Not measured. We claim no accuracy, precision, recall or false-positive rate."),
                  ("Why YOLO?", "A lightweight, widely used detector that runs on a laptop CPU; it is behind a replaceable interface and its AGPL-3.0 licence is disclosed."),
                  ("How do you prevent AI false positives?", "We do not claim to. Observations carry confidence and are rules, not verdicts; the planned trust engine must treat them as uncertain and never let confidence override cryptographic authenticity.")],
             terms="'Inference-only FPS', 'end-to-end FPS'. Never 'accuracy benchmark'.",
             acknowledge="No person was in view during the runs, so post-processing with detections is not represented; one run each."),
         sources=["ai/README.md"]),

    dict(id="E14", kind="figure", tag="MEASURED", figure=DIAG + "14_validation_flow.png",
         notes=dict(
             proves="How the claims were checked, from standards vectors to a real run.",
             say=["NIST vectors, an independent implementation, behaviour tests, protocol tests, a sabotage check, then the real run and offline re-verification.",
                  "347 of 347 tests pass; 182 pre-date Phase 3 and are unchanged."],
             ask=[("What evidence do you have that PQC works?", "NIST ACVP vectors agree (35 decapsulation cases, 20 key-validity cases, 15 ML-DSA verification cases), an independent implementation interoperates both ways, and the real run verified. That is evidence of algorithm-level correctness, not certification.")],
             terms="'Known-answer tests', 'interoperability', 'sabotage check'.",
             acknowledge="No keygen/signing/encapsulation known-answer tests (library takes no seed); no FIPS 140; no audit."),
         sources=["pqc/README.md", "tests/"]),

    dict(id="E15", kind="figure", tag="MEASURED", figure=ASSET + "07_nist_conformance.png",
         notes=dict(
             proves="Agreement with NIST known-answer vectors for the two algorithms we use.",
             say=["35 ML-KEM-768 decapsulation cases and 20 key-validity cases; 15 ML-DSA-65 verification cases: 3 valid, 12 invalid.", "All agree with NIST ACVP; an independent pure-Python implementation interoperates in both directions."],
             ask=[("Is it FIPS validated?", "No. FIPS 140 validation is not claimed.")],
             terms="'ACVP', 'known-answer test'. Never 'certified' or 'FIPS-validated'.",
             acknowledge="Library pqcrypto 1.0.0 (Apache-2.0), Rust crates not audited by us, verified on Windows x86-64 only."),
         sources=["tests/vectors/pqc/MANIFEST.json", "pqc/README.md"]),

    dict(id="E16", kind="figure", tag="PLANNED", figure=DIAG + "15_trust_engine_next.png",
         notes=dict(
             proves="What the trust engine will take as input, and what exists today for each input. Nothing here is implemented.",
             say=["Inputs are cryptographic authenticity, physical tamper, sensor consistency, visual anomalies, network behaviour, integrity state and recent security events.",
                  "Green inputs already produce data; amber ones are schema fields or simulated; network behaviour is not collected.",
                  "We have not chosen weights or thresholds: the specification comes first."],
             ask=[("How is the trust score calculated?", "It is not yet. We will specify inputs, formula, caps, decay and state transitions before writing code, and every change will carry machine-readable reasons."),
                  ("What if AI confidence is low?", "Detection confidence and cryptographic authenticity are separate; low confidence reduces impact, and confidence can never bypass authenticity.")],
             terms="'Phase 4, next implementation'. Never show a number or threshold.",
             acknowledge="Physical tamper, sensor and integrity signals need the real ESP32; self-reported hashes are not proof of firmware integrity."),
         sources=["docs/implementation-roadmap.md", "docs/technical-decisions.md (TD-08)"]),

    dict(id="E17", kind="steps", tag="PLANNED", title="Self-healing architecture: roadmap",
         scope="Recovery for defined software / security compromise classes, not physical repair",
         steps=[("1", "Revoke session"), ("2", "Preserve evidence"), ("3", "Enter safe mode"), ("4", "Verify state"),
                ("5", "Restore known-good config"), ("6", "PQC re-authentication"), ("7", "Health checks"), ("8", "Rebuild trust gradually")],
         callout="If any check fails, the device stays QUARANTINED. Nothing on this slide is implemented.",
         notes=dict(
             proves="The intended recovery model and its boundaries.",
             say=["Self-healing here means recovering from defined software and security compromises, not repairing hardware.", "A reboot alone never marks a device recovered; failed checks leave it quarantined."],
             ask=[("What exactly is self-healing?", "A planned, checked sequence for compromise classes we define: revoke the session, preserve evidence, enter safe mode, verify state, restore known-good configuration, re-authenticate with the PQC layer, validate, then rebuild trust gradually. It is designed in our decisions document and not implemented.")],
             terms="'Recovery for defined compromise classes'. Never 'the system heals itself'.",
             acknowledge="Firmware/config hashes reported by a compromised device are evidence, not proof."),
         sources=["docs/technical-decisions.md (TD-10)"]),

    dict(id="E18", kind="figure", tag="MIXED", figure=DIAG + "16_esp32_status.png",
         notes=dict(
             proves="Transparent ESP32 status.",
             say=["Architecture is prepared and the gateway verifies the HMAC device profile, tested with a software agent.", "A firmware project exists but has never been validated on a board; the exact board is not confirmed.",
                  "ESP32-side PQC is not claimed; the R1 feasibility experiment is pending."],
             ask=[("Why is the ESP32 not using PQC?", "We do not claim it until implemented and tested there. Whether ML-DSA verification is practical on an ESP32 is experiment R1, which has not run because no board is connected. The architecture stays the same either way.")],
             terms="'Feasibility experiment R1'. Never imply the ESP32 does PQC.",
             acknowledge="PlatformIO is installed on the laptop but the toolchain is not downloaded and nothing has been flashed."),
         sources=["hardware/esp32/README.md", "docs/implementation-roadmap.md (R1)"]),

    dict(id="E19", kind="rows", tag="MIXED", title="Limitations",
         items=["Dynamic trust, quarantine and recovery are not implemented",
                  "ESP32: firmware unvalidated, board unconfirmed, no ESP32-side PQC",
                  "PQC library: not audited by us, verified on Windows x86-64, no FIPS 140 validation",
                  "ML-KEM session is our composition of standard primitives, with no external review",
                  "Single-host trust domain; session state is in memory",
                  "YOLO11n is AGPL-3.0; false positives and negatives are possible and unmeasured"],
         notes=dict(
             proves="We know the boundaries of our claims.",
             say=["These six matter most.", "More detail is in the appendix: the webcam is not cryptographically bound to the ESP32, tokens travel over plain HTTP on a trusted LAN, camera-obstruction thresholds are unvalidated, and only a software agent exercised the device path."],
             ask=[("What happens if the gateway is compromised?", "Then the protections end: it holds the master key, the database and the verification logic. That is out of scope for the prototype and we say so."),
                  ("Is the system actually quantum-safe?", "No system-wide claim. Post-quantum cryptography is used on the vision-service to gateway path (ML-DSA-65 authenticates observations; the optional ML-KEM-768 session encrypts them); the ESP32 uses HMAC-SHA256; the trust and recovery layers do not exist yet.")],
             terms="'Defined threat model', 'prototype'.",
             acknowledge="This whole slide."),
         sources=["pqc/README.md", "ai/README.md", "backend/README.md"]),

    dict(id="E20", kind="figure", tag="PLANNED", figure=DIAG + "17_roadmap.png",
         notes=dict(
             proves="Where the project goes next, in order.",
             say=["Trust specification first, then the trust engine, attack simulation, quarantine, recovery, evidence chain, digital twin and dashboard.", "In parallel: confirm the ESP32 board, validate firmware, run experiment R1."],
             ask=[("What will you do first?", "Write the trust-model specification and its deterministic test matrix; nothing gets coded until it is consistent.")],
             terms="'Planned' for every amber item.", acknowledge="Everything to the right is not started."),
         sources=["docs/implementation-roadmap.md"]),

    dict(id="E21", kind="bullets", tag="MIXED", title="Key takeaway",
         headline="Trust should be continuous. Authenticity is an input, not the decision.",
         bullets=["BUILT: authenticated observations with a post-quantum layer (347/347 tests)",
                  "MEASURED: NIST vectors agree; 11/11 signed observations re-verified; tampered 401, replayed 409",
                  "NEXT: specify, then build, the trust engine, quarantine and recovery"],
         callout="The ESP32 authenticates with HMAC-SHA256, which is not post-quantum.",
         notes=dict(
             proves="One-sentence thesis plus the honest split.",
             say=["Authenticity tells you who said something; trust asks whether to believe and allow it.", "We built and measured the authenticated observation layer that a trust engine will consume."],
             ask=[], terms="Thesis: 'Continuous cyber-physical trust with post-quantum security and a planned recovery loop.'",
             acknowledge="Trust and recovery are next."),
         sources=["ppt/references/verified-facts.md"]),
]

APPENDIX = [
    dict(id="A1", kind="figure", tag="IMPLEMENTED", figure=DIAG + "09_authenticity_is_not_trust.png",
         notes=dict(proves="Authentication proves provenance, not device health.", say=["A valid signature or HMAC tag does not prove the device is uncompromised."],
                    ask=[("Why keep authenticity separate from AI confidence?", "So a confident detector can never bypass a failed signature, and a valid signature can never hide an anomaly.")],
                    terms="'Provenance', 'possession of the provisioned secret'.", acknowledge="The trust engine that uses this principle is not built."),
         sources=["ppt/diagrams/09_authenticity_is_not_trust.png"]),
    dict(id="A2", kind="figure", tag="MEASURED", figure=ASSET + "08_test_summary.png",
         notes=dict(proves="Test counts by area.", say=["347 pass; the 182 tests that existed before Phase 3 are unchanged."], ask=[], terms="Counts are collected by pytest at build time.",
                    acknowledge="Tests cover implemented behaviour only."), sources=["python -m pytest"]),
    dict(id="A3", kind="figure", tag="IMPLEMENTED", figure=DIAG + "04_security_domains.png",
         notes=dict(proves="Security domains at a glance.", say=["Operator and ingest tokens are classical and separate from device HMAC and from PQC signatures."],
                    ask=[], terms="'Token-only ingest path' is labelled ingest-token and can be disabled.", acknowledge="Tokens travel over plain HTTP on a trusted LAN."),
         sources=["docs/technical-decisions.md (TD-17)"]),
    dict(id="A4", kind="table", tag="MIXED", title="Threat model: what is established today",
         header=("Threat", "Current status", ""),
         rows=[("Modified or forged observation", "rejected (tested, real run)", ""), ("Replay", "rejected: 409 in window, 401 stale (tested)", ""),
               ("Delayed genuine observation", "accepted within the 300 s window", ""), ("Stolen device HMAC secret", "impersonation possible; not detectable yet", ""),
               ("Compromised vision service", "can sign false observations; scope-limited, revocable", ""), ("Compromised gateway host", "not protected (out of scope)", ""),
               ("Sensor spoofing / physical tamper", "not addressed yet (needs ESP32 + trust engine)", ""), ("AI false positives / negatives", "possible; not measured", "")],
         notes=dict(proves="An honest threat model for the current milestone.", say=["We list what the current architecture cannot establish."],
                    ask=[("Does the trust engine fix these?", "Some it will help detect; others (gateway compromise) remain out of scope.")],
                    terms="'Defined threat model'.", acknowledge="The threat model for the trust engine is not yet written."),
         sources=["pqc/README.md", "backend/README.md"]),
    dict(id="A5", kind="rows", tag="MIXED", title="More limitations (detail)",
         items=["The webcam is not cryptographically bound to the ESP32; the vision service is trusted by its key and configured device id",
                  "Tokens (operator, ingest) travel over plain HTTP; use on a trusted LAN only",
                  "Device secrets are encrypted at rest, but the master key sits on the same host",
                  "Camera-obstruction thresholds are unvalidated defaults; no accuracy or false-positive measurement",
                  "Only a software device agent has exercised the device path; no real ESP32 telemetry",
                  "Ultralytics YOLO is AGPL-3.0; no legal review"],
         notes=dict(proves="The details behind the limitations slide.", say=["Read only what a judge asks about."], ask=[], terms="", acknowledge="All of it."),
         sources=["backend/README.md", "ai/README.md", "pqc/README.md"]),
]

SUBMISSION_REFS = [
    "NIST FIPS 203 (ML-KEM): https://csrc.nist.gov/pubs/fips/203/final",
    "NIST FIPS 204 (ML-DSA): https://csrc.nist.gov/pubs/fips/204/final",
    "NIST ACVP-Server test vectors: https://github.com/usnistgov/ACVP-Server (commit 975de31)",
    "pqcrypto 1.0.0, Apache-2.0: https://pypi.org/project/pqcrypto/",
    "Ultralytics YOLO11n, AGPL-3.0: https://github.com/ultralytics/ultralytics",
]
