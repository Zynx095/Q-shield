import json

from ai.vision.camera import SequenceSource
from ai.vision.pipeline import VisionPipeline
from ai.vision.runner import run
from ai.vision.sinks import FanoutSink, HttpSink, JsonlSink, ListSink
from backend.protocol.observation import Observation
from tests.ai.helpers import Clock, FakeDetector, make_config, normal_frame, person


def obs():
    return Observation(event_type="visual_observation", device_id="DEVICE-001", timestamp="2026-01-01T00:00:00Z",
                       source="usb_webcam", object="person", confidence=0.9,
                       bbox={"x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}, anomaly=False)


def test_jsonl_sink_writes_valid_lines(tmp_path):
    path = tmp_path / "sub" / "o.jsonl"
    JsonlSink(path).emit(obs())
    JsonlSink(path).emit(obs())
    lines = path.read_text().splitlines()
    assert len(lines) == 2 and Observation(**json.loads(lines[0])).object == "person"


class FakeResp:
    def __init__(self, code):
        self.status_code = code


class FakeClient:
    def __init__(self, codes):
        self.codes, self.calls = list(codes), []

    def post(self, path, json, headers):
        self.calls.append((path, headers["Authorization"]))
        c = self.codes.pop(0) if self.codes else 200
        if isinstance(c, Exception):
            raise c
        return FakeResp(c)


def test_http_sink_posts_with_ingest_bearer():
    c = FakeClient([200])
    HttpSink("http://x", "tok", client=c).emit(obs())
    assert c.calls == [("/api/v1/observations", "Bearer tok")]


def test_http_sink_queues_during_outage_and_flushes_in_order():
    c = FakeClient([ConnectionError("down"), 200, 200])
    s = HttpSink("http://x", "tok", client=c)
    s.emit(obs())                 # fails, queued
    assert len(s._queue) == 1
    s.emit(obs())                 # retries first, then sends second
    assert len(s._queue) == 0 and len(c.calls) == 3


def test_http_sink_drops_rejected_and_bounds_queue():
    c = FakeClient([422])
    s = HttpSink("http://x", "tok", client=c)
    s.emit(obs())
    assert len(s._queue) == 0     # 4xx will never succeed: dropped, not retried forever
    c2 = FakeClient([ConnectionError("d")] * 50)
    s2 = HttpSink("http://x", "tok", client=c2, max_queue=3)
    for _ in range(5):
        s2.emit(obs())
    assert len(s2._queue) == 3 and s2.dropped == 2


def test_runner_processes_frames_and_fans_out():
    det = FakeDetector()
    det.next = [person(0.6, 0.1, 0.9, 0.9)]
    p = VisionPipeline(make_config(), det, Clock())
    a, b = ListSink(), ListSink()
    n = run(p, SequenceSource([normal_frame(i) for i in range(4)]), FanoutSink(a, b), target_fps=1000,
            max_frames=4, sleep=lambda s: None)
    assert n == 4 and len(a.items) == 1 and len(b.items) == 1


def test_runner_honours_stop_flag():
    p = VisionPipeline(make_config(), FakeDetector(), Clock())
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 2

    assert run(p, SequenceSource([normal_frame()] * 10), ListSink(), 1000, should_stop=stop, sleep=lambda s: None) == 2
