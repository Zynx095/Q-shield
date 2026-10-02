# Q-SHIELD — Implementation Status

Persistent project memory. Read together with `docs/BUILD_CHECKPOINT.md`.
Last updated: 2026-10-02.

## CURRENT PHASE
Phases 0–17 implemented and tested. Phase 17 is the final software hardening (see **FINAL SOFTWARE HARDENING (Phase 17)**). Phase 14 is the command-center UI rework (see **COMMAND CENTER UI (Phase 14)**); Phase 15 is the premium visual pass and the Camera & vision page (see **PREMIUM VISUAL PASS + CAMERA (Phase 15)**); Phase 16 is the final hardening and demo-readiness pass (see **FINAL HARDENING + DEMO READINESS (Phase 16)**). Remaining work is listed under **WHAT IS LEFT**.

## TEST COUNT
**785 passed, 0 failed** (`python -m pytest -o addopts="" -q`, about 1.5 to 3 minutes depending on machine load). This includes the 40 dashboard JavaScript unit tests (`node --test dashboard/tests/*.test.mjs`: derive 23, reveal 4, ambient 4, camera 9), run through Node. Phase 16 ended at 695; the baseline before the continuous build was 544.

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

## OPERATOR CONTROLS (Phase 12)
- These use the existing operator API and its single shared operator bearer token. That token is authentication plus authorization. There is no RBAC and no per-operator identity yet (TD-17). The ingest token and device credentials are rejected with 401.
  - `POST /api/v1/devices/{id}/recovery/start` `{reason}`: goes through `RecoveryOrchestrator.start`. It needs QUARANTINED, not revoked, a twin expected state, and no recovery already active (otherwise 409). The body is `extra=forbid`, so no target state can be smuggled in (422). The operator cannot force any state.
  - `POST /api/v1/devices/{id}/recovery/abort` `{reason}`: the recovery is marked failed with `aborted: <reason>` and the device goes to QUARANTINED through the state machine. If no recovery is active, it returns 409.
  - `PUT /api/v1/devices/{id}/twin/expected`: the known-good fw_version/cfg_hash (and capabilities/sensor_ranges). It needs at least fw_version or cfg_hash (otherwise 422). It is **frozen while a recovery is active** (409), so the health-check yardstick cannot be moved mid-verification. Expected and observed state are stored and returned separately. Observed is self-reported evidence, not attestation.
  - Every action is recorded: `recovery_started` / `recovery_failed` / `twin_expected_updated` security events plus ML-DSA evidence-chain entries.
- Dashboard: the "Operator actions" card has a reason field, START/ABORT RECOVERY, and a known-good-state form. It shows loading, success, and refusal with the server's reason. Button enablement is only a hint, because the gateway re-checks everything. After every action the card re-renders from the API, so it reflects backend reality after a reload.
- Tests: `tests/fullstack/test_operator_controls.py` (28) and `tests/fullstack/test_dashboard_contract.py` (3, which check that the JS calls existing routes and replay the button request sequence).
- Not verified: no real browser click-through (no browser automation is installed here). The JS passes `node --check`, and its exact requests are replayed in the tests.
- Webcam: `python scripts/demo_full.py --webcam` was run with no camera attached. It prints `webcam step NOT run: cannot open camera source 0` and the rest of the demo completes (TRUSTED 85). The camera path itself is still unverified.

## OPERATOR IDENTITY + TLS (Phase 13)
**Implemented and tested:**
- **Named operators** (`backend/security/operators.py`, `operators` table): `operator_id`, `display_name`, `role`, `status` (active/revoked), optional `expires_at`, `created_by`, `revoked_by`. Tokens are `qso_` + 256-bit random. **Only SHA-256(token) is stored.** The token is returned once at creation and never appears in listings, events or the evidence chain. Revocation and expiry apply on the next request.
- **Roles:** `viewer` (read-only API), `operator` (+ start/abort recovery, set expected state, manual quarantine), `admin` (+ create/list/revoke operators). An authenticated caller without the required role gets 403, and a throttle-free `operator_forbidden` event is recorded.
- **Bootstrap:** the legacy shared token (`QSHIELD_OPERATOR_TOKEN` / `keys/operator.token`) authenticates as `bootstrap-admin` (role admin; flagged `bootstrap: true`; **not a person**) so the first operators can be created. Disable it with `ALLOW_SHARED_OPERATOR_TOKEN=false`. It is enabled by default for backward compatibility, and the gateway prints a startup note.
- **Auth boundaries unchanged:** the ingest token, device HMAC secrets and operator tokens never substitute for one another (tests both ways).
- **Attribution:** every operator action (START_RECOVERY, ABORT_RECOVERY, SET_EXPECTED_STATE, QUARANTINE, CREATE_OPERATOR, REVOKE_OPERATOR) writes one `operator_action` security event **and** one ML-DSA evidence-chain entry with `operator_id`, `operator_role`, `action`, `device_id`, `reason` and `result` (`success` or `refused` with the error). `operator_id` comes only from the authenticated identity. Request bodies are `extra=forbid`, so an `operator_id` in JSON is a 422. The recovery record stores `requested_by=<operator_id>`, and the abort reason carries `(by <operator_id>)`.
- **Operator management:** API `GET /api/v1/operators/me` (any operator), `GET|POST /api/v1/operators`, `POST /api/v1/operators/{id}/revoke` (admin), and the local CLI `python scripts/operators.py create|list|revoke`.
- **TLS** (`backend/security/tls.py`): `QSHIELD_TLS_CERT` + `QSHIELD_TLS_KEY` make uvicorn serve HTTPS. Half or invalid configuration (missing file, mismatched pair, garbage) fails at startup with a clear message. `QSHIELD_REQUIRE_TLS=true` refuses to start in HTTP mode. With neither set, the gateway stays in development HTTP mode and prints a CLEARTEXT warning. `python scripts/gen_dev_cert.py [--host <LAN IP>]` writes a **self-signed** ECDSA P-256 dev cert to `keys/tls/` (gitignored; key file owner-only, never overwritten). Tested against a real uvicorn HTTPS listener: a request pinned to the dev cert succeeds, the default client rejects the self-signed cert, and plain HTTP to the TLS port gets no API response.
- **Dashboard:** shows `Operator: <id> (<role>)` from `/operators/me`. Action buttons are disabled for `viewer`. 401 and 403 are shown as "token rejected/revoked/expired" and "role does not allow". The token is entered in a password field and kept in sessionStorage. It is never rendered.
- Tests: `tests/fullstack/test_operator_identity.py` (22), `tests/security/test_tls.py` (6). One Phase 12 assertion changed on purpose (the abort reason now ends with `(by bootstrap-admin)`), documented in the test.

**Security review (attempted bypasses):** the following all failed. Spoofing `operator_id`/`requested_by` in the body (422). Ingest token or device secret as operator (401). Revoked or expired token (401 on the next request). A viewer or operator calling admin/action routes (403, recorded). An operator creating an admin (403). Creating the reserved `bootstrap-admin` id or choosing your own token (refused). Tokens leaking through `/operators`, `/events` or the evidence chain (they don't).

**Prototype-only / production hardening required:**
- A bearer token *is* the identity: whoever holds it acts as that operator. There is no MFA, no session binding and no per-request replay protection (TLS is the protection on the wire). Over development HTTP, tokens are visible to anyone on the network.
- Roles are global, not per device. There is no lockout or rate limit on failed operator auth (only throttled logging).
- The shared bootstrap token is enabled by default. Production must create named admins and set `ALLOW_SHARED_OPERATOR_TOKEN=false` and `QSHIELD_REQUIRE_TLS=true`.
- The dev certificate is self-signed: no PKI, no rotation automation, no HTTP->HTTPS redirect, no mTLS. The ESP32 firmware has no TLS client (HMAC only).
- The `demo_full.py` script still uses the shared bootstrap token over local HTTP and prints a dashboard URL containing it (demo only).

## COMMAND CENTER UI (Phase 14)
**Implemented and tested.** `dashboard/` was rebuilt as a light security command center. It uses native ES modules and has no build step or dependencies; the fonts are vendored so it works on an offline LAN. See `dashboard/README.md`.
- **Screens:** Overview (posture, trust lattice, story rail, enforcement channels, trust over time, live timeline, active incident, evidence chain); Devices and the device security profile; Incidents; Recovery (8-step stepper, deadlines, remediation, health checks, history); Evidence ledger; Digital twin; Cryptography (which path is post-quantum and which is not, plus live rejection counts); Settings (operator, connection, roster); Presentation mode (`#/live`); Sign-in.
- **Real data only:** every value comes from the operator API. `Math.random`, seeded data, `localStorage` and unescaped markup are forbidden by `tests/fullstack/test_dashboard_contract.py`. Simulated device data and synthetic detections are labelled on screen.
- **Operator actions:** start recovery, abort recovery and set the known-good state run in confirmation dialogs that require a reason. Each dialog shows the gateway's real response or its refusal verbatim. Availability hints come from role and state; the gateway stays authoritative.
- **Minimal backend addition:** `GET /api/v1/system` (operator, read-only, no key material). It returns trust thresholds and weights, recovery limits, the PQC and evidence configuration, the transport, and the gateway clock, so the UI hard-codes none of them and can show the demo's TIME-LAPSE offset. Tests: `tests/fullstack/test_system_info.py`.
- **Demo fix:** `demo_full.py --hold` crashed with `WinError 10053` when uvicorn closed an idle keep-alive connection exactly as the 5 s report fired. It now reports every 4 s and tolerates a transport error.
- **Tests:** `dashboard/tests/derive.test.mjs` has 13 node tests on two real captured gateway runs, one of which includes an operator abort and a second recovery. It runs inside pytest via `tests/fullstack/test_dashboard_unit.py` and is skipped if Node.js is absent. The contract tests check every route in `ROUTES` against the real app, check the action methods, and check that the files are served with a JS MIME type.
- **Browser QA (Edge, headless Playwright, outside the repo):** the full story was driven on a live gateway through the UI. Steps checked: bad-token sign-in rejected; the token is removed from the URL; TRUSTED → SUSPICIOUS → QUARANTINED rendered live; a viewer's controls are disabled; operator `alice` started recovery through the dialog (validation, then success); aborted (the device returned to QUARANTINED); started again; the twin edit is locked during recovery; VERIFIED → RECOVERED → TRUSTED; the evidence ledger shows `alice started recovery` and `alice aborted recovery`; a known-good edit produced a visible MISMATCH; with the gateway stopped, the offline banner appeared. Layout was checked at 1440/1280/1024/768/390 px. There was no horizontal overflow from 768 px up; the 390 px overflow found during QA was fixed. Keyboard checks: skip link, nav order, dialog focus and Escape with focus return.
- **Not verified:** the webcam path in the UI (no camera here); screen-reader output (only structure and ARIA were checked).

## PREMIUM VISUAL PASS + CAMERA (Phase 15)
**Implemented and tested, frontend only.** Nothing changed in the backend, API, trust, enforcement, recovery or evidence code, and no dependency was added. The work is a series of small commits starting at `67066da`; see `git log`.
- **Interaction system:**
  - motion and glow tokens
  - hover lift with a glow tinted by the button's meaning; press settle
  - unclipped focus rings
  - hover only on clickable ledger entries and device rows
  - animated nav indicator; success check-mark draw
  - hover applies to pointer devices only, and all of it is off under reduced motion
- **Scroll reveal:**
  - `dashboard/src/lib/reveal.js` uses an IntersectionObserver: each section reveals once, the stagger is capped at 4, and a 1.2 s safety net shows anything left. Sections are hidden only while `html.reveal-ready` is set.
  - `lib/morph.js` keeps the `data-revealed` marker, so refreshes never replay a reveal.
  - Marked: overview, devices/device, incidents, recovery, the evidence header, twin, crypto.
  - Never marked: the topbar, sidebar, dialogs, ledger blocks, timeline items, presentation mode.
- **Ambient background** (`components/ambient.js` + `styles/ambient.css`):
  - algorithm names plus 8-digit decorative hex from a fixed seed (mulberry32; no random source)
  - at most 5% opacity, transform-only drift
  - tint and speed follow the posture; speed changes use Web Animations `updatePlaybackRate`, so rows never jump
  - static under reduced motion; masked behind page headings; the topbar is near-solid while it runs
  - Settings switch (sessionStorage)
  - The module imports nothing (checked by node and contract tests).
- **State moments**, driven by `UI.flash` on real transitions only, with no layout change:
  - SUSPICIOUS: amber sweep
  - QUARANTINED: the normal channel's X draws in and the recovery channel opens
  - RECOVERING / VERIFIED: the active recovery step pulses
  - RECOVERED: the check mark draws in, with an emerald wash
- **Camera & vision page (`#/vision`):**
  - `components/camera.js` holds the controller and the view.
  - The preview is **local only**: it is not analysed, signed, recorded or sent, and nothing is drawn over the video.
  - It never starts on its own. Cameras can be listed and switched (the old stream is stopped first).
  - Camera permission is read before the browser asks, and there is a secure-context check.
  - The camera is released on Stop, route change, sign-out, page hide, and while the tab is hidden.
  - Errors are explained: denied, no camera, in use (possibly by the vision service), insecure page, unsupported browser.
  - Beside the preview: the vision service's **signed** observations from `/api/v1/observations` with the gateway's ML-DSA-65 label, the signers from `/api/v1/system`, and the pipeline. Synthetic detections are tagged Simulated.
- **Found and fixed in browser QA:** at phone width the topbar's right-hand chips widened every page to 511 px. This was pre-existing. They now wrap to a second row.
- **Tests:**
  - `dashboard/tests/{reveal,ambient,camera}.test.mjs`, plus an observation test in `derive.test.mjs`
  - contract tests: ambient has no imports and no network calls; camera has no network, recording or frame-capture API and requests `audio: false`; the `#/vision` route, nav entry, mount and labels exist, and the camera is released
- **Browser QA** (headless Edge, with Playwright kept outside the repo):
  - hover, press, focus, nav and card states measured
  - reveal on every marked page: entrance, scroll, no replay on refresh, deep link
  - ambient: built once, at most 5%, drifts, ignores the pointer; posture checked through full live attack-to-recovery cycles
  - every state moment captured on the overview and in presentation mode, with normal and reduced motion
  - Camera & vision with Edge's fake camera: no auto-start; 1280×720 live; the `<video>` node and stream stay the same across refreshes; Stop, leaving the page and signing out each end every track; a refused permission is explained
  - no horizontal scroll on ten pages at 390, 700 and 1024 px
  - presentation-mode 7-viewport regression: 83 of 83 checks passed
  - 4× CPU-throttled overview: same frame cadence and refresh long tasks as the dashboard before this pass. Renders of about 100 ms at 4× throttle existed before and after; the ambient layer adds none.
- **Not verified:**
  - the preview with a physical webcam (only Edge's fake camera was available here)
  - camera contention with the running vision service on real hardware
  - screen-reader output

## FINAL HARDENING + DEMO READINESS (Phase 16)

**Bugs found and fixed, each with a regression test that failed before the fix:**

| Area | Bug | Fix | Test |
|---|---|---|---|
| Recovery | Health checks compared the twin's *accumulated* observed state. A device that stopped reporting `cfg_hash` after the attack passed every check on the value it had reported before quarantine, and reports consumed in one tick all borrowed the newest state. | `DigitalTwin.compare_report()` judges each report on its own content. Each health-check record keeps per-field verdicts. | `tests/fullstack/test_recovery.py::test_health_checks_judge_each_report_not_a_stale_twin_field`, `::test_each_health_check_records_what_that_report_said`, `tests/twin/test_twin.py::test_compare_report_judges_only_what_the_report_says` |
| PQC session | The handshake nonce check and record sat in two critical sections around signature verification and decapsulation, so a concurrent replay of one init got two sessions. | The nonce is reserved atomically and released on rejection. | `tests/security/test_pqc_session.py::test_concurrent_replay_of_one_handshake_yields_one_session`, `::test_failed_handshake_does_not_keep_its_nonce` |
| Vision | Webcam auto-exposure frames read as an obstructed lens, and the signed "obstructed" report lowered trust before the attack. | `camera.warm_up()` with `camera.warmup_frames` (default 15) for live cameras. | `tests/ai/test_sinks_and_runner.py::test_camera_warm_up_keeps_auto_exposure_frames_out_of_health` |
| Dashboard | The vision list class `.obs` turned the twin table's `td.obs` cells into flex boxes, misaligning the table. | Renamed to `.obs-list`. | Browser QA (cell geometry) |
| Dashboard | A route change waited for the next animation frame: up to about 2 s in headless Edge. | `hashchange` paints immediately. | Browser QA (route change measured at 20–50 ms) |
| Demo | During the webcam step the simulated device went silent, so it was marked stale (cap 79). | The device keeps reporting during the step. | Live `demo_full --webcam` run |

**Other changes:**
- **Evidence chain.** Unchanged signatures are not re-verified: a cache keyed by (event_hash, SHA-256(signature),
  key_id). Hashes and links are still recomputed on every call, and every tampering case is still detected. A
  repeat verification of 500 entries dropped from 172 ms to 15 ms (`tests/evidence/test_chain.py`).
- **Observation transport.** Each stored observation records `secure` (inside an ML-KEM-768 session), `signed`
  (direct) or `token`. The API returns it, and the Camera & vision pipeline strip and the Cryptography counts use it
  instead of always claiming a session. The three ingest paths are tested.
- **Digital twin.** Each field records when it was last reported. The twin view shows the enclosure tamper switch and
  marks values missing from the latest report.
- **Dashboard.**
  - The forensic case file on the evidence page (`derive.forensicCase`, node-tested on both captured runs).
  - The "Verified continuously" strip in presentation mode's trusted state (`derive.liveProof`).
  - Camera & vision status facts (`derive.visionStatus`).
  - One phrasing for trust rebuilt by clean evidence.
- **Demo** (`scripts/demo_full.py`).
  - The device keeps reporting during the webcam step.
  - Step 3 counts clear and rule-matching observations and explains a real restricted-zone detection.
  - With `--pace`, recovery stages are held on the wall clock so the dashboard shows each one (TIME-LAPSE
    unchanged).
  - A missing camera prints how to pick the index.
- **Documentation.**
  - The README is rewritten to match the system, with a real-versus-simulated table.
  - The hackathon novelty and problem statements no longer claim "PQC-backed device identity", "AI-driven" trust or
    "machine learning" sensor checks.
  - The architecture diagram is redrawn as implemented.
  - The demo runbook (`docs/hackathon/demo-plan.md`) is written.

**Verified live:**
- `python scripts/demo_full.py --webcam --pace 2 --hold` with the configured camera (index 1) **absent**: the webcam
  step reported it and the rest of the demo completed (TRUSTED 85). Presentation mode showed all seven states.
- The same command with a scratch config pointing at the built-in camera (index 0): 40 real frames, YOLO11n, and
  signed observations accepted inside an ML-KEM-768 session.
  - The camera saw a person in the restricted zone, which is real evidence, and the demo now says so.
  - There was no false "obstructed" report.
  - Every state from TRUSTED through RECOVERED to TRUSTED was shown in presentation mode at 1366x768 and 1280x720.

**Browser QA** (headless Edge, Playwright outside the repo):
- 11 routes at 1920, 1440, 1366, 1280, 768 and 390 px with no horizontal page scroll.
- Presentation-mode 7-viewport regression: 83 of 83 checks.
- Keyboard: skip link, 39 tab stops all with a visible focus ring, dialog focus and Escape, Escape out of
  presentation mode.
- Camera lifecycle with Edge's fake camera: no auto-start, start, node and stream stable across refreshes, stop,
  leaving the page, sign-out, refused permission.
- Reduced motion on all routes.
- Gateway API: every dashboard endpoint under 15 ms on the demo gateway.

## FINAL SOFTWARE HARDENING (Phase 17)

No physical ESP32 was available. The USB webcam (index 1, "USB Video Device") and the built-in camera were.

| Area | Change | Tests |
|---|---|---|
| Rejected traffic | An unauthenticated flood used to add one `security_events` row per message. `backend/security/rejections.py` now does three things. It keeps 3 samples per sender per 10 s window, with at most 120 per window. It coalesces the rest into a representative row with `aggregated`, `first_ts` and `last_ts`; that row is written before the device's next authenticated message. It prunes routine rows past 20 000, but only rows the trust engine has consumed. High-value events are never sampled. The dashboard shows `×count`. | `tests/fullstack/test_rejection_flood.py` (7). Trust state is identical with and without sampling. 5 of the 7 fail with sampling disabled. |
| Vision session churn | The gateway answers 401 `session_expired` only for an unknown or expired session. The client then re-handshakes once, and only then. Any other refusal drops the observation and keeps the session. Backoff runs from 1 s to 60 s, with a budget of 20 handshakes per hour. `status()` reports diagnostics, printed by the vision CLI and the demo. | `tests/integration/test_vision_session_churn.py` (7, all fail against the previous client); `test_pqc_session.py` |
| Camera as security boundary | New camera states: `frozen`, `view_changed` (`viewpoint_shift` with the measured shift, `scene_replaced`, `view_altered`) and `degraded` (`low_light`, `blurred`). Obstruction now distinguishes dark, flat and overexposed. A state is reported after 2 s and 5 frames of agreement. Detected people are masked out of the viewpoint check. Image-space proximity heuristics: `subject_too_close` and `rapid_approach`. All thresholds are config keys with defaults, so `config/vision.json` is unchanged. | `tests/ai/test_camera_security.py` (23) |
| Trust integration | New kinds `camera_frozen`, `camera_view_changed` (both HIGH), `camera_degraded` (MEDIUM) and `subject_proximity` (LOW). Signed camera interference counts as VISUAL modality evidence. With tamper it gives `confirmed_incident`; with a sensor excursion, `correlated_incident`. Alone it is a penalty only. Weak evidence never confirms. The spec is updated first (trust-engine.md sections 3, 4.4, 6.3, 7.1, 9, 12, 13, 15, 16). | `tests/trust/test_camera_boundary.py` (35); `tests/fullstack/test_camera_boundary_e2e.py` (3, including the real pipeline, the ML-DSA sink, the gateway and quarantine) |
| Hardware-ready interfaces | `device_agent/sensors.py` (`SimulatedSensors`, `ReplaySensors`); `rssi_dbm` network telemetry; device protocol test vectors (7 cases, byte-exact, gateway-accepted); `docs/hardware/device-protocol.md`, `hardware-architecture.md`, `wiring-plan.md`; network-camera labelling for an ESP32-CAM stream. Firmware: the JSON escaping syntax error is fixed; telemetry is compiled only once the wiring is declared; a 403 backs off. Still not compiled. | `tests/security/test_device_vectors.py` (5), `tests/integration/test_device_sensors.py` (7), `tests/ai/test_sinks_and_runner.py` |

**Bugs found and fixed, each with a regression test that failed before the fix:**
- Unbounded event growth from unauthenticated floods.
- Session churn: every refused observation opened a new ML-KEM session.
- Proximity flapping, found on the live USB camera: a seated person missed in some frames was reported as "too
  close" 25 times in 90 s. It is now once.
- The demo counted a proximity heuristic as a restricted-zone rule match.
- The firmware's `jsonEscape` had a C++ syntax error.

**Verified live (USB camera, index 1, YOLO11n on CPU):**
- `python -m ai.vision probe --config config/vision.json` prints a 480x640 frame.
- Two 90 s pipeline runs with the full health and proximity checks:
  - warm-up of 15 frames in 1.6 s;
  - about 5 frames/s, about 126 ms per frame at p50 (inference included);
  - no failed reads and no camera-health events while a person sat and moved in view;
  - the reference view learned, with the person masked out;
  - person detections at confidence 0.40 to 0.83;
  - restricted-zone rule matches every 5 s;
  - one `subject_too_close`, at a box of 36 to 60% of the frame (after the fix).
- Built-in camera, static scene, 75 frames: no events. The smallest frame-to-frame difference was 0.59 gray levels,
  against the frozen threshold of 0.05.
- **Not validated physically:** covering, turning, freezing or unplugging the camera. Nobody manipulated the camera
  during these runs; those states are tested on synthetic frames only.
- `python scripts/demo_full.py --webcam --pace 2 --hold` on the USB camera ran end to end:
  - presentation mode at 1366x768 and 1280x720 showed TRUSTED → SUSPICIOUS → QUARANTINED → RECOVERING → VERIFIED
    → RECOVERED → TRUSTED, with every check passed;
  - a dashboard-against-API comparison passed 7 of 7: score and state on the overview and device pages, the
    proximity explanation and rule-match count on Camera & vision, the chain length on Evidence, and no page
    errors;
  - the final state was TRUSTED 85, with the chain VERIFIED at 26 entries.

## HOW TO RUN
```
python -m pytest -o addopts="" -q                   # full suite
python scripts/demo_full.py                         # full story on a real gateway (scratch state)
python scripts/demo_full.py --pace 2 --hold         # presentation pacing; keeps the gateway up for the dashboard
python scripts/demo_full.py --webcam                # adds the real webcam + YOLO11n step (needs a camera; USER TO RUN)
python scripts/gen_dev_cert.py                      # self-signed dev cert -> keys/tls/
QSHIELD_TLS_CERT=keys/tls/gateway.crt QSHIELD_TLS_KEY=keys/tls/gateway.key QSHIELD_REQUIRE_TLS=true python -m backend.main
python scripts/operators.py create alice "Alice" operator   # prints alice's token once
# dashboard: https://localhost:8000/dashboard/  -> paste the operator token -> header shows 'Operator: alice (operator)'
```
The demo prints the dashboard URL with the operator token.

## KNOWN LIMITATIONS (honest)
- The browser camera preview is a local convenience. It is not evidence, and the signed observations never come from it. It needs HTTPS or localhost, and on most webcams it cannot share a camera with the vision service.
- All device data is SIMULATED (software agent). The ESP32 firmware has never been compiled or flashed, and its path is HMAC-SHA256 only (not PQC).
- No physical tamper test was ever performed.
- The webcam step was run live on the USB camera in Phase 17 (start-up, warm-up, normal scene, person detection, proximity). Covering, turning, freezing and unplugging the camera were **not** staged physically; those camera states are tested on synthetic frames only.
- Camera-health and proximity thresholds are unvalidated defaults. Proximity is an image-space heuristic: no distance is measured. The reference view is learned when the vision service starts.
- Twin observed state is self-reported: it is evidence, not attestation.
- The trust ramp takes about 40 minutes of clean evidence at the documented parameters. The demo uses a clearly labelled TIME-LAPSE clock and does not change parameters.
- Trust parameters are design choices and have not been calibrated against data (trust-engine.md §16).
- The custom ML-KEM session protocol has had no external review. TLS is optional (self-signed dev cert); in the default development HTTP mode tokens travel in cleartext.
- The evidence chain has no external anchoring. Anyone holding both the DB and the evidence key can rewrite history.
- Recovery deadlines are evaluated by a background `RecoveryTimer` (every `RECOVERY_TICK_S`, default 5 s; 0 disables) as well as on each request.
- The service is single-process and single-gateway (SQLite).

## WHAT IS LEFT
| Priority | Item | Notes |
|---|---|---|
| Done | Run `demo_full.py --webcam` live with a camera attached | Phase 17: the configured USB camera (index 1), full story to TRUSTED 85 |
| High | Stage physical camera tests (cover, turn, unplug, approach) and set the camera thresholds from them | Thresholds in `HealthConfig` / `ProximityConfig` are unvalidated |
| High | Real ESP32: compile, flash, wire the tamper switch and sensors, replace the software agent | Biggest credibility gap |
| Done | Background timer for recovery deadlines | `RecoveryTimer` in `backend/recovery/orchestrator.py`, started/stopped with the gateway; tests in `tests/fullstack/test_recovery_timer.py` |
| Done | Dashboard operator actions | See "OPERATOR CONTROLS" below |
| Done (prototype) | TLS for the gateway; per-operator tokens | Phase 13; see above |
| Done | Final presentation | Phase 17: `ppt/final/Q-SHIELD_QuantAMaze3.0_Final.pptx` + `.pdf` on the official Quant-A-Maze 3.O template (plan: `ppt/final/SLIDE_PLAN.md`). Team fields still `[ to fill ]` |
| Medium | Update the audit PDF | It still describes Phases 5–10 as planned |
| Low | External anchoring of the evidence head; key rotation | TD-09, TD-15 |
| Research | Calibrate trust parameters; measure vision accuracy; external review of the session protocol | trust-engine.md §16 |
