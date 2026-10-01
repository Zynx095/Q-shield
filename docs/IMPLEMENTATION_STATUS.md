# Q-SHIELD — Implementation Status

Persistent project memory. Read together with `docs/BUILD_CHECKPOINT.md`.
Last updated: 2026-09-30.

## CURRENT PHASE
Phases 0–11 implemented, tested, and exercised by the integrated demo. Remaining work is listed under **WHAT IS LEFT**.

## TEST COUNT
**614 passed, 0 failed** (`python -m pytest -o addopts="" -q`, ~2 min). The baseline before the continuous build was 544.

## COMPLETED
| Phase | Feature | Status | Key code | Tests |
|---|---|---|---|---|
| 0–1 | Foundation; device↔gateway (HMAC-SHA256 envelope, replay counter, operator and ingest tokens) | VERIFIED | `backend/api/app.py`, `backend/security/auth.py` | `tests/security`, `tests/integration` |
| 2 | Vision: real webcam + YOLO11n, zones, camera health | VERIFIED (accuracy not measured) | `ai/vision/` | `tests/ai` |
| 3 | PQC: ML-KEM-768 / ML-DSA-65 (pqcrypto), signed observations, ML-KEM + AES-256-GCM session, ACVP vectors | VERIFIED | `backend/security/` | `tests/pqc`, `tests/security` |
| 4 / 4.1 | Dynamic trust engine: deterministic, explainable, caps, decay, state machine, recovery semantics | VERIFIED | `backend/trust/` | `tests/trust` |
| 5 | Attack simulation: 11 scenarios run through the real gateway; results are read back, not asserted | IMPLEMENTED + TESTED (traffic is SIMULATED and labelled) | `attack_simulation/simulator.py` | `tests/fullstack/test_attacks.py` |
| 6 | Quarantine **enforcement**: normal / recovery / control channels, applied after authentication | IMPLEMENTED + TESTED | `backend/security/enforcement.py`, `backend/api/app.py`, `backend/api/security_routes.py` | `tests/fullstack/test_quarantine.py` |
| 7 | Recovery orchestrator: remediation → health checks → VERIFIED → trust ramp → RECOVERED → TRUSTED; every failure path returns to QUARANTINED | IMPLEMENTED + TESTED | `backend/recovery/orchestrator.py` | `tests/fullstack/test_recovery.py` |
| 8 | Evidence chain: append-only, SHA-256-linked, ML-DSA-65-signed; tamper / delete / reorder / forged-signature detection | IMPLEMENTED + TESTED | `backend/evidence/chain.py` | `tests/evidence/test_chain.py` |
| 9 | Digital twin: expected vs observed state, MATCH / MISMATCH / UNKNOWN, feeds per-device trust expectations | IMPLEMENTED + TESTED | `backend/twin/twin.py` | `tests/twin/test_twin.py` |
| 10 | Dashboard ("Security Command Center"): static page served at `/dashboard`, operator API only | IMPLEMENTED (visually QA'd via headless Edge) | `dashboard/` | smoke test in `test_quarantine.py` |
| 11 | Integrated demo on a real uvicorn gateway: TRUSTED → SUSPICIOUS → QUARANTINED → RECOVERING → VERIFIED → RECOVERED → TRUSTED | IMPLEMENTED + TESTED | `scripts/demo_full.py` | `tests/end_to_end/test_demo_full.py`; transcript in `docs/results/demo-full-run.txt` |
| — | Production wiring: `python -m backend.main` builds trust + twin + signed evidence + recovery (evidence key auto-created, sealed under the master key) | IMPLEMENTED + TESTED + live-smoke-tested | `backend/main.py` | `tests/integration/test_main_services.py` |

## BUG FOUND AND FIXED DURING THE BUILD
Trust engine, out-of-order rule: with a real clock, a time-driven evaluation that ran between a message's receipt and
its processing (an enforcement check or a dashboard poll) made legitimate messages count as "out of order", so they
earned no recovery credit. Recovery was silently about 3× slower and nondeterministic. The frozen test clock could not
show this; the live demo did. The fix: out of order now means older than the last applied **signal**. Documented in
trust-engine.md §6.4 and covered by regression tests.

## HOW TO RUN
```
python -m pytest -o addopts="" -q                   # full suite
python scripts/demo_full.py                         # full story on a real gateway (scratch state)
python scripts/demo_full.py --pace 2 --hold         # presentation pacing; keeps the gateway up for the dashboard
python scripts/demo_full.py --webcam                # adds the real webcam + YOLO11n step (needs a camera)
```
The demo prints the dashboard URL with the operator token.

## KNOWN LIMITATIONS (honest)
- All device data is SIMULATED (software agent). The ESP32 firmware has never been compiled or flashed, and its path is HMAC-SHA256 only (not PQC).
- No physical tamper test was ever performed.
- The webcam step of the new demo was **not** re-run live this session because no camera was attached. The vision pipeline was live-verified in Phases 3–4.
- Twin observed state is self-reported: it is evidence, not attestation.
- The trust ramp takes about 40 minutes of clean evidence at the documented parameters. The demo uses a clearly labelled TIME-LAPSE clock and does not change parameters.
- Trust parameters are design choices and have not been calibrated against data (trust-engine.md §16).
- The custom ML-KEM session protocol has had no external review. There is no TLS. Tokens travel over plain HTTP, so use a trusted LAN only.
- The evidence chain has no external anchoring. Anyone holding both the DB and the evidence key can rewrite history.
- Recovery deadlines are evaluated by a background `RecoveryTimer` (every `RECOVERY_TICK_S`, default 5 s; 0 disables) as well as on each request.
- The service is single-process and single-gateway (SQLite).

## WHAT IS LEFT
| Priority | Item | Notes |
|---|---|---|
| High | Run `demo_full.py --webcam` live with a camera attached | Code path exists; not re-verified this session |
| High | Real ESP32: compile, flash, wire the tamper switch and sensors, replace the software agent | Biggest credibility gap |
| Done | Background timer for recovery deadlines | `RecoveryTimer` in `backend/recovery/orchestrator.py`, started/stopped with the gateway; tests in `tests/fullstack/test_recovery_timer.py` |
| Medium | Dashboard: operator actions (start recovery, set twin) from the UI | Currently read-only; control is via the API |
| Medium | TLS for the gateway; per-operator tokens | TD-17 |
| Medium | Update the audit PDF and the PPT to reflect Phases 5–11 | Both still describe Phases 5–10 as planned |
| Low | External anchoring of the evidence head; key rotation | TD-09, TD-15 |
| Research | Calibrate trust parameters; measure vision accuracy; external review of the session protocol | trust-engine.md §16 |
