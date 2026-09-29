"""Signed observation envelope (protocol v1): ML-DSA authenticity for observations.

Wire form:
    {"protocol_version": 1, "algorithm": "ML-DSA-65", "signer_id": "vision-1",
     "source_id": "usb_webcam:0", "observation_id": "<uuid>", "timestamp": "<ISO-8601 UTC>",
     "payload": "<observation JSON, as a string>", "signature": "<base64>"}

What is signed (never a JSON serialization):
    encode_fields(b"QSHIELD-SIGNED-OBSERVATION", [protocol_version, algorithm, signer_id,
                  source_id, observation_id, timestamp, payload])   # see protocol/canonical.py
with ML-DSA context string b"qshield/signed-observation/v1" for domain separation. `payload` is
the exact text that was signed; the verifier parses it only AFTER the signature verifies.
Every metadata field is inside the signed bytes, so changing any of them invalidates the signature.

Identity: the signer_id names a *software component* (the vision service) whose ML-DSA private key
is held by that process. It does not identify the physical webcam.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from backend.protocol.canonical import encode_fields
from backend.protocol.observation import Observation
from backend.security.pqc import PqcBackend

PROTOCOL_VERSION = 1
DOMAIN = b"QSHIELD-SIGNED-OBSERVATION"
CONTEXT = b"qshield/signed-observation/v1"
MAX_PAYLOAD_CHARS = 16_384
_ID = r"^[A-Za-z0-9_.:-]{1,64}$"


class SignedObservationEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: int
    algorithm: str = Field(max_length=32)
    signer_id: str = Field(pattern=_ID)
    source_id: str = Field(pattern=_ID)
    observation_id: str = Field(min_length=36, max_length=36)
    timestamp: str = Field(max_length=40)          # signing time, ISO-8601 with timezone
    payload: str = Field(max_length=MAX_PAYLOAD_CHARS)
    signature: str = Field(max_length=8192)        # base64 (ML-DSA-65 signature is 3309 bytes -> 4412 chars)


def signing_bytes(e: SignedObservationEnvelope | dict) -> bytes:
    g = (lambda k: getattr(e, k)) if not isinstance(e, dict) else (lambda k: e[k])
    return encode_fields(DOMAIN, [str(g("protocol_version")), g("algorithm"), g("signer_id"), g("source_id"),
                                  g("observation_id"), g("timestamp"), g("payload")])


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_iso(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp; must carry a timezone. Raises ValueError."""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return dt.astimezone(timezone.utc)


def decode_signature(b64: str) -> bytes:
    try:
        return base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("signature is not valid base64") from None


def sign_observation(backend: PqcBackend, secret_key: bytes, signer_id: str, source_id: str,
                     obs: Observation, now: datetime) -> dict:
    """Build a signed envelope for `obs`. The observation is serialised once; that exact text is signed."""
    import json

    body = {
        "protocol_version": PROTOCOL_VERSION, "algorithm": backend.sig_algorithm,
        "signer_id": signer_id, "source_id": source_id, "observation_id": obs.observation_id,
        "timestamp": iso_utc(now), "payload": json.dumps(obs.to_wire(), separators=(",", ":"), sort_keys=True),
    }
    sig = backend.sign(secret_key, signing_bytes(body), CONTEXT)
    return {**body, "signature": base64.b64encode(sig).decode()}
