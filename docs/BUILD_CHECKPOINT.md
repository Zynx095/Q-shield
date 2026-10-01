# BUILD CHECKPOINT

**CURRENT PHASE:** Phases 5-16 are complete.
- Phase 14: command-center UI rework (dashboard/) plus the read-only `GET /api/v1/system`.
- Phase 15: premium visual pass plus the Camera & vision page.
- Phase 16: final hardening and demo readiness (recovery health checks per report, atomic handshake nonce,
  evidence-verify cache, camera warm-up, observation transport, forensic case file, demo fixes, honest docs).

**CURRENT FEATURE:** none in progress. See IMPLEMENTATION_STATUS "FINAL HARDENING + DEMO READINESS (Phase 16)".

**WHAT WAS IMPLEMENTED:** attack simulation, quarantine enforcement, recovery orchestrator, ML-DSA evidence chain,
digital twin, dashboard, integrated demo, and an engine fix for the out-of-order rule. See `docs/IMPLEMENTATION_STATUS.md`.

**TESTS RUN / RESULT:** full suite, 695 passed, 0 failed (includes the 38 dashboard JS unit tests, run through Node).

**KNOWN BUGS:** none open.
- The browser camera preview was verified only with Edge's fake camera.
- The configured USB camera (index 1) was not attached during Phase 16. The webcam demo was run on the built-in
  camera through a scratch config.

**CURRENT BLOCKER:** none.

**EXACT NEXT TASK:**
- (0) User: with the USB camera attached, run `python -m ai.vision probe --config config/vision.json`, then
  `python scripts/demo_full.py --webcam --pace 2 --hold` (runbook: `docs/hackathon/demo-plan.md`). Keep the right
  half of the camera view clear for the scripted story.
- (1) User: open `#/vision` on localhost and preview the built-in camera while the demo uses the USB camera. (2) User: a manual browser check of the dashboard over HTTPS with a named operator (commands in IMPLEMENTATION_STATUS "HOW TO RUN"). (3) Next coding item: switch `demo_full.py` to a named operator over TLS (it still uses the bootstrap token over HTTP). Then do the external anchoring of the evidence head (TD-09).

**IMPORTANT ARCHITECTURAL CONTEXT:**
- `create_app(settings, ..., trust, twin, evidence, recovery)`. All four are optional; without `trust` the Phase 1–3 behaviour is unchanged (no enforcement).
- Enforcement runs in `app.py` `enforce()`, after authentication. Recovery-channel routes and control routes live in `backend/api/security_routes.py`.
- `TrustService.listeners` feed the evidence chain (`EvidenceRecorder.on_trust_change`).
- The trust engine must never score enforcement or control events (see `EXCLUDED` in `backend/trust/adapters.py`).
- `RecoveryOrchestrator` holds an RLock around start/abort/tick. `RecoveryTimer` runs process_pending()+tick() on a daemon thread and is registered on app startup/shutdown (`app.state.recovery_timer`).
- Twin expected state is frozen (409) while a recovery is active. The dashboard PUT merges the existing expected fields and edits only fw/cfg.
- Operator auth: `_operator_guard(role)` in app.py sets `request.state.operator`. `require_operator` = viewer, `require_actor` = operator, `require_admin` = admin. Attribution goes through `audit()`/`attempt()` in security_routes.py (an operator_action event plus an evidence entry).
- TLS: `tls_options()` in backend/security/tls.py is used by backend/main.py. Files: backend/security/{operators,tls}.py, scripts/{operators,gen_dev_cert}.py.
- Recovery health checks call `DigitalTwin.compare_report(device_id, report)`, which judges a report on its own
  content. `compare()` is the accumulated view and carries a per-field `reported_at`.
- Dashboard: ES modules in dashboard/src (no build). All routes are listed in `src/lib/api.js` ROUTES (contract-tested). View models live in `src/lib/derive.js` (pure, node-tested).
  - Rendering uses the escaping `html` template plus the in-place `morph` renderer. `morph` keeps one attribute that templates never set, `data-revealed`, and leaves `data-morph-skip` subtrees alone (for example the camera mount).
  - Operator dialogs are in `src/actions.js` and `components/modal.js`.
  - Motion: `lib/reveal.js` and `components/ambient.js`. State moments key on `UI.flash` through `model.flashTo()`.
  - Camera: `components/camera.js` and `pages/vision.js`. `main.js` releases the camera on route change and on sign-out.
- The full-stack test fixture is in `tests/fullstack/conftest.py`.

**COMMAND TO VERIFY CURRENT STATE:**
```
python -m pytest -o addopts="" -q && python scripts/demo_full.py
```
