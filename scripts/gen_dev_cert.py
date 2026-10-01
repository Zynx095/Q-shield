"""Generate a SELF-SIGNED development TLS certificate for the gateway (not production PKI).

    python scripts/gen_dev_cert.py                       # keys/tls/gateway.crt + gateway.key for localhost,127.0.0.1
    python scripts/gen_dev_cert.py --host 192.168.1.20   # add the LAN address the ESP32/dashboard will use

Then:  QSHIELD_TLS_CERT=keys/tls/gateway.crt QSHIELD_TLS_KEY=keys/tls/gateway.key python -m backend.main
keys/ is gitignored; the key file is created owner-only and never overwritten.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.security.tls import generate_dev_cert  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="keys/tls")
    ap.add_argument("--host", action="append", default=[], help="extra DNS name or IP for the certificate")
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    cert, key = Path(a.out) / "gateway.crt", Path(a.out) / "gateway.key"
    if key.exists():
        raise SystemExit(f"{key} already exists; delete it first to rotate")
    generate_dev_cert(cert, key, ["localhost", "127.0.0.1", *a.host], a.days)
    print(f"wrote {cert} and {key} (SELF-SIGNED, {a.days} days). Clients must trust {cert} explicitly.")


if __name__ == "__main__":
    main()
