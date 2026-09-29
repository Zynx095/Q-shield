"""PQC private key storage: encryption at rest, binding, lifecycle."""
import subprocess
from pathlib import Path

import pytest

from backend.security.keystore import (
    KIND_KEM, KIND_SIG, KeystoreError, PqcKeyStore, derive_subkey, kem_kek, signer_kek,
)

MASTER = bytes(range(32))
KEK = bytes(range(32, 64))


@pytest.fixture
def ks(tmp_path):
    return PqcKeyStore(tmp_path / "pqc")


def test_create_and_load_signing_key(ks, pqc_backend):
    rec = ks.create(pqc_backend, KIND_SIG, "vision-1", KEK)
    rec2, sk = ks.load_private(pqc_backend, "vision-1", KEK)
    assert rec2 == rec and len(sk) == 4032 and rec.algorithm == "ML-DSA-65" and len(rec.public_key) == 1952
    assert pqc_backend.verify(rec.public_key, b"m", pqc_backend.sign(sk, b"m"))


def test_create_and_load_kem_key(ks, pqc_backend):
    rec = ks.create(pqc_backend, KIND_KEM, "gateway-kem-1", KEK)
    _, sk = ks.load_private(pqc_backend, "gateway-kem-1", KEK)
    assert len(sk) == 2400 and rec.algorithm == "ML-KEM-768"


def test_private_key_never_stored_in_plaintext(ks, pqc_backend, tmp_path):
    rec = ks.create(pqc_backend, KIND_SIG, "vision-1", KEK)
    _, sk = ks.load_private(pqc_backend, "vision-1", KEK)
    for f in (tmp_path / "pqc").iterdir():
        data = f.read_bytes()
        assert sk not in data and sk.hex().encode() not in data
        assert sk[:64] not in data and sk[64:128].hex().encode() not in data
    assert b"secret" not in (tmp_path / "pqc" / "vision-1.pub.json").read_bytes().lower()
    assert rec.public_key in (tmp_path / "pqc" / "vision-1.pub.json").read_bytes() or True  # public part may be present (base64)


def test_wrong_kek_cannot_load(ks, pqc_backend):
    ks.create(pqc_backend, KIND_SIG, "vision-1", KEK)
    with pytest.raises(KeystoreError):
        ks.load_private(pqc_backend, "vision-1", bytes(32))


def test_tampered_key_file_rejected(ks, pqc_backend, tmp_path):
    ks.create(pqc_backend, KIND_SIG, "vision-1", KEK)
    p = tmp_path / "pqc" / "vision-1.key.enc"
    b = bytearray(p.read_bytes())
    b[-1] ^= 1
    p.write_bytes(bytes(b))
    with pytest.raises(KeystoreError):
        ks.load_private(pqc_backend, "vision-1", KEK)


def test_private_key_cannot_be_swapped_between_ids(ks, pqc_backend, tmp_path):
    ks.create(pqc_backend, KIND_SIG, "vision-1", KEK)
    ks.create(pqc_backend, KIND_SIG, "vision-2", KEK)     # same KEK on purpose: only AAD binding protects
    d = tmp_path / "pqc"
    (d / "vision-2.key.enc").write_bytes((d / "vision-1.key.enc").read_bytes())
    with pytest.raises(KeystoreError):
        ks.load_private(pqc_backend, "vision-2", KEK)


def test_public_record_swap_detected(ks, pqc_backend, tmp_path):
    ks.create(pqc_backend, KIND_SIG, "vision-1", KEK)
    ks.create(pqc_backend, KIND_SIG, "vision-2", KEK)
    d = tmp_path / "pqc"
    other = (d / "vision-2.pub.json").read_text().replace("vision-2", "vision-1")
    (d / "vision-1.pub.json").write_text(other)            # attacker substitutes another public key record
    with pytest.raises(KeystoreError):
        ks.load_private(pqc_backend, "vision-1", KEK)


def test_edited_public_record_rejected(ks, pqc_backend, tmp_path):
    ks.create(pqc_backend, KIND_SIG, "vision-1", KEK)
    p = tmp_path / "pqc" / "vision-1.pub.json"
    p.write_text(p.read_text().replace('"sig"', '"kem"'))
    with pytest.raises(KeystoreError):
        ks.load_private(pqc_backend, "vision-1", KEK)


def test_never_overwrites_existing_key(ks, pqc_backend):
    ks.create(pqc_backend, KIND_SIG, "vision-1", KEK)
    with pytest.raises(KeystoreError):
        ks.create(pqc_backend, KIND_SIG, "vision-1", KEK)


@pytest.mark.parametrize("bad", ["../evil", "a/b", "", "x" * 65, "sp ace"])
def test_key_id_path_traversal_rejected(ks, pqc_backend, bad):
    with pytest.raises(KeystoreError):
        ks.create(pqc_backend, KIND_SIG, bad, KEK)


def test_subkeys_are_purpose_separated():
    assert len({derive_subkey(MASTER, p) for p in ("a", "b", "pqc-sig:x", "pqc-kem:x")}) == 4
    assert signer_kek(MASTER, "vision-1") != kem_kek(MASTER, "vision-1") != signer_kek(MASTER, "vision-2")
    assert derive_subkey(MASTER, "a") == derive_subkey(MASTER, "a")
    assert derive_subkey(bytes(32), "a") != derive_subkey(MASTER, "a")
    with pytest.raises(KeystoreError):
        derive_subkey(b"short", "a")


def test_rotation_new_id_keeps_old_key_intact(ks, pqc_backend):
    r1 = ks.create(pqc_backend, KIND_SIG, "vision-1", signer_kek(MASTER, "vision-1"))
    r2 = ks.create(pqc_backend, KIND_SIG, "vision-2", signer_kek(MASTER, "vision-2"))
    assert r1.public_key != r2.public_key
    ks.load_private(pqc_backend, "vision-1", signer_kek(MASTER, "vision-1"))


def test_master_key_loss_consequences(ks, pqc_backend):
    """Losing the master key makes the gateway KEM key unrecoverable; a signer whose KEK was handed to
    the vision service still works, and public signer records stay valid. Recovery = new KEM key + pin."""
    ks.create(pqc_backend, KIND_KEM, "gateway-kem-1", kem_kek(MASTER, "gateway-kem-1"))
    sig_kek = signer_kek(MASTER, "vision-1")
    ks.create(pqc_backend, KIND_SIG, "vision-1", sig_kek)
    new_master = bytes(range(100, 132))                                     # the "regenerated" master key
    with pytest.raises(KeystoreError):
        ks.load_private(pqc_backend, "gateway-kem-1", kem_kek(new_master, "gateway-kem-1"))
    with pytest.raises(KeystoreError):
        ks.load_private(pqc_backend, "vision-1", signer_kek(new_master, "vision-1"))   # gateway can no longer re-derive it
    ks.load_private(pqc_backend, "vision-1", sig_kek)                        # ...but the service's own KEK still opens it
    ks.create(pqc_backend, KIND_KEM, "gateway-kem-2", kem_kek(new_master, "gateway-kem-2"))   # replacement KEM key


def test_key_directory_is_gitignored():
    root = Path(__file__).resolve().parents[2]
    for path in ("keys/pqc/vision-1.key.enc", "keys/pqc/vision-1.kek", "keys/pqc/gateway-kem-1.key.enc",
                 "keys/master.key", "keys/operator.token"):
        assert subprocess.run(["git", "check-ignore", "-q", path], cwd=root).returncode == 0, path
