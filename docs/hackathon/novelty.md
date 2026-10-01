# Project Novelty

The novelty of Q-SHIELD is the **closed loop**, not any single mechanism. Authentication is followed by continuous,
evidence-based trust; quarantine is enforced at the gateway; recovery has to be earned with fresh authenticated
evidence; and every decision lands in a signed evidence chain. Each theme below names what is implemented and where
it stops.

1. **Continuous dynamic device trust.** A deterministic, explainable trust engine re-scores every device from every
   authenticated message, observation and security event. Every score change lists the reasons that sum to it
   (`backend/trust/`).

2. **Cross-modal correlation.** Physical, sensor, configuration, network and visual evidence are scored separately.
   A confirmed incident needs two independent kinds of evidence inside a 60 s window, for example an authenticated
   tamper report and a signed camera observation. Forged or replayed traffic adds only bounded pressure (at most 25
   points), so it can never quarantine a device on its own.

3. **Post-quantum-signed evidence.**
   - The vision service signs every observation with ML-DSA-65 and can send it inside an ML-KEM-768 session
     (AES-256-GCM, HKDF-SHA256).
   - The gateway signs every evidence-chain entry with ML-DSA-65.
   - The **device** path is HMAC-SHA256 and is **not** post-quantum. ESP32 PQC feasibility is an open research item.

4. **Vision as evidence, not as a verdict.** YOLO11n reports what the camera sees, and camera health reports
   obstruction or loss. Only the trust engine decides what that means for a device. Sensor checks are configured
   ranges, not machine learning.

5. **Digital twin.** The expected (known-good) state, set by an operator, is compared with the device's
   authenticated self-reports, field by field and with the time each field was last reported. A match is evidence,
   not attestation.

6. **Tamper-evident evidence chain.** It is SHA-256 linked and ML-DSA-65 signed, and verification finds an edited,
   reordered or removed entry. It is not anchored externally.

7. **Quarantine and earned recovery.**
   - Quarantine is automatic and enforced at the gateway.
   - Recovery is started by an operator, and is then automated and verified: a remediation command, health checks
     judged on each report, then a trust ramp.
   - Every failure path returns the device to quarantine.

   This is software remediation; it cannot repair hardware.
