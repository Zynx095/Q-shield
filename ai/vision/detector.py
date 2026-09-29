"""Object detectors behind a replaceable interface.

The pipeline only sees `Detector`, so the YOLO model can be swapped (e.g. for a permissively
licensed one) without touching the rest. Heavy imports (ultralytics, torch) are lazy.
A detector reports what it sees; it does not judge whether anything is a threat.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

Box = tuple[float, float, float, float]  # normalized x1, y1, x2, y2


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    box: Box


class Detector(Protocol):
    name: str
    version: str

    def detect(self, frame) -> list[Detection]: ...


class YoloDetector:
    """Ultralytics YOLO. NOTE: the `ultralytics` package and the official weights are
    AGPL-3.0. See ai/README.md and docs/technical-decisions.md (TD-11) before distributing."""

    def __init__(self, weights_path: str, name: str = "yolo11n", conf_threshold: float = 0.4,
                 imgsz: int = 640, device: str = "cpu", classes_of_interest: tuple[str, ...] = ("person",)):
        import ultralytics
        from ultralytics import YOLO

        path = Path(weights_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"model weights not found at {path}. Download the official weights once "
                f"(see ai/README.md); they are not committed to the repository."
            )
        self._model = YOLO(str(path))
        self.name = name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        self.version = f"ultralytics-{ultralytics.__version__}+weights-sha256:{digest}"
        self._conf, self._imgsz, self._device = conf_threshold, imgsz, device
        names = self._model.names  # {class_id: label}
        wanted = set(classes_of_interest)
        missing = wanted - set(names.values())
        if missing:
            raise ValueError(f"classes not in model vocabulary: {sorted(missing)}")
        self._class_ids = [i for i, n in names.items() if n in wanted]
        self._names = names

    def detect(self, frame) -> list[Detection]:
        result = self._model.predict(frame, conf=self._conf, imgsz=self._imgsz, device=self._device,
                                     classes=self._class_ids, verbose=False)[0]
        out: list[Detection] = []
        for cls, conf, xyxyn in zip(result.boxes.cls.tolist(), result.boxes.conf.tolist(),
                                    result.boxes.xyxyn.tolist()):
            x1, y1, x2, y2 = (min(1.0, max(0.0, v)) for v in xyxyn)
            if x2 > x1 and y2 > y1:  # drop degenerate boxes
                out.append(Detection(self._names[int(cls)], float(conf), (x1, y1, x2, y2)))
        return out
