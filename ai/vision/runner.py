"""Capture loop and measurement helpers."""
from __future__ import annotations

import platform
import statistics
import time
from typing import Callable

from ai.vision.camera import FrameSource
from ai.vision.detector import Detector
from ai.vision.pipeline import VisionPipeline
from ai.vision.sinks import ObservationSink


def run(pipeline: VisionPipeline, source: FrameSource, sink: ObservationSink, target_fps: float,
        max_frames: int | None = None, should_stop: Callable[[], bool] = lambda: False,
        sleep: Callable[[float], None] = time.sleep, monotonic: Callable[[], float] = time.monotonic) -> int:
    """Read frames, run the pipeline, emit observations. Returns the number of frames processed."""
    period = 1.0 / target_fps
    n = 0
    next_t = monotonic()
    while not should_stop() and (max_frames is None or n < max_frames):
        for obs in pipeline.process_frame(source.read()):
            sink.emit(obs)
        n += 1
        next_t += period
        delay = next_t - monotonic()
        if delay > 0:
            sleep(delay)
        else:
            next_t = monotonic()  # running slower than target: do not accumulate debt
    return n


def _stats(ms: list[float]) -> dict:
    s = sorted(ms)
    return {"mean": round(statistics.fmean(s), 2), "median": round(statistics.median(s), 2),
            "p95": round(s[min(len(s) - 1, int(0.95 * len(s)))], 2),
            "min": round(s[0], 2), "max": round(s[-1], 2)}


def benchmark(source: FrameSource, detector: Detector, frames: int = 100, warmup: int = 10) -> dict:
    """Measure real capture and inference time on the live source. Nothing is estimated."""
    read_ms, infer_ms, n_det, frame_shape = [], [], 0, None
    for _ in range(warmup):  # excluded: model/camera warm-up
        f = source.read()
        if f is not None:
            detector.detect(f)
    start = time.perf_counter()
    for _ in range(frames):
        t0 = time.perf_counter()
        f = source.read()
        t1 = time.perf_counter()
        if f is None:
            continue
        frame_shape = f.shape
        dets = detector.detect(f)
        t2 = time.perf_counter()
        read_ms.append((t1 - t0) * 1000)
        infer_ms.append((t2 - t1) * 1000)
        n_det += len(dets)
    elapsed = time.perf_counter() - start
    if not infer_ms:
        raise RuntimeError("no frames captured during benchmark")
    info = {"python": platform.python_version(), "machine": platform.machine(),
            "cpu": platform.processor(), "os": platform.platform()}
    try:
        import torch
        info["torch"] = torch.__version__
        info["cuda_available"] = torch.cuda.is_available()
    except Exception:
        pass
    return {
        "frames_measured": len(infer_ms), "frames_dropped": frames - len(infer_ms), "warmup_frames": warmup,
        "frame_shape": list(frame_shape) if frame_shape else None,
        "capture_ms": _stats(read_ms), "inference_ms": _stats(infer_ms),
        "end_to_end_fps": round(len(infer_ms) / elapsed, 2),
        "inference_only_fps": round(1000.0 / statistics.fmean(infer_ms), 2),
        "total_detections": n_det, "model": detector.name, "model_version": detector.version,
        "environment": info,
    }
