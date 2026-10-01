# Q-SHIELD Command Center (dashboard)

A light, operator-facing security console served by the gateway at `/dashboard/`. It reads and acts only
through the gateway operator API. There is no seeded, demo or invented data anywhere in it: if the gateway does not
report a value, the screen says so.

## Run it

```
python scripts/demo_full.py --pace 2 --hold      # full attack -> quarantine -> recovery story, gateway kept up
# open the printed  http://127.0.0.1:8765/dashboard/#token=...   (the token is removed from the address bar on load)

python -m backend.main                           # your own gateway; sign in with an operator token
python scripts/operators.py create alice "Alice" operator    # a named operator token (shown once)
```

For HTTPS see `docs/IMPLEMENTATION_STATUS.md` (QSHIELD_TLS_CERT / QSHIELD_TLS_KEY). Presentation mode for a
projector: **Presentation mode** in the sidebar, or `#/live`. Press Escape to leave it.

## Screens

| Route | What it answers |
|---|---|
| `#/overview` | Is the system secure right now? Posture, the focused device's trust lattice (six factors converging on the score), its path through TRUSTED → … → TRUSTED, what the gateway enforces (normal channel / recovery channel), trust over time, the live timeline, the active incident and the evidence chain. |
| `#/devices`, `#/devices/<id>` | Every device; a full security profile per device (identity, factors, enforcement, recovery, digital twin, incidents, timeline, evidence). |
| `#/incidents` | Correlated incidents: the evidence (with its authentication and provenance), trust before/after, the enforcement and the resolution. |
| `#/recovery` | The eight-step recovery path, deadlines, remediation command, health checks, and the operator controls. |
| `#/evidence`, `#/evidence/<seq>` | The forensic ledger: each entry's SHA-256 hash, the previous hash it commits to, its ML-DSA signature; gateway verification. |
| `#/twin` | Known-good (expected) state against the device's self-reported state, field by field. |
| `#/crypto` | Which path is protected by what: ML-KEM-768 / ML-DSA-65 for vision, HMAC-SHA256 for the device path, the evidence chain, and the operator transport. Live rejection counts. |
| `#/vision` | Camera & vision: a **local** live preview from this browser's camera beside the **signed** observations the Python vision service sent the gateway. See "Camera preview" below. |
| `#/settings` | Signed-in operator, gateway connection, display (ambient background on/off), operator roster (admins). |
| `#/live` | Presentation mode: the story at three metres. |

## Operator actions

Start recovery, abort recovery and set the known-good state open a confirmation dialog that requires a reason
(recorded in the evidence chain with the authenticated operator identity) and shows the gateway's actual response,
or its refusal verbatim. Button availability is a hint (role, state, active recovery); the gateway re-checks every
precondition. Viewers see the controls disabled with the reason.

## Camera preview (Camera & vision)

- **Local only.** The preview stream goes from the browser's camera to a `<video>` on the page and nowhere else: it is
  not analysed, recorded, signed or sent. Nothing is drawn over it (no boxes, detections, confidence or frame rate).
  The signed observations beside it come from the separate Python vision service (`python -m ai.vision`, or
  `demo_full.py --webcam`) and are shown exactly as the gateway stored them, with its ML-DSA-65 verdict label;
  synthetic attack-simulation detections are tagged **Simulated**.
- **Nothing starts on its own.** The camera opens only on **Start preview**; it is released on Stop, when you leave the
  page, sign out or close the tab, and while the tab is hidden (it resumes when you return).
- **Choosing a camera.** Integrated, USB and virtual cameras are listed (names appear after permission is granted);
  switching closes the old stream before opening the new one. The choice is remembered for the tab (sessionStorage).
- **One camera, one program.** Most webcams (on Windows especially) serve one program at a time. The vision service
  opens the camera set by `camera.source` in `config/vision.json`; preview the *other* camera, for example the
  integrated one while the USB camera feeds the vision service. A busy camera is reported as "in use by another
  program, possibly the Q-SHIELD vision service".
- **HTTPS or localhost.** Browsers expose cameras only to secure pages. Over plain HTTP from a LAN address the page
  explains this; use `http://localhost` / `http://127.0.0.1` on the gateway machine, or run the gateway with
  `QSHIELD_TLS_CERT` / `QSHIELD_TLS_KEY`.

## Motion and ambience

- **Interaction:** actionable buttons lift 1 px with a glow tinted by what they do (cobalt, navy, crimson) and settle
  to `scale(0.98)` when pressed; clickable ledger entries and device rows react to the pointer, plain panels do not.
  The 2 px cobalt focus ring is the only focus signal. Hover effects apply to pointer devices only.
- **Section reveals** (`src/lib/reveal.js`): page sections marked `data-reveal` fade and rise once as they enter the
  viewport (staggered, at most four deep). They are hidden only while the controller runs; a 1.2 s safety net shows
  anything on screen; the morph renderer keeps the `data-revealed` marker so the 2-second refresh never replays them.
- **Ambient background** (`src/components/ambient.js`, `styles/ambient.css`): faint (≤ 5 %) monospace rows of the
  algorithm names in use plus fixed-seed decorative hex, drifting slowly behind the solid panels and tinted by the
  fleet posture (calm when trusted, amber under suspicion, nearly still and crimson while a threat is contained,
  cobalt during recovery). It imports nothing, so no live value, token or key can reach it. Off switch in Settings.
- **State moments**, only on real transitions: an amber sweep on suspicion; on quarantine the normal channel seals as
  its X draws in and the recovery channel opens; the active recovery step pulses as the device advances; on
  restored access the check draws in with an emerald wash in presentation mode.
- **Reduced motion:** reveals, lifts, sweeps and drift are off; content and final states appear immediately.

## Engineering

- Native ES modules, no build step, no dependencies. Fonts (Archivo, IBM Plex Mono, SIL OFL) are vendored in
  `assets/fonts`, so the console works on an offline LAN.
- `src/lib/api.js` lists every route used (`ROUTES`); `tests/fullstack/test_dashboard_contract.py` checks each one
  against the real gateway app.
- `src/store.js` polls every 2 s (evidence incrementally with `after_seq`; chain verification when new entries arrive).
  `GET /api/v1/system` supplies thresholds, recovery limits, PQC/evidence configuration and the gateway clock, so the
  UI hard-codes none of them and can show the demo's TIME-LAPSE offset honestly.
- `src/lib/derive.js` turns API payloads into view models (timeline, incidents, recovery steps, factors, vision
  observations). Pure, unit-tested with real captured responses. All dashboard tests:
  `node --test dashboard/tests/*.test.mjs` (derive, reveal, ambient, camera; also run by pytest).
- Rendering: the `html` tagged template escapes every interpolated value (security events carry attacker-chosen strings), and
  `render()` morphs the DOM in place, so focus, scroll and CSS transitions survive the 2-second refresh.
- Accessibility: semantic landmarks, skip link, visible focus, keyboard-operable dialog with focus return, every
  status as icon + word (never colour alone), `prefers-reduced-motion` respected, ARIA on charts and meters.

## Honest limits

- Device telemetry in the demo comes from the software agent; screens label it **Simulated**. Visual violations in
  the demo after the webcam step are synthetic detections signed with the real vision key, and are labelled so.
- A digital-twin MATCH is self-reported evidence, not attestation; the screens say so.
- The browser re-checks only evidence-chain link continuity; signatures are verified by the gateway.
- Single shared bootstrap token sessions are flagged; named operators are recommended.
