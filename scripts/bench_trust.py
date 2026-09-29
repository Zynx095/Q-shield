"""Measure trust-engine processing cost (laptop numbers; not a real-time or deployment claim).

    python scripts/bench_trust.py [--out docs/results/trust_bench.json]

Measures (1) TrustEngine.apply() per signal (pure logic), (2) TrustService.process_pending() end to end over rows
already in SQLite (feature extraction + engine + persistence), for a mixed workload.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.devices.store import Store  # noqa: E402
from backend.trust.engine import TrustEngine  # noqa: E402
from backend.trust.model import Auth, Kind, Signal  # noqa: E402
from backend.trust.service import TrustService  # noqa: E402

T0 = 1_700_000_000.0


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p / 100 * len(xs)))]


def summarize(us):
    return {"n": len(us), "mean_us": round(statistics.fmean(us), 2), "p50_us": round(pct(us, 50), 2),
            "p95_us": round(pct(us, 95), 2), "p99_us": round(pct(us, 99), 2), "max_us": round(max(us), 2)}


def bench_engine(n=20000):
    e = TrustEngine()
    e.track("D")
    lat, t = [], T0
    for i in range(n):
        t += 1.0
        k = i % 10
        if k == 0:
            s = Signal(f"a{i}", "D", Kind.VISUAL_RULE_VIOLATION, t, Auth.SIGNER_MLDSA, confidence=0.5 + (i % 50) / 100, value={"zone": str(i % 7)})
        elif k == 1:
            s = Signal(f"a{i}", "D", Kind.INVALID_TAG, t, Auth.UNAUTHENTICATED)
        elif k == 2:
            s = Signal(f"a{i}", "D", Kind.PHYSICAL_TAMPER, t, Auth.DEVICE_HMAC, value={"active": (i // 10) % 2 == 0})
        else:
            s = Signal(f"a{i}", "D", Kind.DEVICE_EVIDENCE, t, Auth.DEVICE_HMAC)
        t0 = time.perf_counter()
        e.apply(s)
        lat.append((time.perf_counter() - t0) * 1e6)
    return summarize(lat)


def bench_service(n=2000):
    store = Store(":memory:")
    store.enroll_device("DEVICE-001", "hmac-sha256-psk", T0)
    for i in range(n):
        store.touch("DEVICE-001", T0 + i, telemetry={"tamper": False, "temperature_c": 25.0}, message_kind="telemetry")
        if i % 20 == 0:
            body = {"observation_id": f"o{i}", "device_id": "DEVICE-001", "event_type": "visual_observation", "anomaly": True,
                    "confidence": 0.8, "zone": "z", "object": "person",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(T0 + i))}
            store._db.execute("INSERT INTO observations(observation_id, received_at, device_id, event_type, observed_at, anomaly, body, auth) "
                              "VALUES (?,?,?,?,?,?,?,?)", (f"o{i}", T0 + i, "DEVICE-001", "visual_observation", body["timestamp"], 1,
                                                           json.dumps(body), "ML-DSA-65:vision-1"))
    store._db.commit()
    svc = TrustService(store, clock=lambda: T0 + n)
    t0 = time.perf_counter()
    svc.process_pending()
    batch = time.perf_counter() - t0
    rows = n + n // 20
    # incremental: one new record at a time, as the gateway middleware does
    lat = []
    for i in range(300):
        store.touch("DEVICE-001", T0 + n + i, telemetry={"tamper": False}, message_kind="telemetry")
        t1 = time.perf_counter()
        svc.process_pending()
        lat.append((time.perf_counter() - t1) * 1e6)
    return {"batch_rows": rows, "batch_seconds": round(batch, 4), "batch_rows_per_s": round(rows / batch),
            "incremental_process_pending": summarize(lat)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/results/trust_bench.json")
    a = ap.parse_args()
    res = {"host": {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine()},
           "engine_apply": bench_engine(), "service": bench_service(),
           "caveat": "Single-process, single-device laptop measurement; SQLite in memory. Not a real-time or deployment-latency claim."}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
