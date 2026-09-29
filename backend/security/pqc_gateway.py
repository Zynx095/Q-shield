"""Gateway-side PQC service: verifies signed observations and terminates ML-KEM sessions.

Verification order for a signed observation (each failure has a distinct reason code that is
logged as a security event; the HTTP response never reveals which check failed):
  1 protocol version, 2 algorithm, 3 signer known and active, 4 signature over the canonical
  signed bytes, 5 freshness of the signed timestamp, 6 payload parses as an Observation,
  7 metadata bound to payload (observation_id, source) and signer authorised for that device
  and source, 8 replay (observation_id already stored).
The signature is verified BEFORE the payload is parsed or any timestamp is trusted.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import ValidationError

from backend.devices.store import SignerRecord, Store
from backend.protocol.observation import Observation
from backend.protocol.signed_observation import (
    CONTEXT, PROTOCOL_VERSION, SignedObservationEnvelope, decode_signature, parse_iso, signing_bytes,
)
from backend.security.keystore import KIND_KEM, PqcKeyStore, PublicKeyRecord, kem_kek
from backend.security.pqc import PqcBackend
from backend.security.session import (
    HandshakeInit, HandshakeResponse, SealedMessage, SecureChannel, SessionError, server_accept,
)


class PqcRejection(Exception):
    def __init__(self, reason: str, severity: str = "high", status: int = 401, device_id: str | None = None):
        super().__init__(reason)
        self.reason, self.severity, self.status = reason, severity, status
        self.device_id = device_id     # set only when the payload was parsed after signature verification


@dataclass
class _Session:
    channel: SecureChannel
    signer_id: str


class PqcGateway:
    def __init__(self, store: Store, backend: PqcBackend, kem_keys: dict[str, tuple[PublicKeyRecord, bytes]],
                 active_kem_id: str, clock=time.time, max_skew_s: float = 300.0, session_ttl_s: int = 3600,
                 max_sessions: int = 64):
        if active_kem_id not in kem_keys:
            raise ValueError("active KEM key not loaded")
        self.store, self.backend, self._kem, self.active_kem_id = store, backend, kem_keys, active_kem_id
        self._clock, self.max_skew_s, self.session_ttl_s, self.max_sessions = clock, max_skew_s, session_ttl_s, max_sessions
        self._sessions: dict[str, _Session] = {}
        self._seen_nonces: dict[str, float] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_keystore(cls, store: Store, backend: PqcBackend, keystore: PqcKeyStore, master_key: bytes,
                      kem_key_ids: list[str], **kw) -> "PqcGateway":
        """Load the gateway KEM key(s); the first id is active for new sessions. Extra ids stay loaded
        so sessions/clients pinned to a previous key keep working until it is removed."""
        keys = {}
        for kid in kem_key_ids:
            rec, sk = keystore.load_private(backend, kid, kem_kek(master_key, kid))
            if rec.kind != KIND_KEM:
                raise ValueError(f"{kid} is not a KEM key")
            keys[kid] = (rec, sk)
        return cls(store, backend, keys, kem_key_ids[0], **kw)

    def _now(self) -> datetime:
        return datetime.fromtimestamp(self._clock(), timezone.utc)

    def gateway_public_key(self) -> PublicKeyRecord:
        return self._kem[self.active_kem_id][0]

    # ---------------- signed observations ----------------
    def _signer(self, signer_id: str) -> SignerRecord:
        s = self.store.get_signer(signer_id)
        if s is None:
            raise PqcRejection("unknown_signer")
        if s.status != "active":
            raise PqcRejection(f"signer_{s.status}")
        return s

    def verify_signed_observation(self, env: SignedObservationEnvelope, *, expected_signer: str | None = None
                                  ) -> tuple[Observation, SignerRecord]:
        if env.protocol_version != PROTOCOL_VERSION:
            raise PqcRejection("unsupported_protocol_version", "low")
        if env.algorithm != self.backend.sig_algorithm:
            raise PqcRejection("unsupported_algorithm", "low")
        signer = self._signer(env.signer_id)
        if signer.algorithm != env.algorithm:
            raise PqcRejection("signer_algorithm_mismatch")
        if expected_signer is not None and env.signer_id != expected_signer:
            raise PqcRejection("signer_session_mismatch")
        try:
            sig = decode_signature(env.signature)
        except ValueError:
            raise PqcRejection("malformed_signature") from None
        if not self.backend.verify(signer.public_key, signing_bytes(env), sig, CONTEXT):
            raise PqcRejection("invalid_signature")

        try:
            ts = parse_iso(env.timestamp)
        except ValueError:
            raise PqcRejection("malformed_timestamp", "low") from None
        skew = (self._now() - ts).total_seconds()
        if abs(skew) > self.max_skew_s:
            raise PqcRejection("stale_timestamp" if skew > 0 else "future_timestamp", "medium")

        try:
            obs = Observation.model_validate_json(env.payload)
        except ValidationError:
            raise PqcRejection("malformed_payload", "medium", 422) from None
        if obs.observation_id != env.observation_id or env.source_id.split(":")[0] != obs.source.value:
            raise PqcRejection("payload_metadata_mismatch", "high", device_id=obs.device_id)
        if env.source_id.split(":")[0] != signer.source or obs.device_id not in signer.allowed_devices:
            raise PqcRejection("signer_not_authorised", "high", device_id=obs.device_id)
        return obs, signer

    # ---------------- ML-KEM sessions ----------------
    def establish_session(self, init: HandshakeInit) -> HandshakeResponse:
        now = self._clock()
        if init.gateway_key_id not in self._kem:
            raise PqcRejection("unknown_gateway_key", "low")
        signer = self._signer(init.signer_id)
        if signer.algorithm != init.sig_algorithm:
            raise PqcRejection("signer_algorithm_mismatch")
        with self._lock:
            self._seen_nonces = {n: t for n, t in self._seen_nonces.items() if t > now}
            self._sessions = {k: s for k, s in self._sessions.items() if s.channel.expires_at > now}
            if len(self._sessions) >= self.max_sessions:
                raise PqcRejection("too_many_sessions", "low", 503)
            if init.client_nonce in self._seen_nonces:
                raise PqcRejection("handshake_replay")
        try:
            resp, channel = server_accept(self.backend, init, self._kem[init.gateway_key_id][1], signer.public_key,
                                          self._now(), self.max_skew_s, self.session_ttl_s, self._clock)
        except SessionError as e:
            raise PqcRejection(f"handshake_{e.reason}") from None
        with self._lock:
            self._seen_nonces[init.client_nonce] = now + 2 * self.max_skew_s
            self._sessions[resp.session_id] = _Session(channel, signer.signer_id)
        return resp

    def open_secure(self, msg: SealedMessage) -> tuple[SignedObservationEnvelope, str]:
        """Decrypt a sealed message; returns the inner signed envelope and the session's signer id."""
        with self._lock:
            sess = self._sessions.get(msg.session_id)
        if sess is None:
            raise PqcRejection("unknown_session")
        import base64
        import binascii
        try:
            ct = base64.b64decode(msg.ciphertext, validate=True)
        except (binascii.Error, ValueError):
            raise PqcRejection("malformed_ciphertext", "low", 422) from None
        try:
            plaintext = sess.channel.open(msg.counter, ct)
        except SessionError as e:
            raise PqcRejection(f"session_{e.reason}") from None
        try:
            return SignedObservationEnvelope.model_validate_json(plaintext), sess.signer_id
        except ValidationError:
            raise PqcRejection("malformed_envelope", "medium", 422) from None
