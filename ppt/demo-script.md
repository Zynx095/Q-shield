# Q-SHIELD: live demonstration script (current milestone)

Everything here uses commands that exist in the repository and were run in this form during Phases 1-3. **There is no trust score, quarantine or recovery demo, because those are not implemented. Do not improvise one.** Run every step once beforehand: the person-in-restricted-zone case in particular has only been tested with a fake detector, never live.

Run from the repository root, Windows PowerShell or Git Bash. Use a scratch database so the demo does not touch real data; keys go to the default `keys/` directory, which is already gitignored (as are `*.db` files):

```
$env:DATABASE_URL="sqlite:///demo.db"      (Git Bash: export DATABASE_URL=sqlite:///demo.db)
$env:QSHIELD_HOST="127.0.0.1"              (Git Bash: export QSHIELD_HOST=127.0.0.1)
```
To reset the demo, delete `demo.db` and the `keys/` folder (only if you have no other keys you need).

## 0. Preflight (2 minutes before)
- `python -m pytest` -> expect `347 passed` (about 20 s). Keep the terminal to show if asked.
- Webcam works: `python -m ai.vision probe` -> prints frame shape 480x640 and brightness/texture values.
- `ai/models/yolo11n.pt` exists (5,613,764 bytes).
- Port 8000 free. Two terminals open.
- Fallback assets ready: `docs/results/live-run-phase3.json`, `ppt/diagrams/03_signed_observation_flow.png`.

## 1. Provision (terminal 1, about 20 s)
```
python scripts/enroll_device.py DEVICE-001
python scripts/pqc_provision.py init-gateway
python scripts/pqc_provision.py enroll-signer vision-1 --device DEVICE-001
```
Expect: `enrolled DEVICE-001`, `created gateway ML-KEM-768 key gateway-kem-1` with a fingerprint, `enrolled signer vision-1 (ML-DSA-65) for usb_webcam on ['DEVICE-001']`. Say: private keys are sealed on disk; the vision service gets only its own key-encryption key. No secrets are printed.

## 2. Start the gateway (terminal 1)
```
python -m backend.main
```
Expect Uvicorn on `127.0.0.1:8000`. (It refuses to start with PQC enabled if the gateway key is missing, by design.)

## 3. ESP32-class device path, HMAC (terminal 2, optional, 30 s)
```
python -m device_agent --device-id DEVICE-001 --count 3 --interval 1   # reads keys/devices/DEVICE-001.secret
curl -H "Authorization: Bearer <contents of keys/operator.token>" http://127.0.0.1:8000/api/v1/devices
```
Expect `register: 200`, `heartbeat: 200 telemetry: 200`, and DEVICE-001 `ONLINE`, `hw: "software-agent"`. Say clearly: this is a **software device agent using HMAC-SHA256, not post-quantum, not the physical ESP32** (its firmware is an untested skeleton). The same API without the bearer token returns 401.

## 4. Real vision + PQC path (terminal 2, the centrepiece, 60 s)
Default config detects only `person`, with the right half of the frame as `restricted_zone`.
```
python -m ai.vision run --gateway http://127.0.0.1:8000 --signer-id vision-1 --secure --max-frames 75
```
- If a presenter steps into the **right half** of the frame: expect `anomaly: true`, `anomaly_reason: restricted_class_in_restricted_zone` (rehearse first; not yet exercised live).
- If nobody is in view, no observations appear. Use the widened config instead (this is what produced the recorded evidence):
  copy `config/vision.json`, set `"classes_of_interest"` to e.g. `["person","chair","laptop","cup","bottle","keyboard"]` and `"conf_threshold"` to 0.3, then add `--config <that file>`.
- Say: each observation is signed with the vision service's ML-DSA-65 key and sent inside an ML-KEM-768 session (AES-256-GCM). The identity is the software service, not the webcam.

Show the result:
```
curl -H "Authorization: Bearer <operator token>" http://127.0.0.1:8000/api/v1/observations
```
Expect each record with `"auth": "ML-DSA-65:vision-1"`, object, confidence, zone, `anomaly`, model `yolo11n`.

## 5. Attack: modify and replay (terminal 2, 20 s)
```
python scripts/demo_forgery.py --db demo.db
```
Expect: `1. payload altered ... -> 401`; `2. exact replay ... -> 409` if run within 300 s of the observation, otherwise `401` (stale timestamp). Both are rejections. Then:
```
curl -H "Authorization: Bearer <operator token>" http://127.0.0.1:8000/api/v1/events
```
Expect `pqc_invalid_signature` (high) and `pqc_observation_replay` (medium; only if the replay came inside the window). Say: nothing was forged cryptographically; the altered copy carries the original signature, which no longer verifies. The script refuses any non-local target.

## 6. Evidence and rigor (30 s)
```
python scripts/export_live_evidence.py --db demo.db --out docs/results/live-run-demo.json
python scripts/bench_pqc.py --iterations 100 --rounds 3
```
The export re-verifies every stored signature offline and shows altered copies are rejected. (Full benchmark numbers on the slides come from the 300 x 5 run in `docs/results/pqc-benchmark.json`; a shorter run gives similar but not identical numbers, so do not present it as the recorded result.)

## 7. Close
Return to slide 13/15: authenticity is not trust; the trust engine specification is the next step.

## If something fails
| Failure | Do |
|---|---|
| Webcam busy/absent | Skip step 4; show `docs/results/live-run-phase3.json` and figure 03; run `python -m pytest tests/security/test_signed_observations.py tests/security/test_pqc_session.py -q` (no camera needed) |
| Model weights missing | `python -c "from ultralytics import YOLO; YOLO('ai/models/yolo11n.pt')"` (needs internet once) |
| Gateway refuses to start (PQC keys) | rerun step 1; or `PQC_ENABLED=false` (then signed endpoints return 503; say so) |
| 401 on operator curl | wrong/missing token: read `keys/operator.token` |
| Replay shows 401 not 409 | expected after 300 s; explain the freshness window |
| Nothing detected | widen classes (step 4) and say why |

## Do not
- Do not show or describe a trust score, states, quarantine, recovery, evidence chain or dashboard as working.
- Do not call the software device agent "the ESP32" or the HMAC path "post-quantum".
- Do not present FPS numbers as accuracy.
- Do not run forgery against anything but the local demo gateway.
