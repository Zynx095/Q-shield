# BUILD CHECKPOINT

**CURRENT PHASE:** Phases 5–11 plus Phase 12 (operator controls) are complete. This is a stable checkpoint and everything is committed.
**CURRENT FEATURE:** none in progress. Last done: operator controls (API hardening + dashboard actions card); see IMPLEMENTATION_STATUS "OPERATOR CONTROLS".

**WHAT WAS IMPLEMENTED:** attack simulation, quarantine enforcement, recovery orchestrator, ML-DSA evidence chain,
digital twin, dashboard, integrated demo, and an engine fix for the out-of-order rule. See `docs/IMPLEMENTATION_STATUS.md`.

**TESTS RUN / RESULT:** full suite, 649 passed, 0 failed.

**KNOWN BUGS:** none open. The webcam demo step is unverified this session (no camera attached).

**CURRENT BLOCKER:** none.

**EXACT NEXT TASK:** (1) User: run `python scripts/demo_full.py --webcam` with a camera (without one it fails gracefully). (2) Manual browser click-through of the dashboard Operator actions card: `python scripts/demo_full.py --hold`, then open the printed URL. (3) Next coding item: TLS + per-operator tokens (TD-17), so operator actions carry an operator identity.

**IMPORTANT ARCHITECTURAL CONTEXT:**
- `create_app(settings, ..., trust, twin, evidence, recovery)`. All four are optional; without `trust` the Phase 1–3 behaviour is unchanged (no enforcement).
- Enforcement runs in `app.py` `enforce()`, after authentication. Recovery-channel routes and control routes live in `backend/api/security_routes.py`.
- `TrustService.listeners` feed the evidence chain (`EvidenceRecorder.on_trust_change`).
- The trust engine must never score enforcement or control events (see `EXCLUDED` in `backend/trust/adapters.py`).
- `RecoveryOrchestrator` holds an RLock around start/abort/tick. `RecoveryTimer` runs process_pending()+tick() on a daemon thread and is registered on app startup/shutdown (`app.state.recovery_timer`).
- Twin expected state is frozen (409) while a recovery is active. The dashboard PUT merges the existing expected fields and edits only fw/cfg.
- The full-stack test fixture is in `tests/fullstack/conftest.py`.

**COMMAND TO VERIFY CURRENT STATE:**
```
python -m pytest -o addopts="" -q && python scripts/demo_full.py
```
