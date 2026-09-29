"""Fetch NIST ACVP test vectors (pinned commit) and extract the subsets Q-SHIELD tests use.

    python scripts/fetch_acvp_vectors.py

Source: https://github.com/usnistgov/ACVP-Server (gen-val/json-files/*/internalProjection.json),
pinned to one commit so the result is reproducible. Nothing is generated or edited by us:
each test case is copied verbatim; the source files' SHA-256 digests are recorded in the output
so the extraction can be audited. Output: tests/vectors/pqc/.
"""
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

COMMIT = "975de31eb83d87039ec88934fdc47d8c312b892d"
BASE = f"https://raw.githubusercontent.com/usnistgov/ACVP-Server/{COMMIT}/gen-val/json-files"
OUT = Path(__file__).resolve().parent.parent / "tests" / "vectors" / "pqc"

SOURCES = {
    "mlkem768": ("ML-KEM-encapDecap-FIPS203", "FIPS 203"),
    "mldsa65_sigver": ("ML-DSA-sigVer-FIPS204", "FIPS 204"),
}


def fetch(name: str) -> tuple[bytes, str]:
    url = f"{BASE}/{name}/internalProjection.json"
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read(), url


def keep(t: dict, fields: tuple[str, ...]) -> dict:
    return {k: t[k] for k in fields if k in t}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "acvp_server_commit": COMMIT, "sources": {}}

    raw, url = fetch("ML-KEM-encapDecap-FIPS203")
    data = json.loads(raw)
    groups = []
    for g in data["testGroups"]:
        if g["parameterSet"] != "ML-KEM-768":
            continue
        fields = {"encapsulation": ("tcId", "dk", "c", "k"),
                  "decapsulation": ("tcId", "dk", "c", "k", "reason"),
                  "encapsulationKeyCheck": ("tcId", "ek", "testPassed", "reason"),
                  "decapsulationKeyCheck": ("tcId", "dk", "testPassed", "reason")}[g["function"]]
        groups.append({"tgId": g["tgId"], "function": g["function"], "testType": g["testType"],
                       "tests": [keep(t, fields) for t in g["tests"]]})
    (OUT / "acvp_mlkem768.json").write_text(json.dumps(
        {"algorithm": data["algorithm"], "mode": data["mode"], "revision": data["revision"],
         "parameterSet": "ML-KEM-768", "source_url": url, "source_sha256": hashlib.sha256(raw).hexdigest(),
         "testGroups": groups}, indent=1))
    manifest["sources"]["acvp_mlkem768.json"] = {"url": url, "sha256": hashlib.sha256(raw).hexdigest(),
                                                 "groups": [g["function"] for g in groups]}

    raw, url = fetch("ML-DSA-sigVer-FIPS204")
    data = json.loads(raw)
    groups = []
    for g in data["testGroups"]:
        if g["parameterSet"] == "ML-DSA-65" and g["signatureInterface"] == "external" and g["preHash"] == "pure":
            groups.append({"tgId": g["tgId"], "signatureInterface": "external", "preHash": "pure",
                           "tests": [keep(t, ("tcId", "pk", "message", "context", "signature", "testPassed", "reason"))
                                     for t in g["tests"]]})
    (OUT / "acvp_mldsa65_sigver.json").write_text(json.dumps(
        {"algorithm": data["algorithm"], "mode": data["mode"], "revision": data["revision"],
         "parameterSet": "ML-DSA-65", "source_url": url, "source_sha256": hashlib.sha256(raw).hexdigest(),
         "testGroups": groups}, indent=1))
    manifest["sources"]["acvp_mldsa65_sigver.json"] = {"url": url, "sha256": hashlib.sha256(raw).hexdigest(),
                                                       "groups": ["external/pure"]}

    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=1))
    for f in sorted(OUT.glob("*.json")):
        print(f.name, f.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
