# AI / Vision observation pipeline (Phase 2)

Status: **implemented and tested** with the laptop USB webcam. Output is **observations, not trust decisions.**

```
USB webcam -> FrameSource -> YoloDetector -> zone classification -> VisionPipeline -> Observation
                                                                                        |
                                              JsonlSink (local file)  /  HttpSink -> POST /api/v1/observations
                                                                                        |
                                                                   (Phase 4 trust engine will fuse these later)
```

`ai/vision` imports only the pure schema `backend/protocol/observation.py`. It has no dependency on the API, the database, or trust logic (enforced by a test). YOLO reports what it sees; **it does not decide whether a device is compromised.** The `anomaly` flag means only "matched a configured rule".

## Model and licensing (verified 2026-09-24)

| Item | Value |
|---|---|
| Model | YOLO11n (`yolo11n.pt`), COCO 80-class detector, task `detect` |
| Source | https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11n.pt (downloaded by the `ultralytics` package) |
| Size / SHA-256 | 5,613,764 bytes / `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1` |
| Checkpoint metadata | trained/exported with ultralytics 8.2.100; checkpoint field `license`: **"AGPL-3.0 License (https://ultralytics.com/license)"** |
| Inference library | `ultralytics` 8.4.50; its package metadata declares **AGPL-3.0** (`GNU Affero General Public License v3 or later`) |
| Runtime | PyTorch 2.13.0+cpu (CPU only in this setup) |

**AGPL-3.0 applies. It is not hidden.** Q-SHIELD's own code is MIT-licensed (repo `LICENSE`). We do not vendor or redistribute Ultralytics code or weights; the weights are gitignored and each user downloads them. Nevertheless, distributing a combined work, or offering it to users over a network, may trigger AGPL obligations (corresponding source, same-license terms), and Ultralytics sells a separate commercial license. This has **not** had legal review. For a hackathon prototype it is acceptable and disclosed; before any wider distribution either comply with AGPL / obtain the commercial license, or replace the detector (the `Detector` interface in `ai/vision/detector.py` is the only place that touches the model). COCO dataset licensing of the training data was not investigated here.

The lightweight `n` (nano) model was chosen because it is sufficient for person/object presence on a laptop CPU; nothing larger was downloaded.

Getting the weights (once, ~5.4 MB; needs internet):
```
python -c "from ultralytics import YOLO; YOLO('ai/models/yolo11n.pt')"
```

## Configuration (`config/vision.json`)

Camera: `source` (device index, file path or URL), `backend` (auto/dshow/msmf), width/height, `target_fps`. Model: path, `conf_threshold`, `imgsz`, `device`, `classes_of_interest`. `zones`: polygons in normalized 0..1 image coordinates with `kind` `restricted` or `monitored`; `zone_anchor` (`bottom_center` default, or `center`). `restricted_classes`: object classes that are flagged when inside a restricted zone. `health`: camera-obstruction thresholds. `emit`: repeat suppression. Validation is strict (unknown keys, bad ranges, duplicate zone names, degenerate polygons are rejected).

The shipped default splits the frame vertically (right half `restricted_zone`, left half `monitored_zone`) purely as a demo; **draw zones to match your real camera view.**

Used in the verified run: camera index 0, backend `auto`, 640x480 requested (640x480 received), YOLO11n, `imgsz` 640, `conf_threshold` 0.4, CPU.

## Observation schema (v1) — `backend/protocol/observation.py`

```json
{
  "schema_version": 1,
  "observation_id": "uuid",
  "event_type": "visual_observation | camera_health",
  "device_id": "DEVICE-001",
  "timestamp": "ISO-8601 with timezone (UTC-normalised)",
  "source": "usb_webcam",
  "object": "person",            // visual_observation only
  "confidence": 0.91,            // visual_observation only, 0..1 inclusive, NaN/inf rejected
  "zone": "restricted_zone",     // null if outside all zones; zone and zone_kind set together
  "zone_kind": "restricted | monitored",
  "bbox": {"x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0},   // normalized, x1<x2, y1<y2
  "anomaly": true,
  "anomaly_reason": "restricted_class_in_restricted_zone", // required when anomaly is true
  "model": {"name": "yolo11n", "version": "ultralytics-8.4.50+weights-sha256:0ebbc80d4a76"},
  "details": {}
}
```
`camera_health` has no `object`/`confidence`; `details.state` is `ok | obstructed | source_lost` (plus `previous_state`, `reason`, and frame `mean_brightness`/`texture` where relevant). Unknown fields are rejected, so a trust score or verdict cannot be smuggled into an observation. Numeric epoch timestamps are rejected (ISO-8601 only).

Emission: one observation per (object, zone) per frame (highest confidence; no tracker, so not per person instance); continuing sightings repeat at most every `repeat_interval_s`; a re-appearance after `absence_gap_s` is emitted immediately. Health events are emitted only on state changes, after `consecutive_frames` agreeing frames.

## Run

```
python -m ai.vision probe     --config config/vision.json           # one frame + brightness/texture stats
python -m ai.vision benchmark --config config/vision.json --frames 100
python -m ai.vision run       --config config/vision.json --jsonl evidence/runtime/observations.jsonl
python -m ai.vision run       --config config/vision.json --gateway http://127.0.0.1:8000   # needs ingest token
python -m pytest -m "not inference"    # tests without loading the model
python -m pytest tests/ai              # vision tests only
```
The ingest token is read from `QSHIELD_INGEST_TOKEN` or `keys/ingest.token` (created when the gateway first starts). Frames are never saved or transmitted; only observations leave the process.

## Measured performance (real, this machine)

Laptop: Intel64 Family 6 Model 191 (x86-64), Windows 11, Python 3.12.0, PyTorch 2.13.0+cpu (no CUDA), built-in USB webcam at 640x480. `python -m ai.vision benchmark --frames 100 --warmup 10`, one run each, 100 frames measured, 0 dropped. **Caveat: no person was in view during either run (0 detections), so post-processing cost with detections is not represented.** Single runs; no repeat variance was measured.

| `imgsz` | inference mean / median / p95 (ms) | capture mean (ms) | inference-only FPS | end-to-end FPS (capture+inference) |
|---|---|---|---|---|
| 640 (configured) | 39.8 / 39.6 / 45.1 | 7.9 | 25.1 | 21.0 |
| 320 (comparison) | 19.5 / 19.5 / 22.7 | 13.9 (noisy; p95 31.5) | 51.4 | 30.0 (probably camera-limited) |

The default loop is paced to `target_fps` 5, far below either figure. Detection accuracy at 320 vs 640 was **not** measured; no accuracy claim is made.

## Real observation (webcam + YOLO11n -> gateway, 75 frames)

To get a real detection with no person in view, the run used a scratch config widening `classes_of_interest` (chair, laptop, cup, ...) at `conf_threshold` 0.3. It produced 15 observations (chair in `monitored_zone`, chair in `restricted_zone`, potted plant in `restricted_zone`), all `anomaly: false` because those classes are not in `restricted_classes`. Example as returned by `GET /api/v1/observations` (operator token):

```json
{"received_at": 1790234669.5159633, "schema_version": 1, "observation_id": "fbf21dcf-3c73-4fff-a4b9-5fafd66f8653",
 "event_type": "visual_observation", "device_id": "DEVICE-001", "timestamp": "2026-09-24T07:24:29.290289Z",
 "source": "usb_webcam", "object": "chair", "confidence": 0.4909548759460449,
 "zone": "restricted_zone", "zone_kind": "restricted",
 "bbox": {"x1": 0.6492834687232971, "y1": 0.4948040544986725, "x2": 0.9993894696235657, "y2": 0.9931728839874268},
 "anomaly": false, "anomaly_reason": null,
 "model": {"name": "yolo11n", "version": "ultralytics-8.4.50+weights-sha256:0ebbc80d4a76"}, "details": {"anchor": "bottom_center"}}
```

## Known limitations
- The live `person in restricted zone -> anomaly: true` path was verified with the fake detector in tests, **not** live on a person in front of the camera. Do that as a demo rehearsal.
- Camera-obstruction thresholds (`dark_mean_below` 12, `flat_texture_below` 1.5) are unvalidated defaults. Normal webcam frames measured brightness ~107 and texture ~9.0 here; a real lens-cover test has not been run. Obstruction is only a brightness/texture heuristic (a photo held in front of the lens would not trigger it).
- No object tracking, no re-identification; zone membership is a single anchor point of the bounding box. Zone shapes are hand-authored.
- Camera identity is asserted by configuration (`device_id` in the config); nothing cryptographically binds the webcam or the vision service to the ESP32. The vision service is a trusted local component authenticated by a bearer token.
- No video is stored, so incidents cannot be replayed visually; no accuracy/false-positive evaluation has been done.
- AGPL-3.0 licensing of Ultralytics (see above).
