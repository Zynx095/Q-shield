"""Helpers for building (valid and deliberately invalid) signed observation envelopes."""
import base64
import json
from datetime import datetime, timezone

from backend.protocol.observation import Observation
from backend.protocol.signed_observation import (
    CONTEXT, PROTOCOL_VERSION, iso_utc, sign_observation, signing_bytes,
)


def now_dt(clock) -> datetime:
    return datetime.fromtimestamp(clock(), timezone.utc)


def make_obs(clock, **over) -> Observation:
    base = dict(event_type="visual_observation", device_id="DEVICE-001", timestamp=iso_utc(now_dt(clock)),
                source="usb_webcam", object="person", confidence=0.91, zone="restricted_zone",
                zone_kind="restricted", bbox={"x1": 0.6, "y1": 0.1, "x2": 0.9, "y2": 0.9}, anomaly=True,
                anomaly_reason="restricted_class_in_restricted_zone", model={"name": "yolo11n", "version": "t"})
    base.update(over)
    return Observation(**base)


def signed_env(world, clock, signer="vision-1", obs=None, source_id="usb_webcam:0", at=None) -> dict:
    obs = obs or make_obs(clock)
    return sign_observation(world.backend, world.signers[signer], signer, source_id, obs, at or now_dt(clock))


def sign_body(world, signer, body: dict, context: bytes = CONTEXT) -> dict:
    """Sign an arbitrary envelope body (for crafting inconsistent-but-validly-signed messages)."""
    sig = world.backend.sign(world.signers[signer], signing_bytes(body), context)
    return {**body, "signature": base64.b64encode(sig).decode()}


def raw_body(clock, obs=None, signer="vision-1", **over) -> dict:
    obs = obs or make_obs(clock)
    body = {"protocol_version": PROTOCOL_VERSION, "algorithm": "ML-DSA-65", "signer_id": signer,
            "source_id": "usb_webcam:0", "observation_id": obs.observation_id,
            "timestamp": iso_utc(now_dt(clock)), "payload": json.dumps(obs.to_wire(), sort_keys=True)}
    body.update(over)
    return body
