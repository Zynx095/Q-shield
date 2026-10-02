"""The camera as part of the security boundary, end to end: real vision pipeline -> ML-DSA signature -> gateway ->
trust engine -> enforcement. Frames are synthetic; the signature, gateway and trust engine are the real ones."""
import numpy as np

from ai.vision.config import parse_config
from ai.vision.pipeline import VisionPipeline
from ai.vision.signed_sink import SignedHttpSink
from tests.ai.helpers import FakeDetector
from tests.fullstack.conftest import state, trusted
from tests.pqc_helpers import now_dt


def trust(s):
    return s.op.get("/api/v1/trust/DEVICE-001").json()


def test_camera_covered_alone_lowers_trust_but_never_quarantines(stack):
    trusted(stack)
    r = stack.sim.camera_interference("obstructed", "dark_frame")
    assert r.http_status == [200] and r.detected
    t = trust(stack)
    assert t["state"] != "QUARANTINED" and t["incident"] is None and t["score"] < 100


def test_camera_turned_away_then_enclosure_opened_quarantines(stack):
    trusted(stack)
    r = stack.sim.blinded_tamper("view_changed", "viewpoint_shift")
    assert r.http_status == [200, 200] and r.detected
    t = trust(stack)
    assert t["state"] == "QUARANTINED" and t["incident"]["class"] == "confirmed_incident"
    assert t["incident"]["modalities"] == ["PHYSICAL", "VISUAL"]
    assert stack.agent.telemetry().status_code == 403                 # enforcement: normal channel blocked


def test_real_pipeline_frozen_feed_reaches_the_trust_engine_signed(stack, pqc_world, clock):
    """Frozen frames through the real pipeline and the real ML-DSA sink: the gateway stores a signed 'frozen' report,
    the trust engine scores it, and with a tamper report it confirms an incident."""
    trusted(stack)
    cfg = parse_config({"device_id": "DEVICE-001", "health": {"consecutive_frames": 3}})
    def tick():                                                         # 5 fps on the gateway's own clock
        clock.advance(0.2)
        return now_dt(clock)
    pipe = VisionPipeline(cfg, FakeDetector(), tick)
    sink = SignedHttpSink("http://test", pqc_world.backend, "vision-1", "usb_webcam:0", pqc_world.signers["vision-1"],
                          client=stack.gw, now=lambda: now_dt(clock))
    rng = np.random.default_rng(4)
    scene = rng.integers(40, 220, (120, 160)).astype(np.float64)
    for _ in range(15):                                                 # live frames: the reference view is learned
        for o in pipe.process_frame(np.clip(scene + rng.normal(0, 2, scene.shape), 0, 255).astype(np.uint8)):
            sink.emit(o)
    still = np.clip(scene + rng.normal(0, 2, scene.shape), 0, 255).astype(np.uint8)
    for _ in range(40):                                                 # 8 s of the very same frame
        for o in pipe.process_frame(still):
            sink.emit(o)
    obs = stack.op.get("/api/v1/observations").json()
    (frozen,) = [o for o in obs if o["event_type"] == "camera_health"]
    assert frozen["details"]["state"] == "frozen" and frozen["auth"] == "ML-DSA-65:vision-1"
    stack.trust.process_pending()
    t = trust(stack)
    assert t["factors"]["visual"]["penalty"] == 60 and t["state"] != "QUARANTINED"
    assert stack.agent.telemetry(tamper=True).status_code == 200
    assert state(stack) == "QUARANTINED"
