"""Vision service CLI.

    python -m ai.vision run       --config config/vision.json [--jsonl PATH] [--gateway URL] [--max-frames N]
    python -m ai.vision benchmark --config config/vision.json [--frames 100]
    python -m ai.vision probe     --config config/vision.json     # grab one frame, print frame stats

Emits observations only; it never decides trust. With --gateway, observations are POSTed
to /api/v1/observations using the ingest token (QSHIELD_INGEST_TOKEN or keys/ingest.token).
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

from ai.vision.camera import OpenCVSource
from ai.vision.config import ConfigError, VisionConfig, load_config
from ai.vision.detector import YoloDetector
from ai.vision.health import frame_stats
from ai.vision.pipeline import VisionPipeline
from ai.vision.runner import benchmark, run
from ai.vision.sinks import FanoutSink, HttpSink, JsonlSink


def _source(cfg: VisionConfig) -> OpenCVSource:
    c = cfg.camera
    return OpenCVSource(c.source, c.backend, c.width, c.height)


def _detector(cfg: VisionConfig) -> YoloDetector:
    m = cfg.model
    return YoloDetector(m.path, m.name, m.conf_threshold, m.imgsz, m.device, m.classes_of_interest)


def _ingest_token() -> str:
    tok = os.environ.get("QSHIELD_INGEST_TOKEN")
    if tok:
        return tok.strip()
    path = Path(os.environ.get("KEYS_DIR", "keys")) / "ingest.token"
    try:
        return path.read_text().strip()
    except OSError:
        sys.exit(f"ingest token not found: set QSHIELD_INGEST_TOKEN or start the gateway once to create {path}")


def _signed_sink(a, cfg: VisionConfig):
    """ML-DSA identity for this software service. Needs only its own key-encryption key, not the master key."""
    from backend.security.keystore import PqcKeyStore, load_kek_file
    from backend.security.pqc import get_backend
    from ai.vision.signed_sink import SignedHttpSink

    backend = get_backend()
    kek_hex = os.environ.get("QSHIELD_SIGNER_KEK_HEX")
    kek = bytes.fromhex(kek_hex) if kek_hex else load_kek_file(Path(a.keys_dir) / "pqc" / f"{a.signer_id}.kek")
    ks = PqcKeyStore(Path(a.keys_dir) / "pqc")
    _, sk = ks.load_private(backend, a.signer_id, kek)
    gw_id, gw_pk = None, None
    if a.secure:
        pin = Path(a.gateway_key) if a.gateway_key else Path(a.keys_dir) / "pqc" / "gateway-kem-1.pub.json"
        rec = PqcKeyStore(pin.parent).load_public(pin.name[:-len(".pub.json")])
        gw_id, gw_pk = rec.key_id, rec.public_key
    source_id = f"usb_webcam:{cfg.camera.source}" if isinstance(cfg.camera.source, int) else "usb_webcam:file"
    return SignedHttpSink(a.gateway, backend, a.signer_id, source_id, sk, secure=a.secure,
                          gateway_key_id=gw_id, gateway_public_key=gw_pk)


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m ai.vision")
    ap.add_argument("command", choices=["run", "benchmark", "probe"])
    ap.add_argument("--config", default="config/vision.json")
    ap.add_argument("--jsonl", help="also append observations to this JSONL file")
    ap.add_argument("--gateway", help="gateway base URL, e.g. http://127.0.0.1:8000")
    ap.add_argument("--signer-id", help="send ML-DSA-signed observations as this enrolled signer (see scripts/pqc_provision.py)")
    ap.add_argument("--secure", action="store_true", help="with --signer-id: also use an ML-KEM session (AES-256-GCM)")
    ap.add_argument("--keys-dir", default=os.environ.get("KEYS_DIR", "keys"))
    ap.add_argument("--gateway-key", help="pinned gateway KEM public key record (default: <keys-dir>/pqc/gateway-kem-1.pub.json)")
    ap.add_argument("--max-frames", type=int)
    ap.add_argument("--frames", type=int, default=100, help="benchmark: frames to measure")
    ap.add_argument("--warmup", type=int, default=10)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    try:
        cfg = load_config(a.config)
    except ConfigError as e:
        return sys.exit(f"config error: {e}")

    if a.command == "probe":
        src = _source(cfg)
        try:
            frame = None
            for _ in range(15):  # let auto-exposure settle
                frame = src.read()
            if frame is None:
                return sys.exit("no frame received")
            print(json.dumps({"shape": list(frame.shape), **frame_stats(frame).__dict__}))
        finally:
            src.release()
        return 0

    detector = _detector(cfg)
    src = _source(cfg)
    try:
        if a.command == "benchmark":
            print(json.dumps(benchmark(src, detector, a.frames, a.warmup), indent=2))
            return 0
        sinks = []
        if a.jsonl:
            sinks.append(JsonlSink(a.jsonl))
        if a.gateway and a.signer_id:
            sinks.append(_signed_sink(a, cfg))
        elif a.gateway:
            sinks.append(HttpSink(a.gateway, _ingest_token()))
        if not sinks:
            sinks.append(JsonlSink("evidence/runtime/observations.jsonl"))
        pipeline = VisionPipeline(cfg, detector)
        n = run(pipeline, src, FanoutSink(*sinks), cfg.camera.target_fps, a.max_frames)
        print(f"processed {n} frames")
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        src.release()


if __name__ == "__main__":
    sys.exit(main())
