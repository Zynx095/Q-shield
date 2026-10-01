# BUILD CHECKPOINT

**CURRENT PHASE:** all of Phases 5–11 are complete. This is a stable checkpoint and everything is committed.
**CURRENT FEATURE:** none in progress. Last done: background recovery-deadline timer (`RecoveryTimer`, `RECOVERY_TICK_S`).

**WHAT WAS IMPLEMENTED:** attack simulation, quarantine enforcement, recovery orchestrator, ML-DSA evidence chain,
digital twin, dashboard, integrated demo, and an engine fix for the out-of-order rule. See `docs/IMPLEMENTATION_STATUS.md`.

**TESTS RUN / RESULT:** full suite, 618 passed, 0 failed.

**KNOWN BUGS:** none open. The webcam demo step is unverified this session (no camera attached).

**CURRENT BLOCKER:** none.

**EXACT NEXT TASK:** the first open item under "WHAT IS LEFT" in `docs/IMPLEMENTATION_STATUS.md`: attach a camera and
run `python scripts/demo_full.py --webcam` (needs hardware). The next software task is dashboard operator actions (start/abort recovery, set twin expected state from the UI, through the existing operator API).

**IMPORTANT ARCHITECTURAL CONTEXT:**
- `create_app(settings, ..., trust, twin, evidence, recovery)`. All four are optional; without `trust` the Phase 1–3 behaviour is unchanged (no enforcement).
- Enforcement runs in `app.py` `enforce()`, after authentication. Recovery-channel routes and control routes live in `backend/api/security_routes.py`.
- `TrustService.listeners` feed the evidence chain (`EvidenceRecorder.on_trust_change`).
- The trust engine must never score enforcement or control events (see `EXCLUDED` in `backend/trust/adapters.py`).
- `RecoveryOrchestrator` holds an RLock around start/abort/tick. `RecoveryTimer` runs process_pending()+tick() on a daemon thread and is registered on app startup/shutdown (`app.state.recovery_timer`).
- The full-stack test fixture is in `tests/fullstack/conftest.py`.

**COMMAND TO VERIFY CURRENT STATE:**
```
python -m pytest -o addopts="" -q && python scripts/demo_full.py
```
