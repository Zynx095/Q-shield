"""Run a simulated device against a gateway.

    python -m device_agent --device-id DEVICE-001 --url http://127.0.0.1:8000

The secret is read from keys/devices/<device-id>.secret (created by scripts/enroll_device.py)
or from the QSHIELD_DEVICE_SECRET_HEX environment variable. It is never printed.
"""
import argparse
import os
import time
from pathlib import Path

import httpx

from device_agent.agent import DeviceAgent


def load_secret(device_id: str, keys_dir: str) -> bytes:
    hex_value = os.environ.get("QSHIELD_DEVICE_SECRET_HEX")
    if not hex_value:
        hex_value = (Path(keys_dir) / "devices" / f"{device_id}.secret").read_text().strip()
    return bytes.fromhex(hex_value)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device-id", default="DEVICE-001")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--keys-dir", default="keys")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--count", type=int, default=0, help="0 = run until interrupted")
    ap.add_argument("--start-counter", type=int, default=int(time.time()),
                    help="initial counter; defaults to current epoch seconds so restarts stay ahead of the gateway")
    a = ap.parse_args()

    with httpx.Client(base_url=a.url, timeout=5.0) as client:
        agent = DeviceAgent(a.device_id, load_secret(a.device_id, a.keys_dir), client,
                            start_counter=a.start_counter)
        print("register:", agent.register().status_code)
        n = 0
        while a.count == 0 or n < a.count:
            print("heartbeat:", agent.heartbeat().status_code, "telemetry:", agent.telemetry().status_code)
            n += 1
            time.sleep(a.interval)


if __name__ == "__main__":
    main()
