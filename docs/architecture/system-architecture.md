# System Architecture (as implemented)

Q-SHIELD has three kinds of client and one gateway. Each client authenticates differently, and the authentication
methods are never interchangeable.

```mermaid
flowchart LR
    subgraph Clients
        DEV["Device<br/>(software agent today; ESP32 skeleton not flashed)"]
        VIS["Vision service<br/>(OpenCV + YOLO11n, camera-health + proximity checks)"]
        OPS["Operator<br/>(dashboard / API)"]
    end

    subgraph Gateway ["Gateway (FastAPI + SQLite, laptop)"]
        AUTH["Device authentication<br/>HMAC-SHA256 envelope + replay counter"]
        REJ["Rejection recorder<br/>sampled + coalesced, bounded retention"]
        PQC["PQC verification<br/>ML-DSA-65 signature, optional ML-KEM-768 session<br/>(AES-256-GCM, HKDF-SHA256)"]
        OPA["Operator authentication<br/>named bearer tokens, roles"]
        ENF["Enforcement<br/>normal channel / recovery channel"]
        TRUST["Trust engine<br/>deterministic, explainable"]
        TWIN["Digital twin<br/>expected vs self-reported"]
        REC["Recovery orchestrator<br/>+ background deadline timer"]
        EV["Evidence chain<br/>SHA-256 linked, ML-DSA-65 signed"]
        DASH["Dashboard (static)<br/>reads the operator API only"]
    end

    DEV -- "register / telemetry (normal channel)<br/>recovery reports (recovery channel)" --> AUTH
    AUTH --> ENF
    AUTH -- "rejected" --> REJ
    PQC -- "rejected" --> REJ
    REJ --> TRUST
    VIS -- "signed observations" --> PQC
    OPS --> OPA
    OPA -- "start / abort recovery, known-good state, quarantine" --> REC
    ENF --> TRUST
    PQC --> TRUST
    TWIN --> TRUST
    TRUST --> ENF
    TRUST --> EV
    REC --> TRUST
    REC -- "remediation command (recovery channel)" --> DEV
    REC --> EV
    OPA --> EV
    DASH --> OPA
```

## Responsibilities

- **Device.** Sends HMAC-SHA256 authenticated register, heartbeat and telemetry messages: tamper switch, sensors,
  firmware version and configuration hash. Today this is a software agent (`device_agent/`) labelled Simulated. The
  ESP32 firmware in `hardware/esp32/` is an untested skeleton.
- **Vision service** (`ai/vision/`). Runs YOLO11n on webcam frames and reports detections and camera-health changes
  as observations. The camera itself is watched: obstructed, frozen, view changed or degraded, plus image-space
  proximity heuristics (`health.py`, `proximity.py`). The client re-handshakes only on `session_expired`, backs off
  and has an hourly handshake budget (`signed_sink.py`). Each observation is ML-DSA-65 signed by the service's own key (the webcam has no cryptographic
  identity), and can be sent inside an ML-KEM-768 session. It reports what it sees; it decides nothing about trust.
- **Gateway.**
  - Authenticates each kind of client. Routine rejections are sampled and coalesced (`backend/security/rejections.py`),
    so a flood cannot grow storage without bound.
  - Enforces quarantine after authentication.
  - Runs the trust engine over its own records.
  - Keeps the digital twin and drives recovery.
  - Appends every decision to the evidence chain.
  - Serves the dashboard as static files.
- **Operator.** A named identity with a role (viewer, operator or admin). Every action is attributed in the evidence
  chain.

Device integration (simulated agent, replayed recordings, future ESP32) shares one protocol:
`../hardware/device-protocol.md` and `../hardware/hardware-architecture.md`.

The trust model is specified in `trust-engine.md`. Design decisions and their limits are in
`../technical-decisions.md`.
