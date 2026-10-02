"""Vision service -> gateway with a real ML-DSA identity (signed and ML-KEM-session modes),
plus provisioning end to end. The gateway app is driven in-process; no camera or model."""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai.vision.signed_sink import SignedHttpSink
from backend.security.keystore import PqcKeyStore
from tests.pqc_helpers import make_obs, now_dt

ROOT = Path(__file__).resolve().parents[2]


def sink(client, world, clock, signer="vision-1", secure=False, gw_pk=None):
    return SignedHttpSink("http://test", world.backend, signer, "usb_webcam:0", world.signers[signer],
                          secure=secure, gateway_key_id="gateway-kem-1",
                          gateway_public_key=gw_pk or world.kem_rec.public_key, client=client,
                          now=lambda: now_dt(clock))


def test_signed_mode_end_to_end(pqc_client, pqc_operator, pqc_world, clock):
    s = sink(pqc_client, pqc_world, clock)
    s.emit(make_obs(clock))
    (o,) = pqc_operator.get("/api/v1/observations").json()
    assert o["auth"] == "ML-DSA-65:vision-1"


def test_secure_mode_end_to_end_and_session_reuse(pqc_client, pqc_operator, pqc_world, clock, pqc_app):
    s = sink(pqc_client, pqc_world, clock, secure=True)
    for _ in range(3):
        s.emit(make_obs(clock))
    assert len(pqc_operator.get("/api/v1/observations").json()) == 3
    assert len(pqc_world.gateway._sessions) == 1        # one handshake, three protected messages


def test_secure_mode_refuses_to_send_to_wrong_gateway_key(pqc_client, pqc_operator, pqc_world, clock, pqc_backend):
    impostor = pqc_backend.kem_keygen()
    s = sink(pqc_client, pqc_world, clock, secure=True, gw_pk=impostor.public_key)
    s.emit(make_obs(clock))
    assert pqc_operator.get("/api/v1/observations").json() == []     # nothing sent without gateway proof
    assert len(s._queue) == 1


def test_secure_mode_reestablishes_after_gateway_lost_session(pqc_client, pqc_operator, pqc_world, clock):
    s = sink(pqc_client, pqc_world, clock, secure=True)
    s.emit(make_obs(clock))
    pqc_world.gateway._sessions.clear()                 # e.g. gateway restarted
    s.emit(make_obs(clock))                             # 401 -> queued, channel dropped
    s.emit(make_obs(clock))                             # new session, queue flushed
    assert len(pqc_operator.get("/api/v1/observations").json()) == 3


def test_sink_queues_when_gateway_down_then_flushes(pqc_app, pqc_operator, pqc_world, clock):
    class Down:
        def post(self, *a, **k):
            raise ConnectionError("down")
    s = sink(Down(), pqc_world, clock)
    mono = [0.0]
    s._mono = lambda: mono[0]            # the sink now backs off after a failure (1 s first); drive its clock
    s.emit(make_obs(clock))
    assert len(s._queue) == 1
    s._client = TestClient(pqc_app)
    mono[0] += 1.5                       # past the first backoff
    s.emit(make_obs(clock))
    assert len(pqc_operator.get("/api/v1/observations").json()) == 2


def test_sink_treats_replay_409_as_delivered(pqc_client, pqc_world, clock):
    s = sink(pqc_client, pqc_world, clock)
    obs = make_obs(clock)
    s.emit(obs)
    from backend.protocol.signed_observation import sign_observation
    s._queue.append(sign_observation(pqc_world.backend, pqc_world.signers["vision-1"], "vision-1", "usb_webcam:0",
                                     obs, now_dt(clock)))     # same observation_id again
    s._flush()
    assert len(s._queue) == 0


def test_signer_without_authority_is_rejected_end_to_end(pqc_client, pqc_operator, pqc_world, clock):
    s = sink(pqc_client, pqc_world, clock)
    s.emit(make_obs(clock, device_id="DEVICE-002"))
    assert pqc_operator.get("/api/v1/observations").json() == []
    assert len(s._queue) == 0                            # 4xx: dropped, not retried forever


def test_vision_signing_path_has_no_database_or_web_framework_imports():
    code = ("import sys, ai.vision.signed_sink, ai.vision.pipeline\n"
            "print([m for m in ('fastapi','sqlite3','starlette','backend.devices','backend.api','backend.security.credentials',"
            "'backend.security.pqc_gateway','torch','ultralytics','cv2') if m in sys.modules])\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[]", r.stdout


def test_provisioning_scripts_and_gateway_startup(tmp_path, pqc_backend):
    env = {**os.environ, "KEYS_DIR": str(tmp_path / "keys"), "DATABASE_URL": f"sqlite:///{(tmp_path / 'q.db').as_posix()}",
           "PYTHONPATH": str(ROOT)}
    for k in ("QSHIELD_MASTER_KEY_HEX",):
        env.pop(k, None)

    def run(*args):
        r = subprocess.run([sys.executable, "scripts/pqc_provision.py", *args], cwd=ROOT, env=env,
                           capture_output=True, text=True)
        return r

    r = run("init-gateway")
    assert r.returncode == 0 and "fingerprint" in r.stdout
    assert run("init-gateway").returncode == 1                       # never overwrites
    r = run("enroll-signer", "vision-1", "--device", "DEVICE-001")
    assert r.returncode == 0
    assert run("enroll-signer", "vision-1", "--device", "DEVICE-001").returncode == 1
    listing = run("list").stdout
    assert "signer vision-1" in listing and "gateway-kem-1" in listing and "active" in listing
    pqc_dir = tmp_path / "keys" / "pqc"
    assert {p.name for p in pqc_dir.iterdir()} == {"gateway-kem-1.key.enc", "gateway-kem-1.pub.json",
                                                   "vision-1.key.enc", "vision-1.pub.json", "vision-1.kek"}
    # the vision service can unseal its key with ONLY its own KEK (no master key)
    from backend.security.keystore import load_kek_file
    PqcKeyStore(pqc_dir).load_private(pqc_backend, "vision-1", load_kek_file(pqc_dir / "vision-1.kek"))
    # gateway startup path loads the KEM key from the keystore using the master key
    from backend.config import Settings
    from backend.devices.store import Store
    from backend.main import build_pqc
    st = Settings(db_path=str(tmp_path / "q.db"), keys_dir=str(tmp_path / "keys"), pqc_enabled=True)
    gw = build_pqc(st, Store(st.db_path))
    assert gw.gateway_public_key().key_id == "gateway-kem-1"
    assert run("retire-signer", "vision-1", "--revoke").returncode == 0
    assert Store(st.db_path).get_signer("vision-1").status == "revoked"
    assert run("retire-signer", "nobody").returncode == 1
    assert "PQC" not in run("list").stderr


def test_gateway_refuses_to_start_pqc_without_keys(tmp_path):
    from backend.config import Settings
    from backend.devices.store import Store
    from backend.main import build_pqc
    from backend.security.keystore import KeystoreError
    st = Settings(db_path=":memory:", keys_dir=str(tmp_path / "keys"), pqc_enabled=True,
                  master_key_hex="ab" * 32)
    with pytest.raises(KeystoreError):
        build_pqc(st, Store(":memory:"))
    assert build_pqc(Settings(db_path=":memory:", pqc_enabled=False), Store(":memory:")) is None
