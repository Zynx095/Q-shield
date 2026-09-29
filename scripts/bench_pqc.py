"""Benchmark the PQC operations on THIS machine (laptop gateway/vision service class hardware).

    python scripts/bench_pqc.py [--iterations 300] [--rounds 5] [--out docs/results/pqc-benchmark.json]

Each operation is timed individually with time.perf_counter_ns over `iterations` calls per round,
for `rounds` rounds (after a warm-up), and the distribution is reported per round and overall.
Nothing here measures ESP32 or any embedded target; these numbers must not be quoted as such.
"""
import argparse
import json
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.protocol.observation import Observation  # noqa: E402
from backend.protocol.signed_observation import CONTEXT, sign_observation, signing_bytes  # noqa: E402
from backend.security.pqc import get_backend  # noqa: E402
from backend.security.session import client_initiate, server_accept, HandshakeInit  # noqa: E402


def cpu_name() -> str:
    for cmd in (["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"],
                ["wmic", "cpu", "get", "name"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip().splitlines()
            out = [x.strip() for x in out if x.strip() and x.strip().lower() != "name"]
            if out:
                return out[0]
        except Exception:
            pass
    return platform.processor()


def stats(ms: list[float]) -> dict:
    s = sorted(ms)
    return {"n": len(s), "mean": round(statistics.fmean(s), 4), "median": round(statistics.median(s), 4),
            "p95": round(s[int(0.95 * (len(s) - 1))], 4), "min": round(s[0], 4), "max": round(s[-1], 4),
            "stdev": round(statistics.pstdev(s), 4)}


def measure(fn, iterations: int, rounds: int, warmup: int = 20) -> dict:
    for _ in range(warmup):
        fn()
    per_round, all_ms = [], []
    for _ in range(rounds):
        ms = []
        for _ in range(iterations):
            t = time.perf_counter_ns()
            fn()
            ms.append((time.perf_counter_ns() - t) / 1e6)
        per_round.append(round(statistics.median(ms), 4))
        all_ms += ms
    return {**stats(all_ms), "median_per_round_ms": per_round}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=300)
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--out", default="docs/results/pqc-benchmark.json")
    a = ap.parse_args()

    b = get_backend("ML-KEM-768", "ML-DSA-65")
    kem, sig = b.kem_keygen(), b.sig_keygen()
    ct, _ = b.kem_encapsulate(kem.public_key)
    obs = Observation(event_type="visual_observation", device_id="DEVICE-001", timestamp="2026-01-01T00:00:00Z",
                      source="usb_webcam", object="person", confidence=0.91, zone="restricted_zone",
                      zone_kind="restricted", bbox={"x1": 0.6, "y1": 0.1, "x2": 0.9, "y2": 0.9}, anomaly=True,
                      anomaly_reason="restricted_class_in_restricted_zone", model={"name": "yolo11n", "version": "v"})
    env = sign_observation(b, sig.secret_key, "vision-1", "usb_webcam:0", obs, datetime.now(timezone.utc))
    msg = signing_bytes(env)                       # a realistic signed-message size
    sg = b.sign(sig.secret_key, msg, CONTEXT)
    it, rd = a.iterations, a.rounds

    ops = {
        "ml_kem_768_keygen": measure(b.kem_keygen, it, rd),
        "ml_kem_768_encapsulate": measure(lambda: b.kem_encapsulate(kem.public_key), it, rd),
        "ml_kem_768_decapsulate": measure(lambda: b.kem_decapsulate(kem.secret_key, ct), it, rd),
        "ml_dsa_65_keygen": measure(b.sig_keygen, it, rd),
        "ml_dsa_65_sign": measure(lambda: b.sign(sig.secret_key, msg, CONTEXT), it, rd),
        "ml_dsa_65_verify": measure(lambda: b.verify(sig.public_key, msg, sg, CONTEXT), it, rd),
    }

    now = datetime.now(timezone.utc)

    def handshake():
        init, pending = client_initiate(b, "gateway-kem-1", kem.public_key, "vision-1", sig.secret_key, now)
        resp, _ = server_accept(b, HandshakeInit(**init), kem.secret_key, sig.public_key, now, 300, 3600)
        pending.finish(resp)

    ops["full_session_handshake_client_and_server"] = measure(handshake, max(20, it // 5), rd)

    result = {
        "measured_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": "laptop-class CPU, single process, Python bindings. NOT ESP32 / embedded performance.",
        "environment": {"cpu": cpu_name(), "machine": platform.machine(), "os": platform.platform(),
                        "python": platform.python_version(), "cpu_count_logical": __import__("os").cpu_count(),
                        "note": "no CPU pinning; other processes were running; power plan not controlled"},
        "crypto": b.info(),
        "method": {"iterations_per_round": it, "rounds": rd, "warmup_calls": 20, "timer": "perf_counter_ns",
                   "signed_message_bytes": len(msg), "handshake_iterations_per_round": max(20, it // 5)},
        "sizes_bytes": {**b.info()["sizes_bytes"], "signed_observation_envelope_json": len(json.dumps(env)),
                        "signature_base64_in_envelope": len(env["signature"])},
        "latency_ms": ops,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(result, indent=2))
    print(f"{'operation':46s} {'median':>9s} {'mean':>9s} {'p95':>9s} {'min':>9s} {'max':>9s}  (ms)")
    for k, v in ops.items():
        print(f"{k:46s} {v['median']:9.3f} {v['mean']:9.3f} {v['p95']:9.3f} {v['min']:9.3f} {v['max']:9.3f}")
    print("sizes:", json.dumps(result["sizes_bytes"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
