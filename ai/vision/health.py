"""Camera health from raw frames: the camera is part of the security boundary.

States (backend.protocol.observation.CameraState). A change is reported only after the new state has held for
`consecutive_frames` frames AND `sustain_s` seconds, so a flicker, a passing hand or a brief exposure swing is not
reported (`source_lost` counts failed reads instead):

  obstructed    no usable image. `dark_frame`: dark with none of the reference scene left (lens covered);
                `flat_frame`: no texture (covered by something lit, or facing a blank surface);
                `overexposed_frame`: blinded by a light.
  source_lost   no frames at all for `source_lost_after_failures` reads (unplugged, driver failure).
  frozen        the same frame again and again (`identical_frames`): a stuck driver, or a looped or substituted
                feed. A live sensor always shows some noise between frames.
  view_changed  the scene no longer matches the reference view learned at start: the camera was turned, tilted,
                knocked or pointed elsewhere. `viewpoint_shift`: the old scene is still found, translated (`shift_x`
                and `shift_y` say how far the scene moved in the image, as a share of the frame; negative x = moved
                left, i.e. the camera turned right); `scene_replaced`: nothing of the old scene is left (pointed
                elsewhere, or a different feed); `view_altered`: neither (rotated, partly re-aimed, or a large object
                placed in front). Boxes the detector reports are masked out first, so a person walking through the
                view is not a viewpoint change; a small bump or vibration is not one either.
  degraded      the camera still sees, poorly. `low_light`: dark, but the reference structure is still there (a
                lighting change, not a covered lens). `blurred`: fine detail lost while coarse structure remains
                (defocus, smear, condensation).
  ok            none of the above.

How the measures work (all on small grayscale images; no learned model):
  * brightness and texture: mean gray level and mean |neighbour difference| (as before);
  * structure: a 32x24 block-averaged thumbnail compared with the reference by normalised cross-correlation over the
    cells (of a 4x4 grid) that no detection overlaps, so a global lighting change (gain or offset) does not register;
    and by phase correlation for a whole-image shift;
  * sharpness: variance of the Laplacian, as a share of the reference's;
  * frozen: mean |difference| between consecutive frames.
The reference view is the average of the first `baseline_frames` healthy frames (start the service with the view as
it should be; `rebaseline()` learns it again). Every threshold is an UNVALIDATED default: check it against the real
camera and scene before relying on it. Nothing here decides trust: the gateway's trust engine does, with other evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ai.vision.config import HealthConfig
from backend.protocol.observation import CameraState

THUMB_W, THUMB_H = 32, 24
GRID = 4                      # GRID x GRID cells, for masking detections out of the comparison
MIN_VALID_CELLS = 6           # fewer unmasked cells than this: too little background to judge the viewpoint
SCENE_GONE_BELOW = 0.2        # similarity under which nothing of the reference scene is left


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
    metrics: dict = field(default_factory=dict)


def _gray(frame: np.ndarray) -> np.ndarray:
    g = frame.astype(np.float32)
    return g.mean(axis=2) if g.ndim == 3 else g


def frame_stats(frame: np.ndarray) -> FrameStats:
    return _stats(_gray(frame)[::4, ::4])


def _stats(small: np.ndarray) -> FrameStats:
    texture = float(np.abs(np.diff(small, axis=1)).mean()) if small.shape[1] > 1 else 0.0
    return FrameStats(float(small.mean()), texture)


def _thumb(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape
    if h >= THUMB_H and w >= THUMB_W:
        by, bx = h // THUMB_H, w // THUMB_W
        return gray[: by * THUMB_H, : bx * THUMB_W].reshape(THUMB_H, by, THUMB_W, bx).mean(axis=(1, 3))
    rows = np.linspace(0, h - 1, THUMB_H).astype(int)
    cols = np.linspace(0, w - 1, THUMB_W).astype(int)
    return gray[np.ix_(rows, cols)]


def _normalise(t: np.ndarray) -> np.ndarray | None:
    sd = float(t.std())
    return None if sd < 1e-3 else (t - t.mean()) / sd


def _sharpness(small: np.ndarray) -> float:
    if small.shape[0] < 3 or small.shape[1] < 3:
        return 0.0
    lap = 4 * small[1:-1, 1:-1] - small[:-2, 1:-1] - small[2:, 1:-1] - small[1:-1, :-2] - small[1:-1, 2:]
    return float(lap.var())


_WINDOW = np.outer(np.hanning(THUMB_H), np.hanning(THUMB_W))


def _shift(ref: np.ndarray, cur: np.ndarray) -> tuple[float, float, float]:
    """Whole-image translation of `cur` relative to `ref` by phase correlation: (dx, dy) as shares of the frame, and
    the correlation peak (near 1: the same scene shifted; near 0: unrelated scenes)."""
    fa, fb = np.fft.fft2(ref * _WINDOW), np.fft.fft2(cur * _WINDOW)
    cross = fb * np.conj(fa)
    r = np.real(np.fft.ifft2(cross / (np.abs(cross) + 1e-9)))
    iy, ix = np.unravel_index(int(np.argmax(r)), r.shape)
    dy = iy - THUMB_H if iy > THUMB_H // 2 else iy
    dx = ix - THUMB_W if ix > THUMB_W // 2 else ix
    return dx / THUMB_W, dy / THUMB_H, float(r[iy, ix])


def _masked_cells(boxes) -> set[tuple[int, int]]:
    """Grid cells overlapped by any normalised (x1, y1, x2, y2) box."""
    out = set()
    for x1, y1, x2, y2 in boxes:
        for gy in range(GRID):
            for gx in range(GRID):
                if x1 < (gx + 1) / GRID and x2 > gx / GRID and y1 < (gy + 1) / GRID and y2 > gy / GRID:
                    out.add((gx, gy))
    return out


class CameraHealthMonitor:
    def __init__(self, cfg: HealthConfig):
        self._cfg = cfg
        self.state = CameraState.OK
        self._fail_streak = 0
        self._target = CameraState.OK
        self._target_streak = 0
        self._target_since: float | None = None
        self._prev_small: np.ndarray | None = None
        self._same_streak = 0
        self._same_since: float | None = None
        self._learn: list[tuple[np.ndarray, float]] = []
        self.reference: np.ndarray | None = None      # normalised thumbnail of the expected view
        self._ref_sharpness = 0.0

    @property
    def baseline_ready(self) -> bool:
        return self.reference is not None

    def rebaseline(self) -> None:
        """Forget the reference view; the next `baseline_frames` healthy frames become the new one."""
        self.reference, self._learn = None, []

    # ------------------------------------------------------------------ per frame
    def update(self, frame: np.ndarray | None, now: float | None = None, exclude=()) -> Transition | None:
        """frame: BGR/gray ndarray, or None when the source failed. now: seconds (None: frame counts only).
        exclude: normalised boxes of what the detector found in this frame (masked out of the viewpoint check)."""
        cfg = self._cfg
        if frame is None:
            self._fail_streak += 1
            self._target_streak, self._target_since = 0, None
            self._prev_small, self._same_streak = None, 0
            if self._fail_streak >= cfg.source_lost_after_failures and self.state is not CameraState.SOURCE_LOST:
                return self._move(CameraState.SOURCE_LOST, "no_frames", None, {"failed_reads": self._fail_streak})
            return None

        self._fail_streak = 0
        gray = _gray(frame)
        small, thumb = gray[::4, ::4], _thumb(gray)
        stats = _stats(small)
        target, reason, metrics = self._classify(thumb, small, stats, now, exclude)

        if target is self._target and self._target_streak > 0:
            self._target_streak += 1
        else:
            self._target, self._target_streak, self._target_since = target, 1, now
        held = 0.0 if now is None or self._target_since is None else now - self._target_since
        if target is not self.state and self._target_streak >= cfg.consecutive_frames \
                and (now is None or held >= cfg.sustain_s):
            metrics["held_s"] = round(held, 2)
            return self._move(target, reason or "normal_frames", stats, metrics)
        if target is CameraState.OK and self.state is CameraState.OK and self.reference is None:
            self._learn_frame(thumb, small)
        return None

    def _classify(self, raw_thumb, small, stats: FrameStats, now, exclude) -> tuple[CameraState, str, dict]:
        cfg = self._cfg
        thumb = _normalise(raw_thumb)
        similarity = None if thumb is None or self.reference is None else float((thumb * self.reference).mean())
        frozen = self._frozen(small, now)

        if stats.mean_brightness < cfg.dark_mean_below:
            if similarity is not None and similarity >= cfg.low_light_similarity_min:
                return CameraState.DEGRADED, "low_light", {"similarity": round(similarity, 3)}
            return CameraState.OBSTRUCTED, "dark_frame", {} if similarity is None else {"similarity": round(similarity, 3)}
        if stats.mean_brightness > cfg.bright_mean_above:
            return CameraState.OBSTRUCTED, "overexposed_frame", {}
        if stats.texture < cfg.flat_texture_below or thumb is None:
            return CameraState.OBSTRUCTED, "flat_frame", {}
        if frozen:
            return CameraState.FROZEN, "identical_frames", {"identical_frames": self._same_streak}
        if self.reference is None:
            return CameraState.OK, "", {}

        masked = _masked_cells(exclude)
        keep = np.ones(thumb.shape, bool)
        ch, cw = THUMB_H // GRID, THUMB_W // GRID
        for gx, gy in masked:
            keep[gy * ch:(gy + 1) * ch, gx * cw:(gx + 1) * cw] = False
        m: dict = {}
        if GRID * GRID - len(masked) >= MIN_VALID_CELLS:
            a, b = _normalise(thumb[keep]), _normalise(self.reference[keep])
            similarity = 0.0 if a is None or b is None else float((a * b).mean())
            m["similarity"] = round(similarity, 3)
            m["masked_cells"] = len(masked)
        else:
            similarity = None                               # mostly covered by detections: cannot judge the view
        dx, dy, peak = _shift(self.reference, thumb)
        moved = max(abs(dx), abs(dy))
        m["shift_peak"] = round(peak, 3)
        if (similarity is not None and similarity < cfg.view_similarity_below) \
                or (not masked and peak >= cfg.shift_peak_min and moved >= cfg.shift_min_fraction):
            if peak >= cfg.shift_peak_min and moved > 0:
                return CameraState.VIEW_CHANGED, "viewpoint_shift", {**m, "shift_x": round(dx, 3), "shift_y": round(dy, 3)}
            if similarity is not None and similarity < SCENE_GONE_BELOW:
                return CameraState.VIEW_CHANGED, "scene_replaced", m
            return CameraState.VIEW_CHANGED, "view_altered", m
        if self._ref_sharpness > 0:
            ratio = _sharpness(small) / self._ref_sharpness
            if ratio < cfg.blur_ratio_below:
                return CameraState.DEGRADED, "blurred", {**m, "sharpness_ratio": round(ratio, 3)}
        return CameraState.OK, "", {}

    def _frozen(self, small: np.ndarray, now) -> bool:
        cfg, prev = self._cfg, self._prev_small
        self._prev_small = small
        if prev is None or prev.shape != small.shape or float(np.abs(small - prev).mean()) > cfg.frozen_diff_below:
            self._same_streak, self._same_since = 0, now
            return False
        self._same_streak += 1
        held = 0.0 if now is None or self._same_since is None else now - self._same_since
        return self._same_streak >= cfg.frozen_min_frames and (now is None or held >= cfg.frozen_after_s)

    def _learn_frame(self, thumb: np.ndarray, small: np.ndarray) -> None:
        self._learn.append((thumb, _sharpness(small)))
        if len(self._learn) >= self._cfg.baseline_frames:
            ref = _normalise(np.mean([t for t, _ in self._learn], axis=0))
            if ref is not None:
                self.reference = ref
                self._ref_sharpness = float(np.median([sh for _, sh in self._learn]))
            self._learn = []

    def _move(self, new: CameraState, reason: str, stats: FrameStats | None, metrics: dict | None = None) -> Transition:
        t = Transition(self.state, new, reason, stats, dict(metrics or {}))
        self.state = new
        self._target_streak, self._target_since = 0, None
        return t
