"""PQC abstraction for the laptop gateway and the vision service (ML-KEM key establishment,
ML-DSA signatures).

Nothing else in the codebase imports a PQC library directly. ESP32 devices do not use this
module: they authenticate with provisioned HMAC-SHA256 (backend/protocol/envelope.py), which
is not post-quantum.

Error contract:
  * kem_encapsulate / kem_decapsulate / sign raise PqcError for malformed inputs (wrong
    lengths, wrong types, invalid keys). ML-KEM decapsulation of a well-formed but
    corrupted ciphertext does NOT raise (implicit rejection, FIPS 203): it returns a
    different secret, so callers must confirm the secret (see security/session.py).
  * verify never raises; it returns True only for a valid signature.
"""
from __future__ import annotations

import importlib
import importlib.metadata
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class KemKeyPair:
    public_key: bytes
    secret_key: bytes  # never log


@dataclass(frozen=True)
class SigKeyPair:
    public_key: bytes
    secret_key: bytes  # never log


class PqcError(Exception):
    pass


class PqcBackend(ABC):
    """Interface: swap the implementation without touching callers."""

    kem_algorithm: str
    sig_algorithm: str

    @abstractmethod
    def kem_keygen(self) -> KemKeyPair: ...

    @abstractmethod
    def kem_encapsulate(self, public_key: bytes) -> tuple[bytes, bytes]:
        """Return (ciphertext, shared_secret). Raises PqcError on an invalid public key."""

    @abstractmethod
    def kem_decapsulate(self, secret_key: bytes, ciphertext: bytes) -> bytes:
        """Return shared_secret (implicit rejection on corrupted ciphertext, see module doc)."""

    @abstractmethod
    def sig_keygen(self) -> SigKeyPair: ...

    @abstractmethod
    def sign(self, secret_key: bytes, message: bytes, context: bytes = b"") -> bytes:
        """ML-DSA signature. `context` (<=255 bytes) is the FIPS 204 context string, used
        for domain separation: a signature made for one context fails under another."""

    @abstractmethod
    def verify(self, public_key: bytes, message: bytes, signature: bytes, context: bytes = b"") -> bool:
        """True only if the signature verifies. Never raises on a bad signature."""

    @abstractmethod
    def info(self) -> dict:
        """Library name/version, algorithms and sizes (for records and benchmarks)."""


_KEM_MODULES = {"ML-KEM-512": "ml_kem_512", "ML-KEM-768": "ml_kem_768", "ML-KEM-1024": "ml_kem_1024"}
_SIG_MODULES = {"ML-DSA-44": "ml_dsa_44", "ML-DSA-65": "ml_dsa_65", "ML-DSA-87": "ml_dsa_87"}


class PqcryptoBackend(PqcBackend):
    """Backend using the `pqcrypto` package (see pqc/README.md for the selection record)."""

    def __init__(self, kem_algorithm: str = "ML-KEM-768", sig_algorithm: str = "ML-DSA-65"):
        if kem_algorithm not in _KEM_MODULES:
            raise PqcError(f"unsupported KEM algorithm: {kem_algorithm}")
        if sig_algorithm not in _SIG_MODULES:
            raise PqcError(f"unsupported signature algorithm: {sig_algorithm}")
        self.kem_algorithm = kem_algorithm
        self.sig_algorithm = sig_algorithm
        self._kem = importlib.import_module(f"pqcrypto.kem.{_KEM_MODULES[kem_algorithm]}")
        self._sig = importlib.import_module(f"pqcrypto.sign.{_SIG_MODULES[sig_algorithm]}")

    def kem_keygen(self) -> KemKeyPair:
        pk, sk = self._kem.keygen()
        return KemKeyPair(bytes(pk), bytes(sk))

    def kem_encapsulate(self, public_key: bytes) -> tuple[bytes, bytes]:
        try:
            ct, ss = self._kem.encaps(public_key)
        except (ValueError, TypeError) as e:
            raise PqcError(f"encapsulation failed: {e}") from None
        return bytes(ct), bytes(ss)

    def kem_decapsulate(self, secret_key: bytes, ciphertext: bytes) -> bytes:
        try:
            return bytes(self._kem.decaps(secret_key, ciphertext))
        except (ValueError, TypeError) as e:
            raise PqcError(f"decapsulation failed: {e}") from None

    def sig_keygen(self) -> SigKeyPair:
        pk, sk = self._sig.keygen()
        return SigKeyPair(bytes(pk), bytes(sk))

    def sign(self, secret_key: bytes, message: bytes, context: bytes = b"") -> bytes:
        try:
            return bytes(self._sig.sign(secret_key, message, context=context))
        except (ValueError, TypeError) as e:
            raise PqcError(f"signing failed: {e}") from None

    def verify(self, public_key: bytes, message: bytes, signature: bytes, context: bytes = b"") -> bool:
        # The library returns None on success and raises on failure. Any exception (bad
        # signature, wrong length, malformed key, wrong type) is a rejection.
        try:
            self._sig.verify(public_key, message, signature, context=context)
        except Exception:
            return False
        return True

    def info(self) -> dict:
        return {
            "library": "pqcrypto", "library_version": importlib.metadata.version("pqcrypto"),
            "kem_algorithm": self.kem_algorithm, "sig_algorithm": self.sig_algorithm,
            "sizes_bytes": {
                "kem_public_key": self._kem.PUBLIC_KEY_SIZE, "kem_secret_key": self._kem.SECRET_KEY_SIZE,
                "kem_ciphertext": self._kem.CIPHERTEXT_SIZE, "kem_shared_secret": self._kem.SHARED_SECRET_SIZE,
                "sig_public_key": self._sig.PUBLIC_KEY_SIZE, "sig_secret_key": self._sig.SECRET_KEY_SIZE,
                "signature": self._sig.SIGNATURE_SIZE,
            },
        }


def get_backend(kem_algorithm: str = "ML-KEM-768", sig_algorithm: str = "ML-DSA-65") -> PqcBackend:
    return PqcryptoBackend(kem_algorithm, sig_algorithm)
