"""Vision pipeline with a fake detector: no model, no camera, no backend."""
import subprocess
import sys

from ai.vision.pipeline import VisionPipeline
from backend.protocol.observation import EventType
from tests.ai.helpers import Clock, FakeDetector, dark_frame, flat_frame, make_config, normal_frame, person


def setup(**cfg_over):
    det, clock = FakeDetector(), Clock()
    return VisionPipeline(make_config(**cfg_over), det, clock), det, clock


def visual(obs):
    return [o for o in obs if o.event_type is EventType.VISUAL_OBSERVATION]


def test_person_in_restricted_zone_is_flagged_anomaly():
    p, det, _ = setup()
    det.next = [person(0.6, 0.1, 0.9, 0.9)]
    (o,) = p.process_frame(normal_frame())
    assert (o.object, o.zone, o.zone_kind.value, o.anomaly) == ("person", "restricted_zone", "restricted", True)
    assert o.anomaly_reason == "restricted_class_in_restricted_zone"
    assert o.confidence == 0.9 and o.device_id == "DEVICE-001" and o.source.value == "usb_webcam"
    assert o.model.name == "fake-detector"


def test_person_in_monitored_zone_is_not_anomaly():
    p, det, _ = setup()
    det.next = [person(0.1, 0.1, 0.4, 0.9)]
    (o,) = p.process_frame(normal_frame())
    assert o.zone == "monitored_zone" and o.anomaly is False and o.anomaly_reason is None


def test_non_restricted_class_in_restricted_zone_not_anomaly():
    p, det, _ = setup(model={"classes_of_interest": ["person", "dog"]})
    det.next = [person(0.6, 0.1, 0.9, 0.9, label="dog")]
    (o,) = p.process_frame(normal_frame())
    assert o.zone_kind.value == "restricted" and o.anomaly is False


def test_outside_zones_configurable():
    p, det, _ = setup(zones=[{"name": "r", "kind": "restricted", "polygon": [[0, 0], [0.2, 0], [0.2, 0.2], [0, 0.2]]}])
    det.next = [person(0.6, 0.1, 0.9, 0.9)]
    (o,) = p.process_frame(normal_frame())
    assert o.zone is None and o.zone_kind is None and o.anomaly is False
    p2, det2, _ = setup(zones=[{"name": "r", "kind": "restricted", "polygon": [[0, 0], [0.2, 0], [0.2, 0.2], [0, 0.2]]}],
                        emit={"outside_zones": False})
    det2.next = [person(0.6, 0.1, 0.9, 0.9)]
    assert p2.process_frame(normal_frame()) == []


def test_classes_not_of_interest_and_low_confidence_ignored():
    p, det, _ = setup()
    det.next = [person(0.6, 0.1, 0.9, 0.9, label="chair"), person(0.6, 0.1, 0.9, 0.9, conf=0.2)]
    assert p.process_frame(normal_frame()) == []


def test_repeat_suppression_and_reemission():
    p, det, clock = setup()
    det.next = [person(0.6, 0.1, 0.9, 0.9)]
    assert len(p.process_frame(normal_frame())) == 1
    for _ in range(4):                       # continuing sighting inside the 5 s repeat interval
        clock.advance(1)
        assert p.process_frame(normal_frame()) == []
    clock.advance(1)                         # 5 s since last emit
    assert len(p.process_frame(normal_frame())) == 1


def test_reappearance_after_absence_emits_immediately():
    p, det, clock = setup()
    det.next = [person(0.6, 0.1, 0.9, 0.9)]
    assert len(p.process_frame(normal_frame())) == 1
    det.next = []
    clock.advance(3)                         # unseen longer than absence_gap_s (2 s)
    p.process_frame(normal_frame())
    det.next = [person(0.6, 0.1, 0.9, 0.9)]
    clock.advance(0.5)
    assert len(p.process_frame(normal_frame())) == 1


def test_one_observation_per_object_zone_keeps_highest_confidence():
    p, det, _ = setup()
    det.next = [person(0.6, 0.1, 0.8, 0.9, conf=0.5), person(0.7, 0.1, 0.9, 0.9, conf=0.95)]
    (o,) = p.process_frame(normal_frame())
    assert o.confidence == 0.95


def test_same_object_in_two_zones_gives_two_observations():
    p, det, _ = setup()
    det.next = [person(0.6, 0.1, 0.9, 0.9), person(0.1, 0.1, 0.4, 0.9)]
    assert {o.zone for o in p.process_frame(normal_frame())} == {"restricted_zone", "monitored_zone"}


def test_camera_obstruction_reported_once_then_restored():
    p, _, _ = setup()
    out = []
    for _ in range(3):                       # consecutive_frames = 3 in the test config
        out += p.process_frame(dark_frame())
    (o,) = out
    assert o.event_type is EventType.CAMERA_HEALTH and o.anomaly and o.details["state"] == "obstructed"
    assert o.details["reason"] == "dark_frame" and o.object is None and o.confidence is None
    assert p.process_frame(dark_frame()) == []           # no repeat while state unchanged
    out = []
    for _ in range(3):
        out += p.process_frame(normal_frame())
    (r,) = out
    assert r.details["state"] == "ok" and r.anomaly is False


def test_flat_frame_counts_as_obstruction():
    p, _, _ = setup()
    out = []
    for _ in range(3):
        out += p.process_frame(flat_frame())
    assert out[0].details["reason"] == "flat_frame"


def test_single_bad_frame_does_not_flap():
    p, _, _ = setup()
    assert p.process_frame(dark_frame()) == []
    assert p.process_frame(normal_frame()) == []
    assert p.process_frame(dark_frame()) == []


def test_source_lost_and_recovery():
    p, _, _ = setup()
    out = []
    for _ in range(3):                       # source_lost_after_failures = 3
        out += p.process_frame(None)
    (o,) = out
    assert o.details["state"] == "source_lost" and o.anomaly and o.anomaly_reason == "camera_source_lost"
    out = []
    for _ in range(3):
        out += p.process_frame(normal_frame())
    assert out[-1].details["state"] == "ok"


def test_pipeline_output_carries_no_trust_decision():
    p, det, _ = setup()
    det.next = [person(0.6, 0.1, 0.9, 0.9)]
    (o,) = p.process_frame(normal_frame())
    wire = str(o.to_wire()).lower()
    assert "trust" not in wire and "compromis" not in wire


def test_vision_package_is_independent_of_backend_service_and_heavy_libs():
    """The pipeline may use only the pure observation schema from backend; no API/DB and no model libs."""
    code = (
        "import sys, ai.vision.pipeline, ai.vision.sinks, ai.vision.runner\n"
        "bad = [m for m in ('fastapi','sqlite3','torch','ultralytics','cv2','backend.api','backend.devices') if m in sys.modules]\n"
        "print(bad)\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=".")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[]", r.stdout
