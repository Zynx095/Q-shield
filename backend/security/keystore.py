"""PQC key files: encrypted private keys + public key records.

Layout (all under keys/pqc/, which is gitignored):
    <key_id>.pub.json   public record: key_id, kind (sig|kem), algorithm, public_key (base64),
                        SHA-256 fingerprint, created_at. Not secret.
    <key_id>.key.enc    private key sealed with AES-256-GCM under a key-encryption key (KEK).
    <key_id>.kek        (signer keys only) the KEK, when provisioned to a separate component.

KEKs are HKDF-SHA256 subkeys of the gateway master key with a per-purpose label, so:
  * the gateway derives what it needs from the master key;
  * the vision service is handed only ITS OWN signer KEK, never the master key, so it cannot
    decrypt device credentials or the gateway KEM key.
The sealed blob is bound (AES-GCM associated data) to kind/algorithm/key_id/fingerprint, so a
private key cannot be swapped under a different record. On load the pair is self-tested
(sign/verify or encapsulate/decapsulate) to catch mismatched or corrupt files.

Limits: on one host under one OS account this is separation by file access only; anyone who can
read keys/ (master.key, *.kek) can decrypt everything. Not an HSM/TPM. No automatic rotation.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from backend.security.fileutil import write_private_file
from backend.security.pqc import PqcBackend

_MAGIC = b"QSK1"
_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
KIND_SIG, KIND_KEM = "sig", "kem"


class KeystoreError(Exception):
    pass


def derive_subkey(master_key: bytes, purpose: str) -> bytes:
    """HKDF-SHA256 subkey for one purpose (domain-separated by the info label)."""
    if len(master_key) != 32:
        raise KeystoreError("master key must be 32 bytes")
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=b"qshield-subkey-v1:" + purpose.encode("utf-8")).derive(master_key)


def signer_kek(master_key: bytes, key_id: str) -> bytes:
    return derive_subkey(master_key, f"pqc-sig:{key_id}")


def kem_kek(master_key: bytes, key_id: str) -> bytes:
    return derive_subkey(master_key, f"pqc-kem:{key_id}")


def _check_id(key_id: str) -> str:
    if not _ID.match(key_id):
        raise KeystoreError(f"invalid key id {key_id!r}")
    return key_id


def fingerprint(public_key: bytes) -> str:
    return hashlib.sha256(public_key).hexdigest()


@dataclass(frozen=True)
class PublicKeyRecord:
    key_id: str
    kind: str
    algorithm: str
    public_key: bytes
    created_at: str

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.public_key)

    def to_json(self) -> str:
        return json.dumps({"key_id": self.key_id, "kind": self.kind, "algorithm": self.algorithm,
                           "public_key": base64.b64encode(self.public_key).decode(),
                           "fingerprint_sha256": self.fingerprint, "created_at": self.created_at}, indent=1)

    @classmethod
    def from_json(cls, text: str) -> "PublicKeyRecord":
        try:
            d = json.loads(text)
            rec = cls(_check_id(d["key_id"]), d["kind"], d["algorithm"],
                      base64.b64decode(d["public_key"], validate=True), d["created_at"])
            if rec.kind not in (KIND_SIG, KIND_KEM) or rec.fingerprint != d["fingerprint_sha256"]:
                raise KeystoreError("public key record inconsistent")
            return rec
        except (KeyError, ValueError, TypeError) as e:
            raise KeystoreError(f"malformed public key record: {e}") from None


def _aad(rec: PublicKeyRecord) -> bytes:
    return f"qshield-pqc-key-v1:{rec.kind}:{rec.algorithm}:{rec.key_id}:{rec.fingerprint}".encode()


def _seal(kek: bytes, secret: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(12)
    return _MAGIC + nonce + AESGCM(kek).encrypt(nonce, secret, aad)


def _open(kek: bytes, blob: bytes, aad: bytes) -> bytes:
    if blob[:4] != _MAGIC or len(blob) < 4 + 12 + 16:
        raise KeystoreError("unrecognised key file format")
    try:
        return AESGCM(kek).decrypt(blob[4:16], blob[16:], aad)
    except InvalidTag:
        raise KeystoreError("private key cannot be decrypted (wrong key-encryption key, or file tampered/swapped)") from None


class PqcKeyStore:
    def __init__(self, directory: str | Path):
        self.dir = Path(directory)

    def _paths(self, key_id: str) -> tuple[Path, Path]:
        _check_id(key_id)
        return self.dir / f"{key_id}.pub.json", self.dir / f"{key_id}.key.enc"

    def exists(self, key_id: str) -> bool:
        pub, enc = self._paths(key_id)
        return pub.exists() or enc.exists()

    def create(self, backend: PqcBackend, kind: str, key_id: str, kek: bytes) -> PublicKeyRecord:
        """Generate and store a new keypair. Refuses to overwrite an existing key id."""
        pub, enc = self._paths(key_id)
        if self.exists(key_id):
            raise KeystoreError(f"key {key_id!r} already exists; choose a new id to rotate")
        if kind == KIND_SIG:
            kp, alg = backend.sig_keygen(), backend.sig_algorithm
        elif kind == KIND_KEM:
            kp, alg = backend.kem_keygen(), backend.kem_algorithm
        else:
            raise KeystoreError(f"unknown key kind {kind!r}")
        rec = PublicKeyRecord(key_id, kind, alg, kp.public_key, datetime.now(timezone.utc).isoformat(timespec="seconds"))
        write_private_file(enc, _seal(kek, kp.secret_key, _aad(rec)))
        write_private_file(pub, rec.to_json().encode())
        return rec

    def load_public(self, key_id: str) -> PublicKeyRecord:
        pub, _ = self._paths(key_id)
        try:
            return PublicKeyRecord.from_json(pub.read_text())
        except OSError as e:
            raise KeystoreError(f"cannot read public key record for {key_id!r}: {e}") from None

    def load_private(self, backend: PqcBackend, key_id: str, kek: bytes) -> tuple[PublicKeyRecord, bytes]:
        """Decrypt and self-test a private key. Returns (public record, secret key). The secret
        must be kept in memory only and never logged."""
        rec = self.load_public(key_id)
        _, enc = self._paths(key_id)
        try:
            secret = _open(kek, enc.read_bytes(), _aad(rec))
        except OSError as e:
            raise KeystoreError(f"cannot read private key file for {key_id!r}: {e}") from None
        if rec.kind == KIND_SIG and rec.algorithm == backend.sig_algorithm:
            probe = b"qshield-selftest"
            if not backend.verify(rec.public_key, probe, backend.sign(secret, probe, b"selftest"), b"selftest"):
                raise KeystoreError(f"key {key_id!r}: private and public key do not match")
        elif rec.kind == KIND_KEM and rec.algorithm == backend.kem_algorithm:
            ct, ss = backend.kem_encapsulate(rec.public_key)
            if backend.kem_decapsulate(secret, ct) != ss:
                raise KeystoreError(f"key {key_id!r}: private and public key do not match")
        else:
            raise KeystoreError(f"key {key_id!r} algorithm {rec.algorithm} does not match the configured backend")
        return rec, secret


def load_kek_file(path: str | Path) -> bytes:
    try:
        kek = bytes.fromhex(Path(path).read_text().strip())
    except (OSError, ValueError) as e:
        raise KeystoreError(f"cannot read key-encryption key {path}: {e}") from None
    if len(kek) != 32:
        raise KeystoreError(f"{path}: key-encryption key must be 32 bytes")
    return kek
