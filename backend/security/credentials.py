"""Credential-store boundary for per-device HMAC secrets.

HMAC secrets cannot be hashed (the gateway needs them to recompute tags), so they are
stored encrypted with AES-256-GCM under a local master key. The device_id is bound as
associated data, so a ciphertext copied to another device's row fails to decrypt.

Threat model (prototype):
  Protects against: a leaked/backed-up/committed SQLite file on its own; read-only access
  to the DB by a component that does not have the master key.
  Does NOT protect against: an attacker who can read both the DB and the master key
  (same host, same user); a compromised gateway process (secrets are in memory while
  running); loss of the master key (all device secrets become unrecoverable and every
  device must be re-provisioned). The master key is a file (or env var), not an HSM/TPM.
"""
from __future__ import annotations

import os
import secrets
import time
from abc import ABC, abstractmethod
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.devices.store import Store
from backend.security.fileutil import write_private_file

MASTER_KEY_BYTES = 32
_FORMAT_V1 = b"\x01"  # blob = version(1) || nonce(12) || ciphertext+tag


class CredentialError(Exception):
    pass


class CredentialStore(ABC):
    """Everything that touches device secrets goes through this interface."""

    @abstractmethod
    def put(self, device_id: str, secret: bytes) -> None: ...

    @abstractmethod
    def get(self, device_id: str) -> bytes | None:
        """Return the secret, or None if absent. Raises CredentialError if the stored
        credential cannot be decrypted (wrong master key or tampered/moved ciphertext)."""

    @abstractmethod
    def delete(self, device_id: str) -> None: ...


def _aad(device_id: str) -> bytes:
    return b"qshield-device-credential-v1:" + device_id.encode("utf-8")


class EncryptedCredentialStore(CredentialStore):
    def __init__(self, store: Store, master_key: bytes, clock=time.time):
        if len(master_key) != MASTER_KEY_BYTES:
            raise CredentialError("master key must be 32 bytes")
        self._store = store
        self._aead = AESGCM(master_key)
        self._clock = clock

    def put(self, device_id: str, secret: bytes) -> None:
        nonce = os.urandom(12)  # random 96-bit nonce, fresh for every write
        ct = self._aead.encrypt(nonce, secret, _aad(device_id))
        self._store.put_credential_blob(device_id, _FORMAT_V1 + nonce + ct, self._clock())

    def get(self, device_id: str) -> bytes | None:
        blob = self._store.get_credential_blob(device_id)
        if blob is None:
            return None
        if blob[:1] != _FORMAT_V1 or len(blob) < 1 + 12 + 16:
            raise CredentialError("unrecognised credential format")
        try:
            return self._aead.decrypt(blob[1:13], blob[13:], _aad(device_id))
        except InvalidTag:
            raise CredentialError("credential cannot be decrypted (wrong master key or tampered)") from None

    def delete(self, device_id: str) -> None:
        self._store.delete_credential_blob(device_id)


def load_or_create_master_key(keys_dir: str | Path, env_hex: str | None = None) -> bytes:
    """QSHIELD_MASTER_KEY_HEX (64 hex chars) wins; otherwise keys/master.key, created on
    first use with 32 random bytes. Never logged. On Windows the file inherits the
    directory ACL (POSIX modes do not apply), so keep keys/ in a private location."""
    if env_hex:
        try:
            key = bytes.fromhex(env_hex.strip())
        except ValueError:
            raise CredentialError("QSHIELD_MASTER_KEY_HEX is not valid hex") from None
        if len(key) != MASTER_KEY_BYTES:
            raise CredentialError("QSHIELD_MASTER_KEY_HEX must be 64 hex characters")
        return key
    path = Path(keys_dir) / "master.key"
    if not path.exists():
        try:
            write_private_file(path, secrets.token_bytes(MASTER_KEY_BYTES).hex().encode() + b"\n")
        except FileExistsError:
            pass  # lost a creation race; read what the winner wrote
    try:
        key = bytes.fromhex(path.read_text().strip())
    except ValueError:
        raise CredentialError(f"{path} is corrupt") from None
    if len(key) != MASTER_KEY_BYTES:
        raise CredentialError(f"{path} is corrupt (expected 32 bytes hex)")
    return key
