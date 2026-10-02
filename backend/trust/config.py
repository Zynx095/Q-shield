"""Trust engine parameters. Every value is defined in docs/architecture/trust-engine.md.

Weights, thresholds and hysteresis come from TD-08. All other numbers are documented DESIGN CHOICES, not empirically
derived. If a value changes, change the specification first.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping

from backend.trust.model import Factor, Kind

SEVERITY_POINTS = {"INFO": 0.0, "LOW": 10.0, "MEDIUM": 30.0, "HIGH": 60.0, "CRITICAL": 100.0}

DEFAULT_WEIGHTS = {Factor.IDENTITY: 0.25, Factor.PHYSICAL: 0.20, Factor.CONFIG: 0.15,
                   Factor.SENSOR: 0.15, Factor.VISUAL: 0.15, Factor.NETWORK: 0.10}

# Persistent factor penalties: kind -> (factor, severity label). Points come from SEVERITY_POINTS.
DEFAULT_PENALTIES = {
    Kind.PHYSICAL_TAMPER: (Factor.PHYSICAL, "CRITICAL"),
    Kind.SENSOR_OUT_OF_RANGE: (Factor.SENSOR, "HIGH"),
    Kind.INTEGRITY_MISMATCH: (Factor.CONFIG, "HIGH"),
    Kind.CAMERA_OBSTRUCTED: (Factor.VISUAL, "HIGH"),
    Kind.CAMERA_SOURCE_LOST: (Factor.VISUAL, "MEDIUM"),
    Kind.CAMERA_FROZEN: (Factor.VISUAL, "HIGH"),          # as severe as an obstruction: the live scene is not shown
    Kind.CAMERA_VIEW_CHANGED: (Factor.VISUAL, "HIGH"),    # as severe as an obstruction: the protected view is not watched
    Kind.CAMERA_DEGRADED: (Factor.VISUAL, "MEDIUM"),      # reduced evidence quality, not proof of interference
    Kind.SUBJECT_PROXIMITY: (Factor.VISUAL, "LOW"),       # image-space heuristic
    Kind.AUTH_MISBEHAVIOR: (Factor.IDENTITY, "HIGH"),
    Kind.MALFORMED_PAYLOAD: (Factor.IDENTITY, "MEDIUM"),
}
# Bounded unauthenticated pressure, in points of final score.
DEFAULT_PRESSURE = {
    Kind.INVALID_TAG: 10.0, Kind.INVALID_SIGNATURE: 10.0, Kind.AUTH_PROFILE_MISMATCH: 10.0,
    Kind.DEVICE_REPLAY: 8.0, Kind.OBSERVATION_REPLAY: 8.0, Kind.HANDSHAKE_REPLAY: 8.0,
    Kind.STALE_OBSERVATION: 4.0,
}
# Recovery half-lives in credited seconds (credited by authenticated device evidence only).
DEFAULT_HALF_LIFE = {Factor.PHYSICAL: 3600.0, Factor.SENSOR: 1800.0, Factor.CONFIG: 3600.0,
                     Factor.VISUAL: 900.0, Factor.IDENTITY: 1800.0}
# Caps: name -> (ceiling, hold in credited seconds or None when release is condition-based).
DEFAULT_CAPS = {
    "revoked_device": (0.0, None), "confirmed_incident": (30.0, 1800.0), "physical_tamper": (55.0, 900.0),
    "correlated_incident": (55.0, 900.0), "repeated_replay": (65.0, 900.0), "integrity_mismatch": (65.0, None),
    "auth_violation": (70.0, 900.0), "stale_device": (79.0, None),
}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class TrustConfig:
    weights: Mapping[Factor, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    penalties: Mapping[Kind, tuple] = field(default_factory=lambda: dict(DEFAULT_PENALTIES))
    pressure_points: Mapping[Kind, float] = field(default_factory=lambda: dict(DEFAULT_PRESSURE))
    half_life_s: Mapping[Factor, float] = field(default_factory=lambda: dict(DEFAULT_HALF_LIFE))
    caps: Mapping[str, tuple] = field(default_factory=lambda: dict(DEFAULT_CAPS))
    pressure_cap: float = 25.0
    pressure_half_life_s: float = 600.0
    trusted_min: int = 80
    quarantine_below: int = 50
    trusted_reentry_min: int = 85
    # visual / confidence
    visual_base_points: float = 100.0
    confidence_floor: float = 0.30
    confidence_exponent: float = 2.0
    token_only_multiplier: float = 0.5
    correlation_min_confidence: float = 0.5
    # time
    offline_timeout_s: float = 15.0
    stale_full_s: float = 150.0
    stale_cap_after_s: float = 45.0
    credit_cap_s: float = 45.0
    episode_gap_s: float = 30.0
    correlation_window_s: float = 60.0
    replay_window_s: float = 600.0
    replay_threshold: int = 3
    observation_freshness_s: float = 300.0
    max_seen_ids: int = 5000
    # configuration-derived expectations (no digital twin yet): both default to "unavailable"
    sensor_limits: Mapping[str, tuple] = field(default_factory=dict)        # field -> (min|None, max|None)
    expected_fw_version: str | None = None
    expected_cfg_hash: str | None = None

    def validate(self) -> "TrustConfig":
        if set(self.weights) != set(Factor) or any(w <= 0 or not math.isfinite(w) for w in self.weights.values()):
            raise ConfigError("weights must be positive and cover every factor")
        if abs(sum(self.weights.values()) - 1.0) > 1e-9:
            raise ConfigError("weights must sum to 1")
        if not (0 <= self.quarantine_below < self.trusted_min <= self.trusted_reentry_min <= 100):
            raise ConfigError("thresholds must satisfy 0 <= quarantine_below < trusted_min <= trusted_reentry_min <= 100")
        for name, (ceil, hold) in self.caps.items():
            if not (0 <= ceil <= 100) or (hold is not None and hold <= 0):
                raise ConfigError(f"bad cap {name}")
        if "revoked_device" not in self.caps or self.caps["revoked_device"][0] != 0:
            raise ConfigError("revoked_device cap must exist and be 0")
        if not (0 <= self.pressure_cap <= 100) or self.pressure_cap >= 100 - self.quarantine_below + 1:
            raise ConfigError("pressure cap must not be able to reach quarantine by itself")
        if 100 - self.pressure_cap < self.quarantine_below:
            raise ConfigError("pressure cap would allow unauthenticated quarantine")
        if not (0 <= self.confidence_floor <= 1) or self.confidence_exponent <= 0 or not (0 < self.token_only_multiplier <= 1):
            raise ConfigError("bad confidence parameters")
        for k, (f, sev) in self.penalties.items():
            if sev not in SEVERITY_POINTS or f not in self.weights:
                raise ConfigError(f"bad penalty for {k}")
        for f, h in self.half_life_s.items():
            if h <= 0:
                raise ConfigError("half-lives must be positive")
        if self.offline_timeout_s <= 0 or self.stale_full_s <= self.offline_timeout_s or self.credit_cap_s <= 0:
            raise ConfigError("bad time parameters")
        return self

    def penalty_points(self, kind: Kind) -> float:
        return SEVERITY_POINTS[self.penalties[kind][1]]

    def with_(self, **kw) -> "TrustConfig":
        return replace(self, **kw).validate()

    @classmethod
    def load(cls, path: str | Path | None = None, **overrides) -> "TrustConfig":
        """Defaults, optionally overridden by a JSON file with the *configuration-derived* keys only
        (sensor_limits, expected_fw_version, expected_cfg_hash, offline_timeout_s). Weights, caps and thresholds are
        specified in docs/architecture/trust-engine.md and are deliberately not overridable from a file."""
        data: dict = {}
        if path:
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                raise ConfigError(f"cannot read trust config {path}: {e}") from None
        allowed = {"sensor_limits", "expected_fw_version", "expected_cfg_hash", "offline_timeout_s"}
        extra = set(data) - allowed
        if extra:
            raise ConfigError(f"keys not overridable from file (change the specification first): {sorted(extra)}")
        if "sensor_limits" in data:
            limits = {}
            for k, v in data["sensor_limits"].items():
                if not (isinstance(v, list) and len(v) == 2):
                    raise ConfigError("sensor_limits values must be [min, max]")
                limits[k] = (v[0], v[1])
            data["sensor_limits"] = limits
        return cls(**{**data, **overrides}).validate()
