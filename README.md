# Q-SHIELD

**Quantum-Resilient Self-Healing AIoT Security Architecture**

> **STATUS: WORKING PROTOTYPE, PHASES 0-3 (see "Current Development Status" below)**

## Problem
Conventional IoT security often relies on static device authentication and fragmented monitoring mechanisms, while AIoT systems increasingly combine physical sensors, machine learning and network connectivity. This creates a need for security architectures that can continuously evaluate device trust across cyber and physical signals, remain resilient against future quantum threats, detect compromised or manipulated devices, preserve trustworthy security evidence, and autonomously recover from defined classes of compromise.

## Proposed Solution
Q-SHIELD is a quantum-resilient, self-healing AIoT security architecture that continuously evaluates device trust using AI-driven cyber-physical intelligence, protects device identity and communication using post-quantum cryptography, creates tamper-evident security evidence, and autonomously isolates and recovers devices from defined classes of compromise.

## Core Architecture
- **ESP32**: Physical IoT endpoint, sensor acquisition, telemetry, tamper detection, and device state.
- **Laptop Gateway**: Primary AI compute, PQC gateway, backend server, trust engine, digital twin, dashboard host, and recovery orchestration.

### The Lifecycle Pipeline
1. **OBSERVE**: Gather data from physical sensors, cameras, and network.
2. **DETECT**: Identify cyber-physical anomalies using AI.
3. **VERIFY**: Cryptographically verify integrity with PQC.
4. **DYNAMIC TRUST**: Continuously calculate a dynamic trust score.
5. **QUARANTINE**: Isolate anomalous devices automatically.
6. **RECOVER**: Execute predefined safe-mode recovery procedures.
7. **RE-AUTHENTICATE**: Issue new trust challenges.
8. **VALIDATE**: Assess device health.
9. **RESTORE TRUST**: Bring device back into trusted operations.

## Novelty
Our novelty lies in the **integrated, closed-loop architecture** rather than individual mechanisms. We combine:
- **Continuous dynamic device trust** rather than one-time authentication.
- **Cyber + physical + visual + network signal correlation**.
- **PQC-backed device identity and secure communication**.
- **AI-assisted sensor/behaviour consistency checking**.
- **Digital twin** for expected-vs-observed device state.
- **Tamper-evident incident evidence chain**.
- **Autonomous quarantine and recovery**, followed by trust rebuilding.

## Hardware Components
### Physical (IoT Node)
- ESP32
- Camera
- Sensors: BME280, MPU6050, Reed switch (tamper sensor)
- Outputs: OLED display, Buzzer, RGB LED, (Optional) Servo

### Compute Platform
- Laptop (running AI inference, backend, PQC gateway, DB, dashboard)

## Software Components
- **Backend**: Manages evidence, trust scoring, recovery policies, digital twins.
- **AI Engine**: Vision models, anomaly detection, sensor data fusion.
- **PQC Module**: ML-KEM and ML-DSA integrations.
- **Dashboard**: Frontend to visualize device trust, network architecture, and security events.
- **Attack Simulator**: Local tool to trigger and demonstrate cyber-physical attacks and recovery.

## Current Development Status
**Prototype, Phases 0-3 implemented; 347/347 automated tests pass.** Trust engine, quarantine, recovery, evidence chain, digital twin and dashboard are **not yet implemented** (the trust model specification is the next step).

Implemented and tested:
- **Gateway** (FastAPI + SQLite): device registration, heartbeat, telemetry with per-device HMAC-SHA256 authentication (not post-quantum) and replay protection; device status; operator and ingest bearer-token APIs; device secrets encrypted at rest. Exercised with a software device agent.
- **Vision pipeline**: USB webcam, YOLO11n (AGPL-3.0), configurable zones, camera-health events, normalized observation schema. Output is observations, not trust decisions.
- **Post-quantum layer** (gateway + vision service): ML-KEM-768 and ML-DSA-65 via `pqcrypto` 1.0.0; NIST ACVP known-answer tests; ML-DSA-signed observations; optional ML-KEM session with AES-256-GCM; key provisioning, rotation and revocation. See `pqc/README.md`.

Not done: the ESP32 firmware is an untested skeleton (no board has been connected or flashed), and the ESP32 does **not** run post-quantum cryptography. Evidence: `docs/results/`, `pqc/README.md`, `ai/README.md`, `backend/README.md`. Decisions and limitations: `docs/technical-decisions.md`. Presentation source material: `ppt/`.

## Planned Demo
Demonstrate the complete closed loop: a device or its environment is attacked in a controlled local simulation, the AI/trust engine detects it, quarantines the device, preserves evidence, runs a recovery sequence and restores trust gradually. **Today the observe -> authenticate -> analyze part runs for real (webcam, signed observations, rejection of modified and replayed messages); trust, quarantine and recovery are the next phases.**

## Development Roadmap
See `docs/implementation-roadmap.md`. Status: Phase 0/1 (foundation, device slice) done; Phase 2 (vision) done; Phase 3 (PQC) done; Phase 4 (trust engine) specification pending; later phases (attack simulation, quarantine, recovery, evidence chain, digital twin, dashboard) not started. ESP32 hardware bring-up and the ESP32 PQC feasibility experiment remain open.
