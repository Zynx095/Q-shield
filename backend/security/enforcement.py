"""Quarantine enforcement policy (Phase 6).

Three channels, deliberately separate:

  NORMAL   register / heartbeat / telemetry         (device HMAC)   -> the device's ordinary operation
  RECOVERY POST /api/v1/recovery/report              (device HMAC)   -> minimum authenticated evidence needed to decide
                                                                        whether recovery is safe; returns remediation
                                                                        commands
  CONTROL  quarantine / recovery / twin endpoints    (operator token)-> humans and the recovery orchestrator

Enforcement happens in the gateway, AFTER authentication: an unauthenticated or forged message is rejected by the
authenticator exactly as before and never reaches this policy, so forged traffic can neither bypass quarantine nor
trigger it (trust-engine pressure is bounded; TD-19).

Policy by trust state:
  no record / TRUSTED / SUSPICIOUS / RECOVERED -> NORMAL allowed, RECOVERY refused (nothing to recover from)
  QUARANTINED / RECOVERING / VERIFIED          -> NORMAL blocked (403, logged), RECOVERY allowed
  revoked credential                           -> both refused by the authenticator (re-enrolment only)
Messages received on the recovery channel are stored as authenticated device evidence, so fresh clean evidence keeps
crediting recovery time (trust-engine.md section 7.1 interface requirement).
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.trust.model import State

NORMAL, RECOVERY, CONTROL = "normal", "recovery", "control"
RESTRICTED_STATES = frozenset({State.QUARANTINED, State.RECOVERING, State.VERIFIED})


@dataclass(frozen=True)
class Decision:
    allowed: bool
    channel: str
    state: str | None
    reason: str


def decide(channel: str, state: State | None) -> Decision:
    s = state.value if state else None
    if channel == NORMAL:
        if state in RESTRICTED_STATES:
            return Decision(False, channel, s, "device_quarantined")
        return Decision(True, channel, s, "ok")
    if channel == RECOVERY:
        if state in RESTRICTED_STATES:
            return Decision(True, channel, s, "ok")
        return Decision(False, channel, s, "recovery_channel_not_open")
    raise ValueError(f"unknown channel {channel}")
