"""Vision service -> gateway with ML-DSA-signed observations, optionally inside an ML-KEM session.

The signing identity belongs to this software service (its ML-DSA private key), not to the USB
webcam. The service holds only its own signer key (unsealed with its own key-encryption key); it
never receives the gateway master key.

Modes:
  signed  (default): POST /api/v1/observations/signed   -> authenticity + integrity (ML-DSA-65)
  secure           : additionally establish an ML-KEM-768 session and send the signed envelope
                     AES-256-GCM-protected via /api/v1/observations/secure -> plus confidentiality
This module imports no database or web-framework code.
"""
from __future__ import annotations

import json
import logging
import time
from collections import deque
from datetime import datetime, timezone

from backend.protocol.observation import Observation
from backend.protocol.signed_observation import sign_observation
from backend.security.pqc import PqcBackend
from backend.security.session import SecureChannel, SessionError, client_initiate

log = logging.getLogger("qshield.vision")


class SignedHttpSink:
    def __init__(self, base_url: str, backend: PqcBackend, signer_id: str, source_id: str, secret_key: bytes,
                 *, secure: bool = False, gateway_key_id: str | None = None,
                 gateway_public_key: bytes | None = None, client=None, max_queue: int = 1000,
                 now=lambda: datetime.now(timezone.utc)):
        import httpx

        if secure and not (gateway_key_id and gateway_public_key):
            raise ValueError("secure mode needs the pinned gateway key id and public key")
        self._client = client or httpx.Client(base_url=base_url, timeout=5.0)
        self._backend, self._signer_id, self._source_id, self._sk = backend, signer_id, source_id, secret_key
        self._secure, self._gw_id, self._gw_pk, self._now = secure, gateway_key_id, gateway_public_key, now
        self._channel: SecureChannel | None = None
        self._queue: deque[dict] = deque(maxlen=max_queue)
        self.dropped = 0

    def emit(self, obs: Observation) -> None:
        if len(self._queue) == self._queue.maxlen:
            self.dropped += 1
        self._queue.append(sign_observation(self._backend, self._sk, self._signer_id, self._source_id, obs, self._now()))
        self._flush()

    def _establish(self) -> bool:
        init, pending = client_initiate(self._backend, self._gw_id, self._gw_pk, self._signer_id, self._sk, self._now())
        r = self._client.post("/api/v1/pqc/session", json=init)
        if r.status_code != 200:
            log.warning("session establishment rejected (%s)", r.status_code)
            return False
        try:
            self._channel = pending.finish(r.json())  # verifies the gateway's key confirmation
        except SessionError as e:
            log.error("gateway key confirmation failed (%s): wrong pinned key or tampering; not sending", e.reason)
            return False
        return True

    def _send(self, env: dict):
        if not self._secure:
            return self._client.post("/api/v1/observations/signed", json=env)
        if self._channel is None and not self._establish():
            raise ConnectionError("no session")
        counter, ct = self._channel.seal(json.dumps(env, separators=(",", ":")).encode())
        import base64
        r = self._client.post("/api/v1/observations/secure", json={
            "session_id": base64.b64encode(self._channel.session_id).decode(), "counter": counter,
            "ciphertext": base64.b64encode(ct).decode()})
        if r.status_code == 401:  # session unknown/expired (e.g. gateway restarted): re-establish next time
            self._channel = None
        return r

    def _flush(self) -> None:
        while self._queue:
            try:
                r = self._send(self._queue[0])
            except Exception as e:
                log.warning("gateway unreachable, %d observation(s) queued: %s", len(self._queue), e)
                return
            if r.status_code == 200 or r.status_code == 409:  # 409: gateway already has it (replay/duplicate)
                self._queue.popleft()
            elif r.status_code == 401 and self._secure and self._channel is None:
                return  # retry with a fresh session on the next emit
            elif 400 <= r.status_code < 500:
                log.error("gateway rejected signed observation (%s); dropping it", r.status_code)
                self._queue.popleft()
            else:
                return
