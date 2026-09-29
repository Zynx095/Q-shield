"""Camera health from raw frames: dark/flat frames (lens covered) and lost source.

Simple, transparent statistics only. Thresholds in config are UNVALIDATED defaults: they
must be checked against the real camera and lighting before being relied on. A state
change is reported only after `consecutive_frames` agreeing frames, to avoid flapping.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ai.vision.config import HealthConfig
from backend.protocol.observation import CameraState


@dataclass(frozen=True)
class FrameStats:
    mean_brightness: float  # 0..255
    texture: float          # mean |horizontal neighbour difference| on a 4x downsample; ~0 for a flat image


@dataclass(frozen=True)
class Transition:
    old: CameraState
    new: CameraState
    reason: str
    stats: FrameStats | None


def frame_stats(frame: np.ndarray) -> FrameStats:
    gray = frame.astype(np.float32)
    if gray.ndim == 3:
        gray = gray.mean(axis=2)
    small = gray[::4, ::4]
    texture = float(np.abs(np.diff(small, axis=1)).mean()) if small.shape[1] > 1 else 0.0
    return FrameStats(float(gray.mean()), texture)


class CameraHealthMonitor:
    def __init__(self, cfg: HealthConfig):
        self._cfg = cfg
        self.state = CameraState.OK
        self._fail_streak = 0
        self._target = CameraState.OK
        self._target_streak = 0

    def update(self, frame: np.ndarray | None) -> Transition | None:
        cfg = self._cfg
        if frame is None:
            self._fail_streak += 1
            self._target_streak = 0
            if self._fail_streak >= cfg.source_lost_after_failures and self.state is not CameraState.SOURCE_LOST:
                return self._move(CameraState.SOURCE_LOST, "no_frames", None)
            return None

        self._fail_streak = 0
        stats = frame_stats(frame)
        reason = ""
        if stats.mean_brightness < cfg.dark_mean_below:
            target, reason = CameraState.OBSTRUCTED, "dark_frame"
        elif stats.texture < cfg.flat_texture_below:
            target, reason = CameraState.OBSTRUCTED, "flat_frame"
        else:
            target = CameraState.OK

        if target is self._target:
            self._target_streak += 1
        else:
            self._target, self._target_streak = target, 1
        if target is not self.state and self._target_streak >= cfg.consecutive_frames:
            return self._move(target, reason or "normal_frames", stats)
        return None

    def _move(self, new: CameraState, reason: str, stats: FrameStats | None) -> Transition:
        t = Transition(self.state, new, reason, stats)
        self.state = new
        return t
