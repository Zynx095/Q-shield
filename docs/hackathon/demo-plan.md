# Demo plan (presenter runbook)

One command runs the whole story on a real gateway. The dashboard shows it live.

```
python scripts/demo_full.py --webcam --pace 2 --hold
```

## Before judging

1. **Camera.** `python -m ai.vision probe --config config/vision.json` must print a frame shape.
   - `camera.source` is usually `0` for the built-in camera and `1` for the first USB camera.
   - If the configured camera is missing, the webcam step says so and the rest of the demo runs.
   - Another config can be used with `--vision-config <file>`.
2. **Restricted zone.** By default the restricted zone is the **right half** of the camera frame. A person there is a
   *real* rule violation: trust drops during the webcam step and the real detection drives the incident. For the
   scripted story, keep the right half clear and point the camera at the protected area.
3. **Screen.** Open the dashboard link the demo prints and choose **Presentation mode**, or go to `#/live`. It fits
   one screen at 1280x720, 1366x768 and 1440x900. Escape returns to the full console.
4. **Second camera for the browser.** The browser preview on **Camera & vision** is local only. Most webcams serve
   one program at a time, so preview the *other* camera (for example the built-in one while the USB camera feeds the
   vision service). Preview needs `localhost` or HTTPS.

## The story, and what to point at

| Step | What happens (real gateway, over HTTP) | Point at |
|---|---|---|
| 1-2 | The simulated device joins with HMAC-SHA256 and sends telemetry. The digital twin matches the known-good state. | "Verified continuously": device, vision, twin |
| 3 | The real webcam feeds YOLO11n. Observations are ML-DSA-65 signed and sent inside an ML-KEM-768 session. | Camera & vision page: pipeline strip, "ML-KEM session" tags |
| 4 | A forged observation is rejected: its signature did not verify. | Feed: "Attack rejected" and the reason |
| 5 | A replayed observation is rejected. Forged traffic is bounded pressure only. | Score dips but stays above quarantine |
| 6 | The device reports its tamper switch open. The message is authentic; its content is abnormal. | SUSPICIOUS, tamper cap |
| 7 | A signed visual violation arrives inside the 60 s window, giving a confirmed incident. | Quarantine card: "Physical tamper (HMAC-SHA256) + signed camera evidence (ML-DSA-65)" |
| 8 | The gateway refuses the normal channel (403) and keeps the recovery channel open. A forged "all clear" gets 401. | Enforcement tiles: Blocked / Available |
| 9 | Evidence chain verified. | Evidence page: case file (what happened, why, proof, action, recovery) |
| 10-11 | The operator starts recovery. The device acknowledges remediation, passes three clean health checks (each judged on its own report) and reaches VERIFIED. Trust is then rebuilt: RECOVERED at 50, TRUSTED at 85. | Recovery stepper, "n / 3" health checks, trust ramp |
| 12 | Final state TRUSTED 85. The state path is printed and the chain is verified again. | "Normal channel restored" |

## Say it honestly

- Device telemetry comes from a software agent (labelled Simulated). The ESP32 has not been flashed.
- The device path is HMAC-SHA256, not post-quantum. The PQC protects the vision evidence and the evidence chain.
- The step 7 visual violation is a synthetic detection signed with the real vision key (labelled Simulated). The
  step 3 detections are real camera output.
- The trust ramp is shown in announced TIME-LAPSE (the gateway clock is advanced; no parameter is changed).
- The digital twin compares self-reported state: evidence, not attestation. Recovery is software remediation, not
  hardware repair.

## If something goes wrong

| Symptom | Fix |
|---|---|
| `webcam step NOT run: cannot open camera source N` | Wrong index or camera in use: run the probe, change `camera.source` or use `--vision-config`. Close the browser preview. |
| Trust drops during step 3 | A person or object is in the restricted zone: real evidence. Explain it, or clear the right half and rerun. |
| Dashboard asks for a token | Use the link the demo prints. The token is removed from the address bar after loading. |
| Port in use | `--port 8766` |
