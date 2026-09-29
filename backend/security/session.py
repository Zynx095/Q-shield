"""ML-KEM-768 session establishment + AES-256-GCM protected messages.

Composition of standard primitives, NOT a vetted protocol (it is not TLS and has had no
external review). Prefer TLS with a hybrid/PQ key exchange if and when the platform offers it.

Handshake (vision service = client, gateway = server):
  client -> server  init = {signer_id, gateway_key_id, ciphertext = ML-KEM.Encaps(gateway_pk),
                            client_nonce, timestamp, signature = ML-DSA.Sign(client_key, fields)}
      The ML-DSA signature covers the ciphertext and every other field, so (a) the gateway knows
      WHICH enrolled component is establishing the session and (b) any change to the ciphertext
      in flight is rejected before decapsulation.
  server -> client  resp = {session_id, server_nonce, expires_in_s, confirm}
      confirm = HMAC-SHA256(k_confirm, transcript). Only a party that decapsulated to the same
      shared secret can compute it, so it proves the gateway holds the private key matching the
      pinned public key. A client that encapsulated to the WRONG public key (or a corrupted
      ciphertext, which ML-KEM "implicitly rejects" into an unrelated secret) sees a bad confirm.
Key schedule: HKDF-SHA256(ikm=shared_secret, salt=client_nonce||server_nonce,
              info="qshield-session-v1"||session_id||SHA256(init signing bytes)) -> 96 bytes:
              k_c2s | k_s2c | k_confirm.
Protected messages: AES-256-GCM, one key per direction, 96-bit nonce = 0x00000000||counter(8, BE),
strictly increasing per direction (replay/reorder rejected), AAD = session_id||direction||counter.

Not provided: forward secrecy for the gateway's static KEM key beyond ML-KEM's own properties
(compromise of the static KEM private key exposes recorded sessions' shared secrets), gateway
signatures (gateway authenticity rests on possession of the pinned KEM key), session resumption,
or response confidentiality (responses are plain status JSON).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import BaseModel, ConfigDict, Field

from backend.protocol.canonical import encode_fields
from backend.protocol.signed_observation import iso_utc, parse_iso
from backend.security.pqc import PqcBackend, PqcError

SESSION_VERSION = 1
INIT_DOMAIN = b"QSHIELD-SESSION-INIT"
INIT_CONTEXT = b"qshield/session-init/v1"
NONCE_BYTES = 32
SESSION_ID_BYTES = 16
MAX_COUNTER = 2**48


class SessionError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _b64d(s: str) -> bytes:
    try:
        return base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError):
        raise SessionError("malformed_base64") from None


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode()


class HandshakeInit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: int
    kem_algorithm: str = Field(max_length=32)
    sig_algorithm: str = Field(max_length=32)
    signer_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")
    gateway_key_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    ciphertext: str = Field(max_length=4096)
    client_nonce: str = Field(max_length=128)
    timestamp: str = Field(max_length=40)
    signature: str = Field(max_length=8192)


class HandshakeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    server_nonce: str
    expires_in_s: int
    confirm: str


class SealedMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(max_length=64)
    counter: int = Field(ge=1, lt=MAX_COUNTER)
    ciphertext: str = Field(max_length=65536)


def init_signing_bytes(i: HandshakeInit | dict) -> bytes:
    g = (lambda k: i[k]) if isinstance(i, dict) else (lambda k: getattr(i, k))
    return encode_fields(INIT_DOMAIN, [str(g("protocol_version")), g("kem_algorithm"), g("sig_algorithm"),
                                       g("signer_id"), g("gateway_key_id"), _b64d(g("ciphertext")),
                                       _b64d(g("client_nonce")), g("timestamp")])


@dataclass
class SessionKeys:
    c2s: bytes
    s2c: bytes
    confirm: bytes


def derive_keys(shared_secret: bytes, client_nonce: bytes, server_nonce: bytes, session_id: bytes,
                init_bytes: bytes) -> SessionKeys:
    okm = HKDF(algorithm=hashes.SHA256(), length=96, salt=client_nonce + server_nonce,
               info=b"qshield-session-v1" + session_id + hashlib.sha256(init_bytes).digest()).derive(shared_secret)
    return SessionKeys(okm[:32], okm[32:64], okm[64:])


def _confirm_tag(k_confirm: bytes, session_id: bytes, server_nonce: bytes, init_bytes: bytes) -> bytes:
    return hmac.new(k_confirm, b"server-finished" + session_id + server_nonce + hashlib.sha256(init_bytes).digest(),
                    hashlib.sha256).digest()


class SecureChannel:
    """Directional AES-256-GCM channel. `role` is 'client' or 'server'."""

    def __init__(self, role: str, session_id: bytes, keys: SessionKeys, expires_at: float,
                 clock=time.time):
        assert role in ("client", "server")
        self.role, self.session_id, self.expires_at, self._clock = role, session_id, expires_at, clock
        self._send_key, self._recv_key = (keys.c2s, keys.s2c) if role == "client" else (keys.s2c, keys.c2s)
        self._send_dir, self._recv_dir = (b"c2s", b"s2c") if role == "client" else (b"s2c", b"c2s")
        self._send_counter = 0
        self._recv_counter = 0
        self._lock = threading.Lock()

    @staticmethod
    def _nonce(counter: int) -> bytes:
        return b"\x00\x00\x00\x00" + counter.to_bytes(8, "big")

    def _aad(self, direction: bytes, counter: int) -> bytes:
        return self.session_id + direction + counter.to_bytes(8, "big")

    def seal(self, plaintext: bytes) -> tuple[int, bytes]:
        with self._lock:
            self._send_counter += 1
            c = self._send_counter
        if c >= MAX_COUNTER:
            raise SessionError("counter_exhausted")
        return c, AESGCM(self._send_key).encrypt(self._nonce(c), plaintext, self._aad(self._send_dir, c))

    def open(self, counter: int, ciphertext: bytes) -> bytes:
        if self._clock() >= self.expires_at:
            raise SessionError("session_expired")
        with self._lock:
            if counter <= self._recv_counter:
                raise SessionError("replayed_or_reordered_message")
            try:
                pt = AESGCM(self._recv_key).decrypt(self._nonce(counter), ciphertext,
                                                    self._aad(self._recv_dir, counter))
            except InvalidTag:
                raise SessionError("decryption_failed") from None
            self._recv_counter = counter  # advance only after authentication succeeds
        return pt


class PendingClientSession:
    def __init__(self, shared_secret: bytes, init: dict, init_bytes: bytes, clock=time.time):
        self._ss, self._init, self._init_bytes, self._clock = shared_secret, init, init_bytes, clock

    def finish(self, resp: HandshakeResponse | dict) -> SecureChannel:
        """Verify the server's key confirmation and return the channel. Raises SessionError on
        a wrong gateway key, a corrupted ciphertext, or a tampered response."""
        r = HandshakeResponse.model_validate(resp)
        sid, s_nonce = _b64d(r.session_id), _b64d(r.server_nonce)
        if len(sid) != SESSION_ID_BYTES or len(s_nonce) != NONCE_BYTES:
            raise SessionError("malformed_response")
        keys = derive_keys(self._ss, _b64d(self._init["client_nonce"]), s_nonce, sid, self._init_bytes)
        if not hmac.compare_digest(_confirm_tag(keys.confirm, sid, s_nonce, self._init_bytes), _b64d(r.confirm)):
            raise SessionError("key_confirmation_failed")
        return SecureChannel("client", sid, keys, self._clock() + r.expires_in_s, self._clock)


def client_initiate(backend: PqcBackend, gateway_key_id: str, gateway_public_key: bytes, signer_id: str,
                    signer_secret_key: bytes, now: datetime, clock=time.time) -> tuple[dict, PendingClientSession]:
    ct, ss = backend.kem_encapsulate(gateway_public_key)
    init = {"protocol_version": SESSION_VERSION, "kem_algorithm": backend.kem_algorithm,
            "sig_algorithm": backend.sig_algorithm, "signer_id": signer_id, "gateway_key_id": gateway_key_id,
            "ciphertext": _b64e(ct), "client_nonce": _b64e(os.urandom(NONCE_BYTES)), "timestamp": iso_utc(now)}
    init_bytes = init_signing_bytes(init)
    init["signature"] = _b64e(backend.sign(signer_secret_key, init_bytes, INIT_CONTEXT))
    return init, PendingClientSession(ss, init, init_bytes, clock)


def server_accept(backend: PqcBackend, init: HandshakeInit, kem_secret_key: bytes, signer_public_key: bytes,
                  now: datetime, max_skew_s: float, ttl_s: int, clock=time.time) -> tuple[HandshakeResponse, SecureChannel]:
    """Server side. Caller has already resolved the signer/gateway key by id. Order: version and
    algorithms -> signature (covers the ciphertext) -> freshness -> decapsulate -> confirm."""
    if init.protocol_version != SESSION_VERSION:
        raise SessionError("unsupported_version")
    if init.kem_algorithm != backend.kem_algorithm or init.sig_algorithm != backend.sig_algorithm:
        raise SessionError("unsupported_algorithm")
    init_bytes = init_signing_bytes(init)
    try:
        sig = _b64d(init.signature)
    except SessionError:
        raise SessionError("invalid_signature") from None
    if not backend.verify(signer_public_key, init_bytes, sig, INIT_CONTEXT):
        raise SessionError("invalid_signature")
    try:
        ts = parse_iso(init.timestamp)
    except ValueError:
        raise SessionError("malformed_timestamp") from None
    if abs((now - ts).total_seconds()) > max_skew_s:
        raise SessionError("stale_or_future_handshake")
    client_nonce = _b64d(init.client_nonce)
    if len(client_nonce) != NONCE_BYTES:
        raise SessionError("malformed_nonce")
    try:
        ss = backend.kem_decapsulate(kem_secret_key, _b64d(init.ciphertext))
    except PqcError:
        raise SessionError("malformed_ciphertext") from None
    sid, s_nonce = os.urandom(SESSION_ID_BYTES), os.urandom(NONCE_BYTES)
    keys = derive_keys(ss, client_nonce, s_nonce, sid, init_bytes)
    resp = HandshakeResponse(session_id=_b64e(sid), server_nonce=_b64e(s_nonce), expires_in_s=ttl_s,
                             confirm=_b64e(_confirm_tag(keys.confirm, sid, s_nonce, init_bytes)))
    return resp, SecureChannel("server", sid, keys, clock() + ttl_s, clock)
