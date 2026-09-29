"""Trust engine data model: signals in, explainable trust changes out.

Pure data + validation. No I/O, no crypto, no model inference. Conforms to docs/architecture/trust-engine.md.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

_DEVICE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
MAX_TS = 4_102_444_800.0  # year 2100: anything later is treated as malformed


class Factor(str, Enum):
    IDENTITY = "identity_crypto"
    PHYSICAL = "physical"
    CONFIG = "config_integrity"
    SENSOR = "sensor_consistency"
    VISUAL = "visual"
    NETWORK = "network"


class State(str, Enum):
    TRUSTED = "TRUSTED"
    SUSPICIOUS = "SUSPICIOUS"
    QUARANTINED = "QUARANTINED"
    RECOVERING = "RECOVERING"
    VERIFIED = "VERIFIED"
    RECOVERED = "RECOVERED"


class Auth(str, Enum):
    """How the source of a signal was authenticated. Authenticity is an input, never a trust score."""
    DEVICE_HMAC = "DEVICE_HMAC"          # device proved possession of its provisioned HMAC secret
    SIGNER_MLDSA = "SIGNER_MLDSA"        # enrolled software signer proved possession of its ML-DSA key
    TOKEN_ONLY = "TOKEN_ONLY"            # ingest bearer token only (not PQC)
    UNAUTHENTICATED = "UNAUTHENTICATED"  # any network party could have produced this
    GATEWAY_LOCAL = "GATEWAY_LOCAL"      # derived by the gateway from its own records


class Kind(str, Enum):
    DEVICE_EVIDENCE = "device_evidence"
    PHYSICAL_TAMPER = "physical_tamper"              # level: value {"active": bool}
    SENSOR_OUT_OF_RANGE = "sensor_out_of_range"      # level: value {"active": bool}
    INTEGRITY_MISMATCH = "integrity_mismatch"        # level: value {"mismatch": bool}
    VISUAL_RULE_VIOLATION = "visual_rule_violation"
    VISUAL_CLEAR = "visual_clear"
    CAMERA_OBSTRUCTED = "camera_obstructed"
    CAMERA_SOURCE_LOST = "camera_source_lost"
    CAMERA_OK = "camera_ok"
    INVALID_TAG = "invalid_tag"
    INVALID_SIGNATURE = "invalid_signature"
    AUTH_PROFILE_MISMATCH = "auth_profile_mismatch"
    DEVICE_REPLAY = "device_replay"
    OBSERVATION_REPLAY = "observation_replay"
    HANDSHAKE_REPLAY = "handshake_replay"
    STALE_OBSERVATION = "stale_observation"
    AUTH_MISBEHAVIOR = "auth_misbehavior"
    MALFORMED_PAYLOAD = "malformed_payload"
    DEVICE_REVOKED = "device_revoked"


# Which authenticity classes each kind may arrive with. Anything else is rejected (authentication boundary).
_H, _S, _T, _U, _G = Auth.DEVICE_HMAC, Auth.SIGNER_MLDSA, Auth.TOKEN_ONLY, Auth.UNAUTHENTICATED, Auth.GATEWAY_LOCAL
REQUIRED_AUTH: dict[Kind, frozenset[Auth]] = {
    Kind.DEVICE_EVIDENCE: frozenset({_H}),
    Kind.PHYSICAL_TAMPER: frozenset({_H}),
    Kind.SENSOR_OUT_OF_RANGE: frozenset({_H}),
    Kind.INTEGRITY_MISMATCH: frozenset({_H}),
    Kind.VISUAL_RULE_VIOLATION: frozenset({_S, _T}),
    Kind.VISUAL_CLEAR: frozenset({_S, _T}),
    Kind.CAMERA_OBSTRUCTED: frozenset({_S, _T}),
    Kind.CAMERA_SOURCE_LOST: frozenset({_S, _T}),
    Kind.CAMERA_OK: frozenset({_S, _T}),
    Kind.INVALID_TAG: frozenset({_U}),
    Kind.INVALID_SIGNATURE: frozenset({_U}),
    Kind.AUTH_PROFILE_MISMATCH: frozenset({_U}),
    Kind.DEVICE_REPLAY: frozenset({_U}),
    Kind.OBSERVATION_REPLAY: frozenset({_U}),
    Kind.HANDSHAKE_REPLAY: frozenset({_U}),
    Kind.STALE_OBSERVATION: frozenset({_U, _T, _S}),
    Kind.AUTH_MISBEHAVIOR: frozenset({_S}),
    Kind.MALFORMED_PAYLOAD: frozenset({_H, _S}),
    Kind.DEVICE_REVOKED: frozenset({_G}),
}
LEVEL_FIELD = {Kind.PHYSICAL_TAMPER: "active", Kind.SENSOR_OUT_OF_RANGE: "active", Kind.INTEGRITY_MISMATCH: "mismatch"}


class SignalRejected(ValueError):
    """A signal failed validation. It changes no score; the service records a diagnostic."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason, self.detail = reason, detail


class IllegalTransition(ValueError):
    pass


@dataclass(frozen=True)
class Signal:
    signal_id: str
    device_id: str
    kind: Kind
    timestamp: float                       # gateway time of receipt (never a source-supplied time)
    auth: Auth
    confidence: float | None = None        # detector confidence in [0,1] (visual kinds); NOT authenticity
    value: Mapping[str, Any] = field(default_factory=dict)
    source_ref: str = ""
    provenance: str = ""                   # e.g. "simulated by software-agent"

    def validate(self) -> "Signal":
        if not isinstance(self.signal_id, str) or not (0 < len(self.signal_id) <= 160):
            raise SignalRejected("bad_signal_id")
        if not isinstance(self.device_id, str) or not _DEVICE_ID.match(self.device_id):
            raise SignalRejected("bad_device_id")
        if not isinstance(self.kind, Kind):
            raise SignalRejected("unknown_signal_kind", str(self.kind))
        if not isinstance(self.auth, Auth):
            raise SignalRejected("unknown_authenticity_class", str(self.auth))
        if isinstance(self.timestamp, bool) or not isinstance(self.timestamp, (int, float)) \
                or not math.isfinite(self.timestamp) or not (0 < self.timestamp < MAX_TS):
            raise SignalRejected("bad_timestamp", str(self.timestamp))
        if self.auth not in REQUIRED_AUTH[self.kind]:
            raise SignalRejected("authenticity_boundary_violation", f"{self.kind.value} may not arrive as {self.auth.value}")
        c = self.confidence
        if c is not None:
            if isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) or not (0.0 <= c <= 1.0):
                raise SignalRejected("bad_confidence", str(c))
        if self.kind is Kind.VISUAL_RULE_VIOLATION and c is None:
            raise SignalRejected("missing_confidence")
        if self.kind in LEVEL_FIELD and not isinstance(self.value.get(LEVEL_FIELD[self.kind]), bool):
            raise SignalRejected("bad_level_value", f"{self.kind.value} needs boolean '{LEVEL_FIELD[self.kind]}'")
        return self


@dataclass(frozen=True)
class Reason:
    """One term of a score change. Terms sum exactly to the exact score delta."""
    signal: str
    impact: float                          # points of final score (negative = trust down)
    factor: str | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {"signal": self.signal, "impact": self.impact}
        if self.factor:
            d["factor"] = self.factor
        d.update(self.detail)
        return d


@dataclass(frozen=True)
class TrustChange:
    event_id: str
    device_id: str
    timestamp: float
    previous_score: int
    new_score: int
    delta: int
    previous_exact: float
    new_exact: float
    previous_state: State | None
    new_state: State
    trigger_signals: tuple[str, ...]
    reasons: tuple[Reason, ...]
    caps_active: tuple[str, ...]
    incident: Mapping[str, Any] | None
    coverage: float
    unavailable: tuple[str, ...]
    kind: str = "score_change"             # score_change | time_driven | state_transition_request | created

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id, "device_id": self.device_id, "timestamp": self.timestamp, "kind": self.kind,
            "previous_score": self.previous_score, "new_score": self.new_score, "delta": self.delta,
            "previous_exact": self.previous_exact, "new_exact": self.new_exact,
            "previous_state": self.previous_state.value if self.previous_state else None, "new_state": self.new_state.value,
            "trigger_signals": list(self.trigger_signals), "reasons": [r.to_dict() for r in self.reasons],
            "caps_active": list(self.caps_active), "incident": dict(self.incident) if self.incident else None,
            "coverage": self.coverage, "unavailable": list(self.unavailable),
        }
