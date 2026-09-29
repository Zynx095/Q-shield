# Evidence used in the presentation

Everything a slide claims traces to a file here or to a file this folder copies. Nothing is estimated.

| File | What it is | How it was produced |
|---|---|---|
| `live-run-phase3.json` | Real run: USB webcam + YOLO11n + gateway + ML-KEM session + ML-DSA-signed observations. 11 stored, all `ML-DSA-65:vision-1`; HTTP 401 on altered payload, 409 on replay; offline re-verification 11/11 valid, 11/11 altered copies rejected. Contains no keys, tokens or signature bytes. | `scripts/export_live_evidence.py` from the recorded gateway database. Scene note inside: no person in view; classes widened to obtain detections; no anomaly flagged. |
| `pqc-benchmark.json` | Raw PQC latency data (300 calls x 5 rounds per operation), sizes, environment (i7-13700HX, Windows 11, Python 3.12.0, pqcrypto 1.0.0). Laptop only. | `python scripts/bench_pqc.py` |
| `acvp-manifest.json` | Provenance of the NIST ACVP vectors: repository, commit `975de31eb83d87039ec88934fdc47d8c312b892d`, SHA-256 of the source files. | `python scripts/fetch_acvp_vectors.py` |
| `vision-benchmark-640-raw.json` | Raw output of the 640-input vision benchmark (100 frames, 0 detections). The 320-input run was recorded in `ai/README.md` only. | `python -m ai.vision benchmark` |
| `pytest-summary.txt` | Fresh `python -m pytest` result (347 passed) and the per-file test counts. | run at packaging time |
| `demo-forgery-run.txt` | Real output of the tamper/replay demo script, including why the replay returned 401 (stale) here and 409 in the original run. | `python scripts/demo_forgery.py` |
| `environment.txt` | Library and OS versions used. | recorded at packaging time |

Not in this folder because they do not exist: screenshots of any kind, accuracy / false-positive measurements, ESP32 measurements, scalability measurements, a live person-in-restricted-zone run.
