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
    warmup_frames: int = 15          # live cameras only: frames discarded at start while auto-exposure settles


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
    """Camera-health thresholds (ai/vision/health.py). All are UNVALIDATED defaults for a 640x480 webcam indoors."""
    dark_mean_below: float = 12.0        # mean gray level (0-255) under which a frame counts as dark
    flat_texture_below: float = 1.5      # mean |neighbour pixel difference| under which a frame counts as flat
    consecutive_frames: int = 5          # frames of agreement before a state change is reported
    source_lost_after_failures: int = 10 # consecutive failed reads before the source counts as lost
    sustain_s: float = 2.0               # ...and seconds of agreement: a flicker or a passing hand is not reported
    bright_mean_above: float = 235.0     # mean gray level over which a frame counts as overexposed (blinded)
    baseline_frames: int = 10            # healthy frames averaged into the reference view at start
    view_similarity_below: float = 0.7   # structural similarity to the reference under which the view has changed
    shift_min_fraction: float = 0.1      # a whole-image shift this large (share of the frame) is a viewpoint change
    shift_peak_min: float = 0.3          # phase-correlation peak that counts as "the old scene, shifted"
    low_light_similarity_min: float = 0.6  # a dark frame still this similar to the reference is low light, not covered
    blur_ratio_below: float = 0.2        # sharpness below this share of the reference's counts as blurred
    frozen_diff_below: float = 0.05      # mean |frame - previous frame| (gray levels) under which frames are identical
    frozen_min_frames: int = 10          # identical frames in a row before the feed counts as frozen...
    frozen_after_s: float = 3.0          # ...over at least this long


@dataclass(frozen=True)
class ProximityConfig:
    """Image-space proximity heuristics (bounding-box area as a share of the frame). NOT a distance measurement."""
    enabled: bool = True
    classes: tuple[str, ...] = ("person",)
    close_area_fraction: float = 0.35    # a subject's box covering this share of the frame is "too close"
    close_frames: int = 2                # ...for this many frames in a row
    approach_growth: float = 2.0         # box area grew this many times...
    approach_window_s: float = 2.0       # ...within this window...
    approach_min_area_fraction: float = 0.12  # ...ending at least this large: "rapid approach"


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
    proximity: ProximityConfig = field(default_factory=ProximityConfig)


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
    known = {"device_id", "camera", "model", "zones", "zone_anchor", "restricted_classes", "health", "emit", "proximity"}
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
    prox_raw = dict(data.get("proximity") or {})
    if "classes" in prox_raw:
        prox_raw["classes"] = tuple(prox_raw["classes"])
    proximity = _sub(ProximityConfig, prox_raw, "proximity")

    if not isinstance(camera.source, (int, str)) or isinstance(camera.source, bool):
        raise ConfigError("camera.source must be an index or a path/URL")
    if camera.backend not in ("auto", "dshow", "msmf"):
        raise ConfigError("camera.backend must be auto|dshow|msmf")
    if not (16 <= camera.width <= 7680 and 16 <= camera.height <= 4320):
        raise ConfigError("camera width/height out of range")
    if not (0 < camera.target_fps <= 120):
        raise ConfigError("camera.target_fps must be in (0, 120]")
    if isinstance(camera.warmup_frames, bool) or not isinstance(camera.warmup_frames, int) or not (0 <= camera.warmup_frames <= 300):
        raise ConfigError("camera.warmup_frames must be an integer in [0, 300]")
    if not (0.0 < model.conf_threshold <= 1.0):
        raise ConfigError("model.conf_threshold must be in (0, 1]")
    if not (32 <= model.imgsz <= 2048):
        raise ConfigError("model.imgsz out of range")
    if not model.classes_of_interest or not all(isinstance(c, str) and c for c in model.classes_of_interest):
        raise ConfigError("model.classes_of_interest must be a non-empty list of names")
    if health.consecutive_frames < 1 or health.source_lost_after_failures < 1:
        raise ConfigError("health frame counts must be >= 1")
    if health.baseline_frames < 1 or health.frozen_min_frames < 2:
        raise ConfigError("health.baseline_frames must be >= 1 and health.frozen_min_frames >= 2")
    if health.sustain_s < 0 or health.frozen_after_s < 0 or health.frozen_diff_below < 0:
        raise ConfigError("health durations and frozen_diff_below must be >= 0")
    if not (0 <= health.dark_mean_below < health.bright_mean_above <= 255):
        raise ConfigError("health: need 0 <= dark_mean_below < bright_mean_above <= 255")
    for name in ("view_similarity_below", "shift_min_fraction", "shift_peak_min", "low_light_similarity_min", "blur_ratio_below"):
        if not (0.0 < getattr(health, name) <= 1.0):
            raise ConfigError(f"health.{name} must be in (0, 1]")
    if not (0.0 < proximity.approach_min_area_fraction <= 1.0 and 0.0 < proximity.close_area_fraction <= 1.0):
        raise ConfigError("proximity area fractions must be in (0, 1]")
    if proximity.approach_growth <= 1.0 or proximity.approach_window_s <= 0 or proximity.close_frames < 1:
        raise ConfigError("proximity: approach_growth must be > 1, approach_window_s > 0, close_frames >= 1")
    if not all(isinstance(c, str) and c for c in proximity.classes):
        raise ConfigError("proximity.classes must be a list of names")
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

    return VisionConfig(device_id, camera, model, zones, anchor, restricted, health, emit, proximity)


def load_config(path: str | Path) -> VisionConfig:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigError(f"cannot read config {path}: {e}") from None
    return parse_config(data)
