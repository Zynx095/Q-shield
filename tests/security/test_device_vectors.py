"""Device-protocol test vectors (tests/vectors/envelope_v1_cases.json) for the ESP32 firmware.

They must match the reference implementation byte for byte, and a gateway must accept every envelope, as sent, in
order. A firmware that reproduces them needs no gateway change: that is the hardware adapter contract."""
import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config import Settings
from backend.devices.store import Store
from backend.protocol.envelope import AUTH_HMAC, build_hmac_envelope, signing_input
from backend.security.credentials import EncryptedCredentialStore
from backend.trust.config import TrustConfig
from backend.trust.service import TrustService
from tests.conftest import INGEST_TOKEN, MASTER_KEY, OPERATOR_TOKEN

ROOT = Path(__file__).resolve().parents[2]
V = json.loads((ROOT / "tests" / "vectors" / "envelope_v1_cases.json").read_text(encoding="utf-8"))
SECRET = bytes.fromhex(V["secret_hex"])


def test_vectors_file_is_generated_from_the_reference_implementation():
    r = subprocess.run([sys.executable, "scripts/make_device_vectors.py", "--check"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_case_matches_signing_input_tag_and_wire_bytes():
    for c in V["cases"]:
        si = signing_input(AUTH_HMAC, c["type"], V["device_id"], c["counter"], c["payload"])
        assert si.hex() == c["signing_input_hex"], c["name"]
        env = build_hmac_envelope(SECRET, c["type"], V["device_id"], c["counter"], c["payload"])
        assert env["tag"] == c["tag"], c["name"]
        assert json.loads(c["envelope_json"]) == env, c["name"]
        assert c["envelope_json"].startswith('{"proto":1,"auth":"hmac-sha256-psk","type":"'), c["name"]


def test_the_escaping_case_carries_a_quote_and_a_backslash():
    (c,) = [c for c in V["cases"] if c["name"] == "register_escaped_text"]
    fw = json.loads(c["payload"])["fw_version"]
    assert '"' in fw and "\\" in fw
    assert json.dumps(c["payload"]) in c["envelope_json"]        # the payload text, escaped once more as a JSON string
    assert json.loads(c["envelope_json"])["payload"] == c["payload"]


def test_a_gateway_accepts_every_vector_in_order_and_applies_the_tamper_report():
    clock = [1_700_000_000.0]
    store = Store(":memory:")
    creds = EncryptedCredentialStore(store, MASTER_KEY)
    store.enroll_device(V["device_id"], AUTH_HMAC, clock[0])
    creds.put(V["device_id"], SECRET)
    trust = TrustService(store, TrustConfig(), clock=lambda: clock[0])
    app = create_app(Settings(db_path=":memory:"), clock=lambda: clock[0], store=store, creds=creds,
                     operator_token=OPERATOR_TOKEN, ingest_token=INGEST_TOKEN, trust=trust)
    gw, op = TestClient(app), TestClient(app, headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"})
    path = {"register": "register", "heartbeat": "heartbeat", "telemetry": "telemetry"}
    for c in V["cases"]:
        clock[0] += 1
        r = gw.post(f"/api/v1/{path[c['type']]}", content=c["envelope_json"].encode(),
                    headers={"Content-Type": "application/json"})
        assert r.status_code == 200, (c["name"], r.text)
        if c["name"] == "telemetry_tamper_open":
            assert op.get(f"/api/v1/trust/{V['device_id']}").json()["tamper_active"] is True
    dev = op.get(f"/api/v1/devices/{V['device_id']}").json()
    assert dev["hw"] == "esp32" and dev["rssi_dbm"] == -58 and dev["pressure_hpa"] == 1008.6


def test_one_flipped_byte_or_a_replayed_vector_is_refused():
    store = Store(":memory:")
    creds = EncryptedCredentialStore(store, MASTER_KEY)
    store.enroll_device(V["device_id"], AUTH_HMAC, 1.0)
    creds.put(V["device_id"], SECRET)
    gw = TestClient(create_app(Settings(db_path=":memory:"), clock=lambda: 2.0, store=store, creds=creds,
                               operator_token=OPERATOR_TOKEN, ingest_token=INGEST_TOKEN))
    first = V["cases"][0]["envelope_json"]
    tampered = first.replace("esp32", "esp33", 1)                  # one byte of the payload changed, tag kept
    assert tampered != first
    assert gw.post("/api/v1/register", content=tampered.encode(), headers={"Content-Type": "application/json"}).status_code == 401
    assert gw.post("/api/v1/register", content=first.encode(), headers={"Content-Type": "application/json"}).status_code == 200
    assert gw.post("/api/v1/register", content=first.encode(), headers={"Content-Type": "application/json"}).status_code == 401
