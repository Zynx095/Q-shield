# BUILD CHECKPOINT

**CURRENT PHASE:** Phases 5-13 are complete. Phase 13 = operator identity, roles, attribution, TLS.
**CURRENT FEATURE:** none in progress. See IMPLEMENTATION_STATUS "OPERATOR IDENTITY + TLS (Phase 13)".

**WHAT WAS IMPLEMENTED:** attack simulation, quarantine enforcement, recovery orchestrator, ML-DSA evidence chain,
digital twin, dashboard, integrated demo, and an engine fix for the out-of-order rule. See `docs/IMPLEMENTATION_STATUS.md`.

**TESTS RUN / RESULT:** full suite, 677 passed, 0 failed (Phase 13 added tests/fullstack/test_operator_identity.py and tests/security/test_tls.py).

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
- The full-stack test fixture is in `tests/fullstack/conftest.py`.

**COMMAND TO VERIFY CURRENT STATE:**
```
python -m pytest -o addopts="" -q && python scripts/demo_full.py
```
