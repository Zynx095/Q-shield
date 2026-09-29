"""Vision pipeline configuration (JSON) with strict validation."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai.vision.zones import Zone, ZoneError

_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
ANCHORS = ("bottom_center", "center")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CameraConfig:
    source: int | str = 0            # device index, video file path, or stream URL
    backend: str = "auto"            # auto | dshow | msmf (Windows capture backends)
    width: int = 640
    height: int = 480
    target_fps: float = 5.0          # loop pacing for `run`; benchmark ignores it


@dataclass(frozen=True)
class ModelConfig:
    path: str = "ai/models/yolo11n.pt"
    name: str = "yolo11n"
    conf_threshold: float = 0.4
    imgsz: int = 640
    device: str = "cpu"
    classes_of_interest: tuple[str, ...] = ("person",)


@dataclass(frozen=True)
class HealthConfig:
    dark_mean_below: float = 12.0        # mean gray level (0-255) under which a frame counts as dark
    flat_texture_below: float = 1.5      # mean |neighbour pixel difference| under which a frame counts as flat
    consecutive_frames: int = 5          # frames of agreement before a state change is reported
    source_lost_after_failures: int = 10 # consecutive failed reads before the source counts as lost


@dataclass(frozen=True)
class EmitConfig:
    repeat_interval_s: float = 5.0   # re-emit a continuing (object, zone) at most this often
    absence_gap_s: float = 2.0       # unseen this long => next sighting counts as a new appearance
    outside_zones: bool = True       # also emit detections that fall in no zone


@dataclass(frozen=True)
class VisionConfig:
    device_id: str
    camera: CameraConfig = field(default_factory=CameraConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    zones: tuple[Zone, ...] = ()
    zone_anchor: str = "bottom_center"
    restricted_classes: tuple[str, ...] = ("person",)
    health: HealthConfig = field(default_factory=HealthConfig)
    emit: EmitConfig = field(default_factory=EmitConfig)


def _sub(cls, data: dict[str, Any] | None, where: str):
    data = data or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{where} must be an object")
    unknown = set(data) - set(cls.__dataclass_fields__)
    if unknown:
        raise ConfigError(f"unknown keys in {where}: {sorted(unknown)}")
    return cls(**data)


def parse_config(data: dict[str, Any]) -> VisionConfig:
    if not isinstance(data, dict):
        raise ConfigError("config must be a JSON object")
    known = {"device_id", "camera", "model", "zones", "zone_anchor", "restricted_classes", "health", "emit"}
    if set(data) - known:
        raise ConfigError(f"unknown top-level keys: {sorted(set(data) - known)}")
    device_id = data.get("device_id")
    if not isinstance(device_id, str) or not _NAME.match(device_id):
        raise ConfigError("device_id is required and must match [A-Za-z0-9_.-]{1,64}")

    camera = _sub(CameraConfig, data.get("camera"), "camera")
    model_raw = dict(data.get("model") or {})
    if "classes_of_interest" in model_raw:
        model_raw["classes_of_interest"] = tuple(model_raw["classes_of_interest"])
    model = _sub(ModelConfig, model_raw, "model")
    health = _sub(HealthConfig, data.get("health"), "health")
    emit = _sub(EmitConfig, data.get("emit"), "emit")

    if not isinstance(camera.source, (int, str)) or isinstance(camera.source, bool):
        raise ConfigError("camera.source must be an index or a path/URL")
    if camera.backend not in ("auto", "dshow", "msmf"):
        raise ConfigError("camera.backend must be auto|dshow|msmf")
    if not (16 <= camera.width <= 7680 and 16 <= camera.height <= 4320):
        raise ConfigError("camera width/height out of range")
    if not (0 < camera.target_fps <= 120):
        raise ConfigError("camera.target_fps must be in (0, 120]")
    if not (0.0 < model.conf_threshold <= 1.0):
        raise ConfigError("model.conf_threshold must be in (0, 1]")
    if not (32 <= model.imgsz <= 2048):
        raise ConfigError("model.imgsz out of range")
    if not model.classes_of_interest or not all(isinstance(c, str) and c for c in model.classes_of_interest):
        raise ConfigError("model.classes_of_interest must be a non-empty list of names")
    if health.consecutive_frames < 1 or health.source_lost_after_failures < 1:
        raise ConfigError("health frame counts must be >= 1")
    if emit.repeat_interval_s <= 0 or emit.absence_gap_s < 0:
        raise ConfigError("emit intervals invalid")

    anchor = data.get("zone_anchor", "bottom_center")
    if anchor not in ANCHORS:
        raise ConfigError(f"zone_anchor must be one of {ANCHORS}")
    restricted = tuple(data.get("restricted_classes", ("person",)))

    try:
        zones = tuple(Zone.from_dict(z) for z in data.get("zones", []))
    except (ZoneError, TypeError, KeyError) as e:
        raise ConfigError(f"invalid zone: {e}") from None
    names = [z.name for z in zones]
    if len(set(names)) != len(names):
        raise ConfigError("zone names must be unique")

    return VisionConfig(device_id, camera, model, zones, anchor, restricted, health, emit)


def load_config(path: str | Path) -> VisionConfig:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigError(f"cannot read config {path}: {e}") from None
    return parse_config(data)
