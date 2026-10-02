"""The camera as part of the security boundary: occlusion, tamper, viewpoint, frozen feed, degraded image, proximity.

Synthetic but realistic frames: a structured scene with fixed fine detail, plus fresh sensor noise in every frame (a
live camera never repeats a frame exactly). The pipeline clock advances 0.2 s per frame (5 fps). No model, no camera.
"""
import time

import numpy as np

from ai.vision.config import HealthConfig
from ai.vision.health import CameraHealthMonitor
from ai.vision.pipeline import VisionPipeline
from backend.protocol.observation import EventType
from tests.ai.helpers import FakeDetector, TickClock, make_config, person

H, W = 240, 320


def world(seed: int, scale: int = 2) -> np.ndarray:
    """A scene larger than the view, so the camera can be turned within it."""
    rng = np.random.default_rng(seed)
    hh, ww = H * scale, W * scale
    yy, xx = np.mgrid[0:hh, 0:ww]
    img = 70 + 50 * (xx / ww) + 30 * (yy / hh)
    for _ in range(40):
        y0, x0 = rng.integers(0, hh - 30), rng.integers(0, ww - 30)
        img[y0:y0 + rng.integers(20, 90), x0:x0 + rng.integers(20, 90)] += rng.integers(-60, 70)
    img += rng.normal(0, 25, img.shape)              # fixed fine detail (texture of the scene, not sensor noise)
    return np.clip(img, 0, 255)


WORLD = world(1)
OTHER = world(7)
NOISE = np.random.default_rng(11)


def view(src=WORLD, dx=0, dy=0, gain=1.0, offset=0.0, noise=2.0, rng=NOISE) -> np.ndarray:
    y0, x0 = H // 2 + dy, W // 2 + dx
    img = src[y0:y0 + H, x0:x0 + W] * gain + offset
    if noise:
        img = img + rng.normal(0, noise, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def rotated(deg: float) -> np.ndarray:
    a = np.deg2rad(deg)
    yy, xx = np.mgrid[0:H, 0:W]
    cy, cx = H / 2, W / 2
    sy = (np.cos(a) * (yy - cy) - np.sin(a) * (xx - cx) + cy + H // 2).astype(int).clip(0, 2 * H - 1)
    sx = (np.sin(a) * (yy - cy) + np.cos(a) * (xx - cx) + cx + W // 2).astype(int).clip(0, 2 * W - 1)
    return np.clip(WORLD[sy, sx] + NOISE.normal(0, 2, (H, W)), 0, 255).astype(np.uint8)       # fresh sensor noise


def blurred(k: int = 15) -> np.ndarray:
    img = view(noise=0).astype(np.float32)
    kernel = np.ones(k) / k
    img = np.apply_along_axis(lambda r: np.convolve(r, kernel, mode="same"), 1, img)
    img = np.apply_along_axis(lambda c: np.convolve(c, kernel, mode="same"), 0, img)
    return np.clip(img + NOISE.normal(0, 2, img.shape), 0, 255).astype(np.uint8)


def covered() -> np.ndarray:
    return np.clip(np.abs(np.random.default_rng().normal(0, 2, (H, W))), 0, 255).astype(np.uint8)


def setup():
    det, clock = FakeDetector(), TickClock(0.2)
    p = VisionPipeline(make_config(), det, clock)
    return p, det


def feed(p, make, seconds: float) -> list:
    out = []
    for _ in range(int(round(seconds / 0.2))):
        out += p.process_frame(make() if callable(make) else make)
    return out


def health(out) -> list[tuple[str, str]]:
    return [(o.details["state"], o.details["reason"]) for o in out if o.event_type is EventType.CAMERA_HEALTH]


def learned(p):
    assert feed(p, view, 3) == []                    # 15 healthy frames: the reference view is learned, nothing reported
    assert p.health.baseline_ready
    return p


# ---------------------------------------------------------------- normal operation
def test_normal_scene_reports_nothing_and_learns_the_reference():
    p, _ = setup()
    learned(p)
    assert health(feed(p, view, 20)) == []


def test_moderate_lighting_change_is_not_an_event():
    """Lights dimmed to half, or brightened: the scene's structure is unchanged, so nothing is reported."""
    p, _ = setup()
    learned(p)
    assert health(feed(p, lambda: view(gain=0.5), 10)) == []
    assert health(feed(p, lambda: view(gain=1.25, offset=10), 10)) == []


# ---------------------------------------------------------------- A: occlusion vs lighting
def test_sustained_occlusion_is_reported_but_a_brief_one_is_not():
    p, _ = setup()
    learned(p)
    assert health(feed(p, covered, 1.0)) == []                    # a hand passing the lens for 1 s
    assert health(feed(p, view, 2)) == []
    out = health(feed(p, covered, 4))                             # covered and kept covered
    assert out == [("obstructed", "dark_frame")]
    assert health(feed(p, view, 3)) == [("ok", "normal_frames")]  # uncovered: restored


def test_dark_room_with_the_scene_still_visible_is_low_light_not_a_covered_lens():
    p, _ = setup()
    learned(p)
    out = feed(p, lambda: view(gain=0.06, noise=1.0), 4)          # mean gray ~8: under the dark threshold
    (o,) = [x for x in out if x.event_type is EventType.CAMERA_HEALTH]
    assert (o.details["state"], o.details["reason"]) == ("degraded", "low_light")
    assert o.details["similarity"] >= 0.6 and o.anomaly and o.anomaly_reason == "camera_degraded"


def test_blinding_light_is_an_obstruction():
    p, _ = setup()
    learned(p)
    assert health(feed(p, lambda: view(gain=0.1, offset=232), 4)) == [("obstructed", "overexposed_frame")]


# ---------------------------------------------------------------- B/C: viewpoint and physical tamper
def test_camera_turned_is_a_viewpoint_shift_with_its_direction():
    p, _ = setup()
    learned(p)
    out = [o for o in feed(p, lambda: view(dx=60), 4) if o.event_type is EventType.CAMERA_HEALTH]
    (o,) = out
    assert (o.details["state"], o.details["reason"]) == ("view_changed", "viewpoint_shift")
    # the camera turned right by 60 px, so the scene moved LEFT in the image by 60/320 of the frame
    assert abs(o.details["shift_x"] + 60 / W) <= 0.04 and abs(o.details["shift_y"]) <= 0.04
    assert health(feed(p, view, 3)) == [("ok", "normal_frames")]  # turned back: restored


def test_camera_tilted_or_rotated_is_a_view_change():
    for deg in (15, -20, 30):
        p, _ = setup()
        learned(p)
        out = health(feed(p, lambda: rotated(deg), 4))
        assert [s for s, _ in out] == ["view_changed"], (deg, out)


def test_camera_tilted_down_is_a_viewpoint_shift():
    p, _ = setup()
    learned(p)
    (o,) = [x for x in feed(p, lambda: view(dy=40), 4) if x.event_type is EventType.CAMERA_HEALTH]
    assert (o.details["state"], o.details["reason"]) == ("view_changed", "viewpoint_shift")
    assert o.details["shift_y"] < -0.1 and abs(o.details["shift_x"]) <= 0.04


def test_camera_pointed_somewhere_else_is_scene_replaced():
    p, _ = setup()
    learned(p)
    assert health(feed(p, lambda: view(OTHER), 4)) == [("view_changed", "scene_replaced")]


def test_small_vibration_or_a_slight_nudge_is_not_a_viewpoint_change():
    p, _ = setup()
    learned(p)
    rng = np.random.default_rng(3)
    assert health(feed(p, lambda: view(dx=int(rng.integers(-3, 4)), dy=int(rng.integers(-2, 3))), 10)) == []
    assert health(feed(p, lambda: view(dx=10), 6)) == []           # nudged 3% of the frame and left there
    assert health(feed(p, lambda: rotated(5), 6)) == []             # or rotated 5 degrees


def test_a_person_walking_through_the_view_is_not_a_moved_camera():
    """A large figure crossing the frame, reported by the detector, is masked out of the viewpoint check."""
    p, det = setup()
    learned(p)
    out = []
    for step in range(20):
        x = 0.05 + step * 0.03
        frame = view().copy()
        frame[20:230, int(x * W):int((x + 0.35) * W)] = 30            # a dark figure covering 35% of the width
        det.next = [person(x, 0.08, x + 0.35, 0.96, conf=0.9)]
        out += p.process_frame(frame)
    assert health(out) == []


def test_feed_interrupted_or_unplugged_is_source_lost():
    p, _ = setup()
    learned(p)
    assert health(feed(p, None, 4)) == [("source_lost", "no_frames")]
    assert health(feed(p, view, 3)) == [("ok", "normal_frames")]


def test_camera_facing_a_blank_wall_is_reported():
    p, _ = setup()
    learned(p)
    wall = lambda: np.clip(160 + np.random.default_rng().normal(0, 2, (H, W)), 0, 255).astype(np.uint8)  # noqa: E731
    (state, _), = health(feed(p, wall, 4))
    assert state in ("view_changed", "obstructed")


# ---------------------------------------------------------------- E: absurd change
def test_frozen_feed_is_reported():
    p, _ = setup()
    learned(p)
    still = view()
    out = health(feed(p, still, 8))
    assert out == [("frozen", "identical_frames")]
    assert health(feed(p, view, 3)) == [("ok", "normal_frames")]


def test_extreme_blur_is_degraded():
    p, _ = setup()
    learned(p)
    out = [o for o in feed(p, blurred, 4) if o.event_type is EventType.CAMERA_HEALTH]
    (o,) = out
    assert (o.details["state"], o.details["reason"]) == ("degraded", "blurred")
    assert o.details["sharpness_ratio"] < 0.2


def test_health_reports_carry_measurements_not_conclusions():
    p, _ = setup()
    learned(p)
    (o,) = [x for x in feed(p, lambda: view(OTHER), 4) if x.event_type is EventType.CAMERA_HEALTH]
    assert {"similarity", "shift_peak", "masked_cells", "held_s", "mean_brightness", "texture"} <= set(o.details)
    assert o.details["held_s"] >= 2.0
    wire = str(o.to_wire()).lower()
    assert "trust" not in wire and "compromis" not in wire


# ---------------------------------------------------------------- D: proximity (image-space heuristics)
def _approach(p, det, areas, step_frames=1):
    out = []
    for a in areas:
        side = a ** 0.5
        det.next = [person(0.5 - side / 2, 0.5 - side / 2, 0.5 + side / 2, 0.5 + side / 2, conf=0.88)]
        for _ in range(step_frames):
            out += p.process_frame(view())
    return [o for o in out if o.anomaly_reason in ("subject_too_close", "rapid_approach")]


def test_rapid_approach_is_reported_as_an_image_space_heuristic():
    p, det = setup()
    learned(p)
    out = _approach(p, det, [0.03, 0.05, 0.08, 0.13, 0.2])            # area x6.7 in 0.8 s
    assert [o.anomaly_reason for o in out] == ["rapid_approach"]
    d = out[0].details
    assert d["growth"] >= 2.0 and d["area_fraction"] >= 0.12 and d["over_s"] <= 2.0
    assert "not a distance measurement" in d["heuristic"]
    assert out[0].object == "person" and out[0].confidence == 0.88 and out[0].anomaly


def test_slow_approach_is_not_rapid_and_too_close_is_reported_once():
    p, det = setup()
    learned(p)
    areas = [0.03 * 1.12 ** i for i in range(22)]                     # grows 12% per second, ends at ~0.33..0.36
    out = _approach(p, det, areas + [0.4, 0.42, 0.45, 0.44, 0.43], step_frames=5)
    assert [o.anomaly_reason for o in out] == ["subject_too_close"]
    assert out[0].details["area_fraction"] >= 0.35


def test_a_close_subject_the_detector_keeps_missing_is_one_episode():
    """Regression (USB camera, Phase 17): a seated person at ~37% of the frame, missed by the detector in some frames
    and with a jittering box, was reported as 'too close' 25 times in 90 s. It is one episode."""
    p, det = setup()
    learned(p)
    rng = np.random.default_rng(9)
    out = []
    for i in range(150):                                              # 30 s at 5 fps
        a = float(rng.uniform(0.3, 0.45))
        side = a ** 0.5
        det.next = [] if rng.random() < 0.3 else [person(0.5 - side / 2, 0.02, 0.5 + side / 2, 0.02 + side, conf=0.5)]
        out += p.process_frame(view())
    assert [o.anomaly_reason for o in out if o.anomaly_reason == "subject_too_close"] == ["subject_too_close"]
    det.next = []
    assert [o for o in feed(p, view, 4) if o.anomaly_reason] == []      # leaves: nothing reported...
    out = _approach(p, det, [0.4, 0.42, 0.41])                       # ...and comes back close: a new episode
    assert [o.anomaly_reason for o in out] == ["subject_too_close"]


def test_a_far_subject_is_never_a_proximity_event():
    p, det = setup()
    learned(p)
    assert _approach(p, det, [0.02, 0.03, 0.02, 0.04] * 5) == []


def test_proximity_can_be_disabled_by_config():
    det = FakeDetector()
    p = VisionPipeline(make_config(proximity={"enabled": False}), det, TickClock(0.2))
    learned(p)
    assert _approach(p, det, [0.03, 0.08, 0.2, 0.4, 0.5]) == []


# ---------------------------------------------------------------- monitor-level guarantees
def test_monitor_without_timestamps_falls_back_to_frame_counts():
    m = CameraHealthMonitor(HealthConfig(consecutive_frames=3))
    dark = np.zeros((48, 64), np.uint8)
    assert [m.update(dark) is not None for _ in range(3)] == [False, False, True]


def test_health_checks_do_not_slow_the_normal_path():
    m = CameraHealthMonitor(HealthConfig())
    frame = np.dstack([view(noise=2.0)] * 3)
    big = np.kron(frame, np.ones((2, 2, 1), np.uint8))              # 480x640, the configured camera size
    for t in range(12):
        m.update(big, t * 0.2)
    t0 = time.perf_counter()
    for t in range(12, 62):
        m.update(big, t * 0.2)
    per_frame_ms = (time.perf_counter() - t0) / 50 * 1000
    assert per_frame_ms < 15, per_frame_ms                            # vs ~100+ ms of YOLO11n inference on CPU
