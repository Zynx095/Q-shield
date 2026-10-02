"""Frames -> normalized observations. This module makes NO trust decisions.

`anomaly` on an observation means only "matched a configured rule" (an object of a
restricted class inside a restricted zone; a subject too close to the camera or approaching it
fast, by image-space heuristics; a camera that is obstructed, lost, frozen, moved or degraded,
see ai/vision/health.py). What that
means for a device's trust is decided later, by the Phase 4 trust engine, together with
other evidence. YOLO reports what it sees; it does not decide whether a device is
compromised.

Emission policy: one observation per (object, zone) per frame, not per instance (no
tracker); a continuing sighting is re-emitted at most every `repeat_interval_s`, and a
re-appearance after `absence_gap_s` is emitted immediately.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from ai.vision.config import VisionConfig
from ai.vision.detector import Detection, Detector
from ai.vision.health import CameraHealthMonitor
from ai.vision.proximity import ProximityTracker
from ai.vision.zones import ZoneSet
from backend.protocol.observation import (
    BBox, CameraState, EventType, ModelInfo, Observation, Source, ZoneKind,
)

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class VisionPipeline:
    def __init__(self, cfg: VisionConfig, detector: Detector, clock: Clock = utc_now,
                 source: Source = Source.USB_WEBCAM):
        self.cfg = cfg
        self.detector = detector
        self.zones = ZoneSet(cfg.zones, cfg.zone_anchor)
        self.health = CameraHealthMonitor(cfg.health)
        self.proximity = ProximityTracker(cfg.proximity)
        self._clock = clock
        self._source = source
        self._last_seen: dict[tuple[str, str | None], datetime] = {}
        self._last_emit: dict[tuple[str, str | None], datetime] = {}
        self._model = ModelInfo(name=detector.name, version=detector.version)
        self._interest = set(cfg.model.classes_of_interest)
        self._restricted = set(cfg.restricted_classes)

    def process_frame(self, frame) -> list[Observation]:
        """frame: BGR ndarray, or None if the source failed to deliver one."""
        now = self._clock()
        out: list[Observation] = []
        found = [] if frame is None else [d for d in self.detector.detect(frame)
                                          if d.label in self._interest and d.confidence >= self.cfg.model.conf_threshold]

        # Detected subjects are masked out of the viewpoint check: someone walking through is not a moved camera.
        t = self.health.update(frame, now.timestamp(), [d.box for d in found])
        if t is not None:
            out.append(self._health_observation(now, t))
        if frame is None:
            return out

        for reason, det, metrics in self.proximity.update(now.timestamp(), found):
            out.append(self._visual_observation(now, det, self.zones.classify(det.box), reason, metrics))

        # Keep only the highest-confidence detection per (object, zone) key.
        best: dict[tuple[str, str | None], tuple[Detection, object]] = {}
        for det in found:
            zone = self.zones.classify(det.box)
            if zone is None and not self.cfg.emit.outside_zones:
                continue
            key = (det.label, zone.name if zone else None)
            if key not in best or det.confidence > best[key][0].confidence:
                best[key] = (det, zone)

        for key, (det, zone) in best.items():
            if self._should_emit(key, now):
                out.append(self._visual_observation(now, det, zone))
                self._last_emit[key] = now
            self._last_seen[key] = now
        return out

    def _should_emit(self, key, now: datetime) -> bool:
        seen = self._last_seen.get(key)
        if seen is None or (now - seen).total_seconds() > self.cfg.emit.absence_gap_s:
            return True  # new appearance
        last = self._last_emit.get(key)
        return last is None or (now - last).total_seconds() >= self.cfg.emit.repeat_interval_s

    def _visual_observation(self, now: datetime, det: Detection, zone, proximity: str | None = None,
                            metrics: dict | None = None) -> Observation:
        anomaly = bool(zone and zone.kind is ZoneKind.RESTRICTED and det.label in self._restricted)
        reason = "restricted_class_in_restricted_zone" if anomaly else None
        if proximity:                                  # an image-space proximity heuristic, reported separately
            anomaly, reason = True, proximity
        x1, y1, x2, y2 = det.box
        return Observation(
            event_type=EventType.VISUAL_OBSERVATION,
            device_id=self.cfg.device_id,
            timestamp=now,
            source=self._source,
            object=det.label,
            confidence=det.confidence,
            zone=zone.name if zone else None,
            zone_kind=zone.kind if zone else None,
            bbox=BBox(x1=x1, y1=y1, x2=x2, y2=y2),
            anomaly=anomaly,
            anomaly_reason=reason,
            model=self._model,
            details={"anchor": self.cfg.zone_anchor, **(metrics or {})},
        )

    def _health_observation(self, now: datetime, t) -> Observation:
        anomaly = t.new is not CameraState.OK
        details = {"state": t.new.value, "previous_state": t.old.value, "reason": t.reason}
        if t.stats is not None:
            details["mean_brightness"] = round(t.stats.mean_brightness, 2)
            details["texture"] = round(t.stats.texture, 3)
        details.update(t.metrics)
        return Observation(
            event_type=EventType.CAMERA_HEALTH,
            device_id=self.cfg.device_id,
            timestamp=now,
            source=self._source,
            anomaly=anomaly,
            anomaly_reason=f"camera_{t.new.value}" if anomaly else None,
            details=details,
        )
