"""Q-SHIELD device wire protocol, version 1.

An envelope is a JSON object:

    {"proto": 1, "auth": "hmac-sha256-psk", "type": "telemetry",
     "device_id": "DEVICE-001", "counter": 42, "payload": "<JSON text>", "tag": "<hex>"}

`payload` is a JSON *string*. The tag covers the exact payload bytes as sent, so no
canonicalisation is needed and the ESP32 and gateway cannot disagree on formatting.

Authentication profile `hmac-sha256-psk` is symmetric (provisioned per-device secret).
It is NOT post-quantum. Do not describe it as such.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Literal

from pydantic import BaseModel, Field

PROTO_VERSION = 1
DOMAIN = b"QSHIELD-V1"

AUTH_HMAC = "hmac-sha256-psk"  # ESP32 profile: provisioned HMAC-SHA256 credential
AUTH_PQC = "pqc-mldsa-mlkem"   # reserved for Phase 3 (ML-DSA signatures, ML-KEM sessions)

MSG_REGISTER = "register"
MSG_HEARTBEAT = "heartbeat"
MSG_TELEMETRY = "telemetry"
MSG_RECOVERY = "recovery"   # recovery-channel report from a quarantined/recovering device (Phase 6/7)
MESSAGE_TYPES = (MSG_REGISTER, MSG_HEARTBEAT, MSG_TELEMETRY, MSG_RECOVERY)

MAX_PAYLOAD_BYTES = 2048
SECRET_BYTES = 32


class Envelope(BaseModel):
    proto: int
    auth: str = Field(max_length=32)
    type: str = Field(max_length=16)
    device_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    counter: int = Field(ge=0, le=2**53)
    payload: str = Field(max_length=MAX_PAYLOAD_BYTES)
    tag: str = Field(max_length=256)


def signing_input(auth: str, msg_type: str, device_id: str, counter: int, payload: str) -> bytes:
    """Bytes covered by the tag. Binds profile, type, device and counter to the payload."""
    head = "\n".join([auth, msg_type, device_id, str(counter)]).encode("utf-8")
    return DOMAIN + b"\n" + head + b"\n" + payload.encode("utf-8")


def hmac_tag(secret: bytes, data: bytes) -> str:
    return hmac.new(secret, data, hashlib.sha256).hexdigest()


def build_hmac_envelope(
    secret: bytes, msg_type: Literal["register", "heartbeat", "telemetry", "recovery"],
    device_id: str, counter: int, payload: str,
) -> dict:
    data = signing_input(AUTH_HMAC, msg_type, device_id, counter, payload)
    return {
        "proto": PROTO_VERSION, "auth": AUTH_HMAC, "type": msg_type,
        "device_id": device_id, "counter": counter, "payload": payload,
        "tag": hmac_tag(secret, data),
    }


def check_hmac_tag(secret: bytes, env: Envelope) -> bool:
    data = signing_input(env.auth, env.type, env.device_id, env.counter, env.payload)
    return hmac.compare_digest(hmac_tag(secret, data), env.tag.lower())
