"""Real-model tests. Separable from the rest: `pytest -m "not inference"` skips them."""
from pathlib import Path

import numpy as np
import pytest

WEIGHTS = Path("ai/models/yolo11n.pt")
pytestmark = [pytest.mark.inference,
              pytest.mark.skipif(not WEIGHTS.is_file(), reason="weights not downloaded (see ai/README.md)")]


@pytest.fixture(scope="module")
def detector():
    from ai.vision.detector import YoloDetector
    return YoloDetector(str(WEIGHTS), "yolo11n", 0.4, 320, "cpu", ("person",))


def test_model_metadata_recorded(detector):
    assert detector.name == "yolo11n"
    assert detector.version.startswith("ultralytics-") and "weights-sha256:" in detector.version


def test_blank_frame_yields_no_person(detector):
    assert detector.detect(np.full((480, 640, 3), 127, dtype=np.uint8)) == []


def test_output_is_normalised_and_bounded(detector):
    rng = np.random.default_rng(0)
    for d in detector.detect(rng.integers(0, 255, (480, 640, 3), dtype=np.uint8)):
        x1, y1, x2, y2 = d.box
        assert 0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1 and 0.4 <= d.confidence <= 1.0


def test_unknown_class_rejected():
    from ai.vision.detector import YoloDetector
    with pytest.raises(ValueError):
        YoloDetector(str(WEIGHTS), "yolo11n", 0.4, 320, "cpu", ("unicorn",))


def test_missing_weights_message(tmp_path):
    from ai.vision.detector import YoloDetector
    with pytest.raises(FileNotFoundError):
        YoloDetector(str(tmp_path / "nope.pt"))
