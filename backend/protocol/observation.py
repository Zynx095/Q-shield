"""Normalized observation schema (v1).

An Observation states what an observer *saw*. It is evidence for later fusion, never a
verdict: nothing here says a device is compromised, and the `anomaly` flag only means the
observation matched a configured rule (e.g. "person in a zone marked restricted").
Trust decisions belong to the Phase 4 trust engine.

This module is dependency-light (pydantic only) so vision code can import it without
pulling in the backend.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 1


class EventType(str, Enum):
    VISUAL_OBSERVATION = "visual_observation"  # an object seen by the camera
    CAMERA_HEALTH = "camera_health"            # camera obstructed / source lost / restored


class Source(str, Enum):
    USB_WEBCAM = "usb_webcam"
    NETWORK_CAMERA = "network_camera"    # a camera stream over the network (e.g. an ESP32-CAM MJPEG endpoint)
    VIDEO_FILE = "video_file"            # a recorded video: replay and tests, never live evidence


class ZoneKind(str, Enum):
    RESTRICTED = "restricted"
    MONITORED = "monitored"


class CameraState(str, Enum):
    """Camera health as the vision service reports it (ai/vision/health.py documents each state)."""
    OK = "ok"
    OBSTRUCTED = "obstructed"        # no usable image: covered, facing a blank surface, or blinded
    SOURCE_LOST = "source_lost"      # no frames (unplugged, driver failure)
    FROZEN = "frozen"                # the same frame repeated: stuck or substituted feed
    VIEW_CHANGED = "view_changed"    # the scene no longer matches the reference view: camera moved or redirected
    DEGRADED = "degraded"            # still sees, poorly: low light or blur


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=64)


class BBox(BaseModel):
    """Normalized [0,1] image coordinates, x1<x2 and y1<y2."""
    model_config = ConfigDict(extra="forbid")
    x1: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    y1: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    x2: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    y2: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not (self.x1 < self.x2 and self.y1 < self.y2):
            raise ValueError("bbox must satisfy x1<x2 and y1<y2")
        return self


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    observation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    device_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    timestamp: datetime                     # observer's clock; must be timezone-aware
    source: Source
    object: str | None = Field(default=None, min_length=1, max_length=64)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    zone: str | None = Field(default=None, min_length=1, max_length=64)
    zone_kind: ZoneKind | None = None
    bbox: BBox | None = None
    anomaly: bool
    anomaly_reason: str | None = Field(default=None, max_length=128)
    model: ModelInfo | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def _version(cls, v: int) -> int:
        if v != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {v}")
        return v

    @field_validator("observation_id")
    @classmethod
    def _uuid(cls, v: str) -> str:
        uuid.UUID(v)  # raises ValueError if malformed
        return v

    @field_validator("timestamp", mode="before")
    @classmethod
    def _iso_only(cls, v: Any) -> Any:
        # Numeric epochs are ambiguous (seconds vs milliseconds); require ISO-8601 text.
        if not isinstance(v, (str, datetime)):
            raise ValueError("timestamp must be an ISO-8601 string")
        return v

    @field_validator("timestamp")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return v.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _shape_by_type(self) -> Self:
        if self.event_type is EventType.VISUAL_OBSERVATION:
            if self.object is None or self.confidence is None or self.bbox is None:
                raise ValueError("visual_observation requires object, confidence and bbox")
        else:  # camera_health
            if self.confidence is not None or self.object is not None:
                raise ValueError("camera_health must not carry object/confidence")
            state = self.details.get("state")
            if state not in {s.value for s in CameraState}:
                raise ValueError("camera_health requires details.state in " + "|".join(s.value for s in CameraState))
        if (self.zone is None) != (self.zone_kind is None):
            raise ValueError("zone and zone_kind must be set together")
        if self.anomaly and not self.anomaly_reason:
            raise ValueError("anomaly=true requires anomaly_reason")
        return self

    def to_wire(self) -> dict:
        """JSON-safe dict for HTTP/JSONL."""
        return self.model_dump(mode="json", exclude_none=False)
