"""Export a live run's evidence from a gateway DB into a shareable JSON file, re-verifying it.

    python scripts/export_live_evidence.py --db q.db --server-log server.log --out docs/results/live-run-phase3.json

For every stored observation that has a signed envelope, this script independently re-verifies the
ML-DSA signature OFFLINE using the signer's public key from the `signers` table and the same signing
bytes/context the gateway uses, and also proves the check is not vacuous by verifying a copy of each
envelope whose payload was altered (must fail). Output contains no secrets: no keys, tokens or
signature bytes (only their length and verification result).
"""
import argparse
import base64
import collections
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.protocol.signed_observation import CONTEXT, SignedObservationEnvelope, signing_bytes  # noqa: E402
from backend.security.pqc import get_backend  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--server-log")
    ap.add_argument("--out", required=True)
    ap.add_argument("--note", action="append", default=[], help="free-text run notes (repeatable)")
    a = ap.parse_args()

    db = sqlite3.connect(a.db)
    db.row_factory = sqlite3.Row
    backend = get_backend()
    signers = {r["signer_id"]: r for r in db.execute("SELECT * FROM signers")}
    rows = db.execute("SELECT * FROM observations ORDER BY id").fetchall()

    observations, ok_count, tamper_rejected = [], 0, 0
    for r in rows:
        body = json.loads(r["body"])
        entry = {"observation_id": r["observation_id"], "auth": r["auth"], "event_type": body["event_type"],
                 "object": body.get("object"), "confidence": body.get("confidence"), "zone": body.get("zone"),
                 "anomaly": body["anomaly"], "timestamp": body["timestamp"], "model": body.get("model")}
        if r["envelope"]:
            env = SignedObservationEnvelope.model_validate_json(r["envelope"])
            pk = bytes(signers[env.signer_id]["public_key"])
            sig = base64.b64decode(env.signature)
            good = backend.verify(pk, signing_bytes(env), sig, CONTEXT)
            forged = env.model_copy(update={"payload": env.payload.replace('"person"', '"nobody"') + " "})
            bad = backend.verify(pk, signing_bytes(forged), sig, CONTEXT)
            ok_count += good
            tamper_rejected += (not bad)
            entry.update({"signature_bytes": len(sig), "offline_reverification": "valid" if good else "INVALID",
                          "altered_copy_reverification": "rejected" if not bad else "ACCEPTED (bug)"})
        observations.append(entry)

    events = [{"event_type": e["event_type"], "severity": e["severity"], "details": json.loads(e["details"])}
              for e in db.execute("SELECT * FROM security_events ORDER BY id")]
    http = []
    if a.server_log:
        for line in Path(a.server_log).read_text().splitlines():
            m = re.search(r'"(POST|GET) (/api/v1/\S+) HTTP/1.1" (\d{3})', line)
            if m and m.group(1) == "POST":
                http.append({"method": m.group(1), "path": m.group(2), "status": int(m.group(3))})

    confs = [o["confidence"] for o in observations if o["confidence"] is not None]
    out = {
        "what": "Real run: USB webcam -> YOLO11n -> vision service (ML-DSA-65 identity) -> ML-KEM-768 session -> gateway",
        "notes": a.note,
        "signers": [{"signer_id": s["signer_id"], "algorithm": s["algorithm"], "source": s["source"],
                     "allowed_devices": json.loads(s["allowed_devices"]), "status": s["status"]} for s in signers.values()],
        "observations_stored": len(observations),
        "auth_labels": dict(collections.Counter(o["auth"] for o in observations)),
        "objects": dict(collections.Counter(o["object"] for o in observations)),
        "anomalies_flagged": sum(1 for o in observations if o["anomaly"]),
        "confidence_range": [round(min(confs), 3), round(max(confs), 3)] if confs else None,
        "offline_reverification": {"envelopes_checked": sum(1 for o in observations if "offline_reverification" in o),
                                   "valid": ok_count, "altered_copies_rejected": tamper_rejected},
        "security_events": events,
        "http_post_status_sequence": collections.Counter(f'{h["path"]} -> {h["status"]}' for h in http),
        "observations": observations,
    }
    out["http_post_status_sequence"] = dict(out["http_post_status_sequence"])
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(json.dumps({k: out[k] for k in ("observations_stored", "auth_labels", "objects", "anomalies_flagged",
                                          "offline_reverification", "http_post_status_sequence")}, indent=1))
    print("events:", [e["event_type"] for e in events])
    return 0


if __name__ == "__main__":
    sys.exit(main())
