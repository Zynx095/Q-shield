from datetime import datetime, timedelta, timezone

import numpy as np

from ai.vision.config import VisionConfig, parse_config
from ai.vision.detector import Detection

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeDetector:
    name, version = "fake-detector", "0"

    def __init__(self):
        self.next: list[Detection] = []

    def detect(self, frame):
        return list(self.next)


class Clock:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t

    def advance(self, s: float):
        self.t += timedelta(seconds=s)


def normal_frame(seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).integers(60, 200, (48, 64, 3), dtype=np.uint8)


def dark_frame() -> np.ndarray:
    return np.zeros((48, 64, 3), dtype=np.uint8)


def flat_frame() -> np.ndarray:
    return np.full((48, 64, 3), 120, dtype=np.uint8)


def make_config(**over) -> VisionConfig:
    data = {
        "device_id": "DEVICE-001",
        "zones": [
            {"name": "restricted_zone", "kind": "restricted", "polygon": [[0.5, 0], [1, 0], [1, 1], [0.5, 1]]},
            {"name": "monitored_zone", "kind": "monitored", "polygon": [[0, 0], [0.5, 0], [0.5, 1], [0, 1]]},
        ],
        "health": {"consecutive_frames": 3, "source_lost_after_failures": 3},
        "emit": {"repeat_interval_s": 5, "absence_gap_s": 2, "outside_zones": True},
    }
    data.update(over)
    return parse_config(data)


def person(x1, y1, x2, y2, conf=0.9, label="person") -> Detection:
    return Detection(label, conf, (x1, y1, x2, y2))
