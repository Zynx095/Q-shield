# BUILD CHECKPOINT

**CURRENT PHASE:** Phases 5-14 are complete. Phase 14 = command-center UI rework (dashboard/) plus the read-only `GET /api/v1/system`.
**CURRENT FEATURE:** none in progress. See IMPLEMENTATION_STATUS "COMMAND CENTER UI (Phase 14)" and dashboard/README.md.

**WHAT WAS IMPLEMENTED:** attack simulation, quarantine enforcement, recovery orchestrator, ML-DSA evidence chain,
digital twin, dashboard, integrated demo, and an engine fix for the out-of-order rule. See `docs/IMPLEMENTATION_STATUS.md`.

**TESTS RUN / RESULT:** full suite, 683 passed, 0 failed (includes 13 dashboard JS unit tests through Node).

**KNOWN BUGS:** none open. The webcam demo step is unverified this session (no camera attached).

**CURRENT BLOCKER:** none.

**EXACT NEXT TASK:** (1) User: `python scripts/demo_full.py --webcam` with a camera. (2) User: a manual browser check of the dashboard over HTTPS with a named operator (commands in IMPLEMENTATION_STATUS "HOW TO RUN"). (3) Next coding item: switch `demo_full.py` to a named operator over TLS (it still uses the bootstrap token over HTTP). Then do the external anchoring of the evidence head (TD-09).

**IMPORTANT ARCHITECTURAL CONTEXT:**
- `create_app(settings, ..., trust, twin, evidence, recovery)`. All four are optional; without `trust` the Phase 1–3 behaviour is unchanged (no enforcement).
- Enforcement runs in `app.py` `enforce()`, after authentication. Recovery-channel routes and control routes live in `backend/api/security_routes.py`.
- `TrustService.listeners` feed the evidence chain (`EvidenceRecorder.on_trust_change`).
- The trust engine must never score enforcement or control events (see `EXCLUDED` in `backend/trust/adapters.py`).
- `RecoveryOrchestrator` holds an RLock around start/abort/tick. `RecoveryTimer` runs process_pending()+tick() on a daemon thread and is registered on app startup/shutdown (`app.state.recovery_timer`).
- Twin expected state is frozen (409) while a recovery is active. The dashboard PUT merges the existing expected fields and edits only fw/cfg.
- Operator auth: `_operator_guard(role)` in app.py sets `request.state.operator`. `require_operator` = viewer, `require_actor` = operator, `require_admin` = admin. Attribution goes through `audit()`/`attempt()` in security_routes.py (an operator_action event plus an evidence entry).
- TLS: `tls_options()` in backend/security/tls.py is used by backend/main.py. Files: backend/security/{operators,tls}.py, scripts/{operators,gen_dev_cert}.py.
- Dashboard: ES modules in dashboard/src (no build). All routes are listed in `src/lib/api.js` ROUTES (contract-tested). View models live in `src/lib/derive.js` (pure, node-tested). Rendering uses the escaping `html` template plus the in-place `morph` renderer. Operator dialogs are in `src/actions.js` and `components/modal.js`.
- The full-stack test fixture is in `tests/fullstack/conftest.py`.

**COMMAND TO VERIFY CURRENT STATE:**
```
python -m pytest -o addopts="" -q && python scripts/demo_full.py
```
