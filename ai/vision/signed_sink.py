"""Vision service -> gateway with ML-DSA-signed observations, optionally inside an ML-KEM session.

The signing identity belongs to this software service (its ML-DSA private key), not to the USB
webcam. The service holds only its own signer key (unsealed with its own key-encryption key); it
never receives the gateway master key.

Modes:
  signed  (default): POST /api/v1/observations/signed   -> authenticity + integrity (ML-DSA-65)
  secure           : additionally establish an ML-KEM-768 session and send the signed envelope
                     AES-256-GCM-protected via /api/v1/observations/secure -> plus confidentiality

Failure handling (so a persistent problem cannot exhaust the gateway's session table):
  * a session is re-established ONLY when the gateway answers 401 "session_expired" (unknown or expired session);
  * any other 4xx means the observation itself was refused (stale clock, bad signature, retired signer...): it is
    dropped and counted, and the session is kept: re-handshaking cannot fix it;
  * a failed handshake or an unreachable gateway backs off exponentially (1 s doubling to 60 s); observations queue
    (bounded) meanwhile and nothing is sent until the backoff ends;
  * at most `session_budget` handshakes per hour, whatever happens (default 20, well under the gateway's 64 live
    sessions), so even a pathological loop cannot fill the gateway's session table;
  * `status()` reports what happened for operators (sessions, rejections, last error, backoff).
This module imports no database or web-framework code.
"""
from __future__ import annotations

import base64
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


class _NoSession(Exception):
    pass


class SignedHttpSink:
    def __init__(self, base_url: str, backend: PqcBackend, signer_id: str, source_id: str, secret_key: bytes,
                 *, secure: bool = False, gateway_key_id: str | None = None,
                 gateway_public_key: bytes | None = None, client=None, max_queue: int = 1000,
                 now=lambda: datetime.now(timezone.utc), monotonic=time.monotonic,
                 backoff_base_s: float = 1.0, backoff_max_s: float = 60.0, session_budget: int = 20,
                 session_budget_window_s: float = 3600.0):
        import httpx

        if secure and not (gateway_key_id and gateway_public_key):
            raise ValueError("secure mode needs the pinned gateway key id and public key")
        self._client = client or httpx.Client(base_url=base_url, timeout=5.0)
        self._backend, self._signer_id, self._source_id, self._sk = backend, signer_id, source_id, secret_key
        self._secure, self._gw_id, self._gw_pk, self._now = secure, gateway_key_id, gateway_public_key, now
        self._mono, self._backoff_base, self._backoff_max = monotonic, backoff_base_s, backoff_max_s
        self._budget, self._budget_window = session_budget, session_budget_window_s
        self._channel: SecureChannel | None = None
        self._queue: deque[dict] = deque(maxlen=max_queue)
        self._handshakes: deque[float] = deque()
        self._failures = 0
        self._backoff_until = 0.0
        self.dropped = 0              # queue overflow
        self.rejected = 0             # observations the gateway refused (dropped: resending cannot help)
        self.delivered = 0
        self.sessions = 0             # successful handshakes
        self.last_error: str | None = None

    # ------------------------------------------------------------------ public
    def emit(self, obs: Observation) -> None:
        if len(self._queue) == self._queue.maxlen:
            self.dropped += 1
        self._queue.append(sign_observation(self._backend, self._sk, self._signer_id, self._source_id, obs, self._now()))
        self._flush()

    def status(self) -> dict:
        """What an operator needs to see when observations are not arriving."""
        now = self._mono()
        return {"mode": "secure" if self._secure else "signed", "session_open": self._channel is not None,
                "sessions_established": self.sessions, "handshakes_last_hour": self._recent_handshakes(now),
                "delivered": self.delivered, "rejected": self.rejected, "queued": len(self._queue),
                "dropped_queue_full": self.dropped, "consecutive_failures": self._failures,
                "backoff_remaining_s": round(max(0.0, self._backoff_until - now), 1), "last_error": self.last_error}

    # ------------------------------------------------------------------ session
    def _recent_handshakes(self, now: float) -> int:
        while self._handshakes and now - self._handshakes[0] > self._budget_window:
            self._handshakes.popleft()
        return len(self._handshakes)

    def _fail(self, reason: str) -> None:
        self._failures += 1
        delay = min(self._backoff_max, self._backoff_base * 2 ** (self._failures - 1))
        self._backoff_until = self._mono() + delay
        if reason != self.last_error:
            log.warning("vision -> gateway: %s; backing off %.0f s, %d observation(s) queued", reason, delay, len(self._queue))
        self.last_error = reason

    def _establish(self) -> None:
        now = self._mono()
        if self._recent_handshakes(now) >= self._budget:
            raise _NoSession(f"session budget reached ({self._budget} handshakes per {self._budget_window:.0f} s)")
        self._handshakes.append(now)
        init, pending = client_initiate(self._backend, self._gw_id, self._gw_pk, self._signer_id, self._sk, self._now())
        r = self._client.post("/api/v1/pqc/session", json=init)
        if r.status_code != 200:
            raise _NoSession(f"session establishment rejected (HTTP {r.status_code})")
        try:
            self._channel = pending.finish(r.json())  # verifies the gateway's key confirmation
        except SessionError as e:
            log.error("gateway key confirmation failed (%s): wrong pinned key or tampering; not sending", e.reason)
            raise _NoSession(f"gateway key confirmation failed ({e.reason})") from None
        self.sessions += 1

    # ------------------------------------------------------------------ send
    def _post_sealed(self, env: dict):
        counter, ct = self._channel.seal(json.dumps(env, separators=(",", ":")).encode())
        return self._client.post("/api/v1/observations/secure", json={
            "session_id": base64.b64encode(self._channel.session_id).decode(), "counter": counter,
            "ciphertext": base64.b64encode(ct).decode()})

    @staticmethod
    def _detail(r) -> str | None:
        try:
            return (r.json() or {}).get("detail")
        except Exception:
            return None

    def _send(self, env: dict):
        if not self._secure:
            return self._client.post("/api/v1/observations/signed", json=env)
        if self._channel is None:
            self._establish()
        r = self._post_sealed(env)
        if r.status_code == 401 and self._detail(r) == "session_expired":
            self._channel = None                    # the gateway lost or expired the session: one new handshake
            self._establish()
            r = self._post_sealed(env)
        return r

    def _flush(self) -> None:
        if self._queue and self._mono() < self._backoff_until:
            return                                   # backing off: keep queueing, send nothing
        while self._queue:
            try:
                r = self._send(self._queue[0])
            except _NoSession as e:
                self._fail(str(e))
                return
            except Exception as e:                   # gateway unreachable
                self._fail(f"gateway unreachable: {e}")
                return
            if r.status_code in (200, 409):           # 409: the gateway already has it (replay/duplicate)
                self._queue.popleft()
                self.delivered += 1
                self._failures, self.last_error = 0, None
            elif 400 <= r.status_code < 500:
                # Refused for what it is (clock skew, signature, signer status...): resending or re-handshaking cannot
                # help, so drop it, count it and keep the session.
                self._queue.popleft()
                self.rejected += 1
                reason = f"gateway refused an observation (HTTP {r.status_code} {self._detail(r) or ''})".strip()
                if reason != self.last_error:
                    log.error("%s; dropping it (check the clock and the signer's status)", reason)
                self.last_error = reason
            else:
                self._fail(f"gateway error HTTP {r.status_code}")
                return
