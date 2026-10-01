"""GET /api/v1/system: the read-only gateway description the dashboard uses instead of hard-coded facts."""
from fastapi.testclient import TestClient

from tests.conftest import INGEST_TOKEN


def _strings(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)
    elif isinstance(x, str):
        yield x


def test_system_describes_the_running_gateway(stack):
    s = stack.op.get("/api/v1/system").json()
    assert isinstance(s["server_time"], float) and abs(s["server_time"] - stack.clock()) < 1
    assert s["transport"] == "http"
    assert s["pqc"]["enabled"] and s["pqc"]["kem_algorithm"] == "ML-KEM-768" and s["pqc"]["sig_algorithm"] == "ML-DSA-65"
    assert s["pqc"]["gateway_kem_key_id"] and len(s["pqc"]["gateway_kem_fingerprint_sha256"]) == 64
    assert any(x["signer_id"] == "vision-1" for x in s["pqc"]["signers"])
    assert s["evidence"] == {"enabled": True, "signed": True, "key_id": s["evidence"]["key_id"], "algorithm": "ML-DSA-65",
                             "hash": "SHA-256"}
    t = s["trust"]
    assert (t["quarantine_below"], t["trusted_min"], t["trusted_reentry_min"]) == (50, 80, 85)
    assert abs(sum(t["weights"].values()) - 1) < 1e-9 and set(t["weights"]) >= {"identity_crypto", "visual", "network"}
    assert s["recovery"]["enabled"] and s["recovery"]["health_checks_required"] == 3


def test_system_follows_the_gateway_clock(stack):
    before = stack.op.get("/api/v1/system").json()["server_time"]
    stack.clock.advance(2520)                         # e.g. the demo's announced TIME-LAPSE
    assert stack.op.get("/api/v1/system").json()["server_time"] - before >= 2520


def test_system_requires_an_operator_and_exposes_no_secrets(stack):
    assert TestClient(stack.app).get("/api/v1/system").status_code == 401
    assert TestClient(stack.app, headers={"Authorization": f"Bearer {INGEST_TOKEN}"}).get("/api/v1/system").status_code == 401
    s = stack.op.get("/api/v1/system").json()
    # No key material of any kind: every string is short (a 64-hex fingerprint is the longest), and the only
    # "*_key" entries are byte SIZES under sizes_bytes.
    assert max(len(v) for v in _strings(s)) <= 64
    assert all(isinstance(v, int) for v in s["pqc"]["sizes_bytes"].values())
    assert "token" not in str(s["operator_auth"]).replace("shared_token_enabled", "")
