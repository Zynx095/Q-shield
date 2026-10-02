"""Image-space proximity heuristics: a subject too close to the camera, or approaching it fast.

There is no depth sensor and no calibration, so this measures NO distance. It uses the share of the frame a
detected subject's bounding box covers, and how fast that share grows:

  subject_too_close  the largest box of a watched class covers at least `close_area_fraction` of the frame for
                     `close_frames` frames in a row (someone at the lens, about to cover or move the camera);
  rapid_approach     within `approach_window_s`, the box area grew by `approach_growth` times or more and now
                     covers at least `approach_min_area_fraction` (someone walking straight at the camera).

Both are reported as visual observations with `anomaly_reason` set and the measured values in `details`, labelled
as image-space heuristics. A large box can also mean a large subject far away, or a wide-angle lens; the thresholds
are UNVALIDATED defaults. The gateway's trust engine gives them a low weight and never acts on them alone.
"""
from __future__ import annotations

from collections import deque

from ai.vision.config import ProximityConfig

HEURISTIC = "image-space proxy (bounding-box share of the frame); not a distance measurement"


def area(box) -> float:
    x1, y1, x2, y2 = box
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


class ProximityTracker:
    def __init__(self, cfg: ProximityConfig):
        self.cfg = cfg
        self._history: deque[tuple[float, float]] = deque()   # (t, largest area) for frames with a watched subject
        self._close_streak = 0
        self._close_reported = False
        self._approach_armed = True

    def update(self, now: float, detections) -> list[tuple[str, object, dict]]:
        """detections: Detection objects already filtered by class of interest and confidence.
        Returns [(reason, detection, metrics)] for the events to report in this frame."""
        cfg = self.cfg
        if not cfg.enabled:
            return []
        watched = [d for d in detections if d.label in cfg.classes]
        if not watched:
            self._close_streak, self._close_reported, self._approach_armed = 0, False, True
            self._history.clear()
            return []
        subject = max(watched, key=lambda d: area(d.box))
        a = area(subject.box)
        occupancy = min(1.0, sum(area(d.box) for d in detections))
        out = []

        self._history.append((now, a))
        while self._history and now - self._history[0][0] > cfg.approach_window_s:
            self._history.popleft()

        if a >= cfg.close_area_fraction:
            self._close_streak += 1
            if self._close_streak >= cfg.close_frames and not self._close_reported:
                self._close_reported = True
                out.append(("subject_too_close", subject, {"area_fraction": round(a, 3), "occupancy": round(occupancy, 3),
                                                           "frames": self._close_streak, "heuristic": HEURISTIC}))
        elif a < 0.8 * cfg.close_area_fraction:                       # hysteresis: a new episode needs a clear retreat
            self._close_streak, self._close_reported = 0, False

        if a < cfg.approach_min_area_fraction:
            self._approach_armed = True
        elif self._approach_armed and len(self._history) >= 2:
            t0, smallest = min(self._history, key=lambda h: h[1])
            if smallest > 0 and a / smallest >= cfg.approach_growth and t0 < now:
                self._approach_armed = False
                out.append(("rapid_approach", subject, {"area_fraction": round(a, 3), "growth": round(a / smallest, 2),
                                                        "over_s": round(now - t0, 2), "occupancy": round(occupancy, 3),
                                                        "heuristic": HEURISTIC}))
        return out
