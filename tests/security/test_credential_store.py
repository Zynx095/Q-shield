import sqlite3

import pytest

from backend.devices.store import Store
from backend.protocol.envelope import build_hmac_envelope
from backend.security.credentials import (
    CredentialError, EncryptedCredentialStore, load_or_create_master_key,
)

KEY = bytes(range(32))
SECRET = bytes.fromhex("aa" * 32)


def test_roundtrip_and_absent():
    s = Store(":memory:")
    c = EncryptedCredentialStore(s, KEY)
    assert c.get("D1") is None
    c.put("D1", SECRET)
    assert c.get("D1") == SECRET
    c.delete("D1")
    assert c.get("D1") is None


def test_plaintext_not_in_database_file(tmp_path):
    db = tmp_path / "q.db"
    s = Store(str(db))
    EncryptedCredentialStore(s, KEY).put("D1", SECRET)
    s.close()
    raw = db.read_bytes()
    assert SECRET not in raw and SECRET.hex().encode() not in raw
    cols = [r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(devices)")]
    assert "secret" not in cols


def test_wrong_master_key_cannot_decrypt():
    s = Store(":memory:")
    EncryptedCredentialStore(s, KEY).put("D1", SECRET)
    with pytest.raises(CredentialError):
        EncryptedCredentialStore(s, bytes(32)).get("D1")


def test_ciphertext_bound_to_device_id():
    s = Store(":memory:")
    c = EncryptedCredentialStore(s, KEY)
    c.put("D1", SECRET)
    s.put_credential_blob("D2", s.get_credential_blob("D1"), 0.0)  # attacker copies D1's blob to D2
    with pytest.raises(CredentialError):
        c.get("D2")


def test_tampered_blob_rejected():
    s = Store(":memory:")
    c = EncryptedCredentialStore(s, KEY)
    c.put("D1", SECRET)
    blob = bytearray(s.get_credential_blob("D1"))
    blob[-1] ^= 1
    s.put_credential_blob("D1", bytes(blob), 0.0)
    with pytest.raises(CredentialError):
        c.get("D1")


def test_nonce_differs_between_writes():
    s = Store(":memory:")
    c = EncryptedCredentialStore(s, KEY)
    c.put("D1", SECRET)
    a = s.get_credential_blob("D1")
    c.put("D1", SECRET)
    assert a != s.get_credential_blob("D1")


def test_bad_master_key_length():
    with pytest.raises(CredentialError):
        EncryptedCredentialStore(Store(":memory:"), b"short")


def test_master_key_created_once_and_reused(tmp_path):
    k1 = load_or_create_master_key(tmp_path)
    assert len(k1) == 32 and (tmp_path / "master.key").exists()
    assert load_or_create_master_key(tmp_path) == k1


def test_master_key_env_override_and_validation(tmp_path):
    assert load_or_create_master_key(tmp_path, "ab" * 32) == bytes.fromhex("ab" * 32)
    assert not (tmp_path / "master.key").exists()
    with pytest.raises(CredentialError):
        load_or_create_master_key(tmp_path, "abcd")
    with pytest.raises(CredentialError):
        load_or_create_master_key(tmp_path, "zz" * 32)


def test_corrupt_master_key_file_refused(tmp_path):
    (tmp_path / "master.key").write_text("not hex")
    with pytest.raises(CredentialError):
        load_or_create_master_key(tmp_path)


def test_device_auth_fails_closed_when_credential_unreadable(client, store, device_secret):
    store.put_credential_blob("DEVICE-001", b"\x01" + b"\x00" * 40, 0.0)  # corrupt it
    env = build_hmac_envelope(device_secret, "heartbeat", "DEVICE-001", 1, '{"uptime_ms":1}')
    assert client.post("/api/v1/heartbeat", json=env).status_code == 401
    assert client.get("/api/v1/events").json()[0]["event_type"] == "credential_unreadable"
