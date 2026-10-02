# Testing

```
python -m pytest -o addopts="" -q            # everything below, including the dashboard JS tests (run through Node)
node --test dashboard/tests/*.test.mjs       # the dashboard JS tests on their own
python scripts/make_device_vectors.py --check
```

**785 Python tests, 0 failing; 40 JS tests.** The Python count includes one pytest case that runs the JS suite.
These counts are from Phase 17 (2026-10-02). The suite takes about 1.5 to 3 minutes, depending on machine load. No
test needs a camera, a GPU, a network or an ESP32.

| Area (`tests/…`) | Collected | What it covers |
|---|---|---|
| `trust/` | 235 | The trust-engine specification equation by equation, scoring, caps, decay, the state machine, recovery semantics, adversarial input, and the camera as a security boundary (`test_camera_boundary.py`). |
| `security/` | 149 | Device HMAC auth, replay and counters, operator identities and roles, TLS options, signed observations (forged, stale, future, unknown, retired, revoked signer), ML-KEM sessions (handshake replay, session cap, `session_expired`), and device-protocol test vectors. |
| `ai/` | 135 | Observation schema, zones and config, pipeline emission, sinks and runner, camera warm-up, and camera security on synthetic frames (occlusion versus lighting, viewpoint, rotation, frozen feed, blur, blinding, proximity, source labelling). |
| `fullstack/` | 111 | The real gateway app over HTTP with trust, twin, evidence, recovery and enforcement: attacks, quarantine, recovery (including stale-twin health checks), rejection floods, camera boundary end to end, and the dashboard contract. |
| `pqc/` | 74 | NIST ACVP conformance for ML-KEM-768 and ML-DSA-65, interoperability, and behaviour. |
| `integration/` | 47 | Phase 1 flow, the signed vision sink, session churn, device sensor sources, production wiring. |
| `twin/` | 18 | Expected against observed state, per-report comparison, freshness. |
| `evidence/` | 15 | Chain linking, signatures, tampering, deletion, reordering, and the verification cache. |
| `end_to_end/` | 1 | `scripts/demo_full.py` against a real uvicorn gateway. |

## Rules the tests follow

- **A regression test must fail before its fix.** Every bug fixed since Phase 16 was confirmed that way: the fix was
  reverted or sabotaged and the test failed. The commit messages say so.
- **Simulated means labelled.** Attack traffic comes from `attack_simulation/`, and synthetic frames and detections
  are built in the tests. Nothing is presented as camera or hardware output.
- **Frozen clocks, fresh noise.** The trust and gateway tests drive a fake clock. Camera tests add fresh sensor noise
  to every synthetic frame, because a live camera never repeats a frame exactly and repeated frames are the
  frozen-feed signal.
- **Byte-exact device vectors.** `tests/vectors/envelope_v1_cases.json` is generated from the reference
  implementation. The test fails if it drifts.

## What the tests do not show

- Detection accuracy, and camera-health false-alarm or miss rates on a real scene. The thresholds are unvalidated.
- Anything on an ESP32. The firmware has never been compiled.
- Behaviour under real network conditions, several gateways, or long runs.

Live checks are recorded separately in `IMPLEMENTATION_STATUS.md`: USB camera runs, the full webcam demo, and the
dashboard-against-API comparison.
