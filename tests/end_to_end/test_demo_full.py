"""Phase 11: the integrated demo runs the whole story on a real uvicorn gateway and must keep working."""
import argparse
import importlib.util
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_demo_full_story(capsys):
    spec = importlib.util.spec_from_file_location("demo_full", ROOT / "scripts" / "demo_full.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    args = argparse.Namespace(port=_free_port(), webcam=False, vision_config="config/vision.json", frames=0, pace=0.0,
                              hold=False)
    assert demo.Demo(args).run() == 0
    out = capsys.readouterr().out
    assert "state path: TRUSTED → SUSPICIOUS → QUARANTINED → RECOVERING → VERIFIED → RECOVERED → TRUSTED" in out
    assert "HTTP 401  REJECTED" in out and "replay -> HTTP 409" in out
    assert "device normal telemetry -> HTTP 403" in out
    assert "chain VERIFIED" in out and "signed=ML-DSA-65" in out and "BROKEN" not in out
    assert "TIME-LAPSE" in out and "SIMULATED" in out          # the honesty labels are part of the contract
