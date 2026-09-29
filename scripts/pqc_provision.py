"""PQC key provisioning for the gateway and the vision service.

    python scripts/pqc_provision.py init-gateway [--key-id gateway-kem-1]
    python scripts/pqc_provision.py enroll-signer vision-1 --device DEVICE-001 [--source usb_webcam]
    python scripts/pqc_provision.py retire-signer vision-1 [--revoke]
    python scripts/pqc_provision.py list

Keys live under keys/pqc/ (gitignored). Private keys are sealed with AES-256-GCM under
subkeys derived from the gateway master key (keys/master.key). `enroll-signer` also writes
keys/pqc/<id>.kek: the signer's own key-encryption key, which is what the vision service is
given INSTEAD of the master key (move it to the vision service's host/account, then delete the
copy here if they are separate). Nothing secret is printed.

Rotation: create a new id (vision-2 / gateway-kem-2), point the service at it, then retire the
old one. Existing key ids are never overwritten.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import Settings  # noqa: E402
from backend.devices.store import Store  # noqa: E402
from backend.security.credentials import load_or_create_master_key  # noqa: E402
from backend.security.fileutil import write_private_file  # noqa: E402
from backend.security.keystore import (  # noqa: E402
    KIND_KEM, KIND_SIG, KeystoreError, PqcKeyStore, kem_kek, signer_kek,
)
from backend.security.pqc import get_backend  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("init-gateway")
    g.add_argument("--key-id", default="gateway-kem-1")
    e = sub.add_parser("enroll-signer")
    e.add_argument("signer_id")
    e.add_argument("--device", action="append", required=True, help="device id this signer may report on (repeatable)")
    e.add_argument("--source", default="usb_webcam")
    r = sub.add_parser("retire-signer")
    r.add_argument("signer_id")
    r.add_argument("--revoke", action="store_true", help="mark revoked (compromise) instead of retired")
    sub.add_parser("list")
    a = ap.parse_args()

    st = Settings.load()
    backend = get_backend(st.pqc_kem_algorithm, st.pqc_sig_algorithm)
    ks = PqcKeyStore(Path(st.keys_dir) / "pqc")
    master = load_or_create_master_key(st.keys_dir, st.master_key_hex)
    store = Store(st.db_path)

    try:
        if a.cmd == "init-gateway":
            rec = ks.create(backend, KIND_KEM, a.key_id, kem_kek(master, a.key_id))
            print(f"created gateway {rec.algorithm} key {rec.key_id}\n  fingerprint (pin this in clients): {rec.fingerprint}")
        elif a.cmd == "enroll-signer":
            if store.get_signer(a.signer_id) is not None:
                print(f"error: signer {a.signer_id} already registered", file=sys.stderr)
                return 1
            kek = signer_kek(master, a.signer_id)
            rec = ks.create(backend, KIND_SIG, a.signer_id, kek)
            write_private_file(Path(st.keys_dir) / "pqc" / f"{a.signer_id}.kek", kek.hex().encode() + b"\n")
            store.add_signer(a.signer_id, rec.algorithm, rec.public_key, a.source, a.device, time.time())
            print(f"enrolled signer {rec.key_id} ({rec.algorithm}) for {a.source} on {a.device}\n"
                  f"  fingerprint: {rec.fingerprint}\n  key-encryption key: keys/pqc/{a.signer_id}.kek")
        elif a.cmd == "retire-signer":
            ok = store.set_signer_status(a.signer_id, "revoked" if a.revoke else "retired", time.time())
            print("done" if ok else f"error: unknown signer {a.signer_id}")
            return 0 if ok else 1
        else:
            for s in store.list_signers():
                print(f"signer {s.signer_id}  {s.algorithm}  {s.status}  {s.source}  devices={list(s.allowed_devices)}")
            for p in sorted((Path(st.keys_dir) / "pqc").glob("*.pub.json")):
                rec = ks.load_public(p.name[:-len(".pub.json")])
                print(f"key    {rec.key_id}  {rec.kind}  {rec.algorithm}  sha256={rec.fingerprint[:16]}...")
    except KeystoreError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
