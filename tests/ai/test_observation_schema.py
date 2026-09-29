"""Event schema validation: malformed/missing observations and confidence bounds."""
import copy
import json
import math

import pytest
from pydantic import ValidationError

from backend.protocol.observation import Observation

GOOD = {
    "event_type": "visual_observation", "device_id": "DEVICE-001",
    "timestamp": "2026-01-01T00:00:00+00:00", "source": "usb_webcam",
    "object": "person", "confidence": 0.91, "zone": "restricted_zone", "zone_kind": "restricted",
    "bbox": {"x1": 0.6, "y1": 0.1, "x2": 0.9, "y2": 0.9},
    "anomaly": True, "anomaly_reason": "restricted_class_in_restricted_zone",
    "model": {"name": "yolo11n", "version": "x"},
}
HEALTH = {
    "event_type": "camera_health", "device_id": "DEVICE-001", "timestamp": "2026-01-01T00:00:00Z",
    "source": "usb_webcam", "anomaly": True, "anomaly_reason": "camera_obstructed",
    "details": {"state": "obstructed"},
}


def mod(base, **kw):
    d = copy.deepcopy(base)
    d.update(kw)
    return d


def test_valid_visual_observation():
    o = Observation(**GOOD)
    assert o.confidence == 0.91 and o.schema_version == 1
    assert o.timestamp.utcoffset().total_seconds() == 0
    uuid_len = len(o.observation_id)
    assert uuid_len == 36


def test_valid_camera_health():
    assert Observation(**HEALTH).details["state"] == "obstructed"


def test_wire_roundtrip():
    o = Observation(**GOOD)
    assert Observation(**json.loads(json.dumps(o.to_wire()))) == o


@pytest.mark.parametrize("field", ["event_type", "device_id", "timestamp", "source", "anomaly"])
def test_missing_required_field(field):
    d = copy.deepcopy(GOOD)
    del d[field]
    with pytest.raises(ValidationError):
        Observation(**d)


@pytest.mark.parametrize("field", ["object", "confidence", "bbox"])
def test_visual_observation_needs_object_confidence_bbox(field):
    d = copy.deepcopy(GOOD)
    del d[field]
    with pytest.raises(ValidationError):
        Observation(**d)


@pytest.mark.parametrize("bad", [-0.01, 1.01, 5, -1, math.nan, math.inf, "high", None])
def test_confidence_bounds(bad):
    with pytest.raises(ValidationError):
        Observation(**mod(GOOD, confidence=bad))


@pytest.mark.parametrize("ok", [0.0, 0.5, 1.0])
def test_confidence_bounds_inclusive(ok):
    assert Observation(**mod(GOOD, confidence=ok)).confidence == ok


@pytest.mark.parametrize("bbox", [
    {"x1": 0.5, "y1": 0.1, "x2": 0.4, "y2": 0.9},     # x2 < x1
    {"x1": 0.5, "y1": 0.5, "x2": 0.5, "y2": 0.9},     # zero width
    {"x1": -0.1, "y1": 0.1, "x2": 0.4, "y2": 0.9},    # out of range
    {"x1": 0.1, "y1": 0.1, "x2": 1.2, "y2": 0.9},
    {"x1": 0.1, "y1": 0.1, "x2": 0.4},                # missing y2
    {"x1": math.nan, "y1": 0.1, "x2": 0.4, "y2": 0.9},
])
def test_bad_bbox(bbox):
    with pytest.raises(ValidationError):
        Observation(**mod(GOOD, bbox=bbox))


@pytest.mark.parametrize("ts", ["2026-01-01T00:00:00", "not a time", "", None, 12])
def test_timestamp_must_be_timezone_aware_and_valid(ts):
    with pytest.raises(ValidationError):
        Observation(**mod(GOOD, timestamp=ts))


def test_non_utc_timestamp_normalised_to_utc():
    o = Observation(**mod(GOOD, timestamp="2026-01-01T05:30:00+05:30"))
    assert o.timestamp.isoformat() == "2026-01-01T00:00:00+00:00"


@pytest.mark.parametrize("field,val", [
    ("device_id", ""), ("device_id", "bad id/../"), ("device_id", "x" * 65),
    ("event_type", "trust_update"), ("source", "cctv"), ("object", ""),
    ("schema_version", 2), ("observation_id", "not-a-uuid"), ("zone_kind", "secret"),
])
def test_invalid_field_values(field, val):
    with pytest.raises(ValidationError):
        Observation(**mod(GOOD, **{field: val}))


def test_unknown_fields_forbidden_so_trust_cannot_be_smuggled_in():
    for extra in ("trust", "trust_score", "compromised", "verdict"):
        with pytest.raises(ValidationError):
            Observation(**mod(GOOD, **{extra: 0}))


def test_zone_and_zone_kind_together():
    with pytest.raises(ValidationError):
        Observation(**mod(GOOD, zone_kind=None))
    with pytest.raises(ValidationError):
        Observation(**mod(GOOD, zone=None))


def test_anomaly_requires_reason():
    with pytest.raises(ValidationError):
        Observation(**mod(GOOD, anomaly_reason=None))


def test_camera_health_shape_rules():
    with pytest.raises(ValidationError):
        Observation(**mod(HEALTH, confidence=0.5))
    with pytest.raises(ValidationError):
        Observation(**mod(HEALTH, object="person"))
    with pytest.raises(ValidationError):
        Observation(**mod(HEALTH, details={}))
    with pytest.raises(ValidationError):
        Observation(**mod(HEALTH, details={"state": "on_fire"}))


def test_non_object_input_rejected():
    for bad in (None, [], "x", 5):
        with pytest.raises(ValidationError):
            Observation.model_validate(bad)
