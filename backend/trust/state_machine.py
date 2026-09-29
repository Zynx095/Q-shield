"""Trust state machine: legal transitions and score-driven automatic transitions.

Phase 4 records states and validates transitions. It does NOT enforce quarantine or drive recovery; QUARANTINED is a
recorded state with a recommendation, and it is sticky (a rising score never leaves it).
"""
from __future__ import annotations

from backend.trust.config import TrustConfig
from backend.trust.model import IllegalTransition, State

TRANSITIONS: dict[State, frozenset[State]] = {
    State.TRUSTED: frozenset({State.SUSPICIOUS, State.QUARANTINED}),
    State.SUSPICIOUS: frozenset({State.TRUSTED, State.QUARANTINED}),
    State.QUARANTINED: frozenset({State.RECOVERING}),
    State.RECOVERING: frozenset({State.VERIFIED, State.QUARANTINED}),
    State.VERIFIED: frozenset({State.RECOVERED, State.QUARANTINED}),
    State.RECOVERED: frozenset({State.TRUSTED, State.SUSPICIOUS, State.QUARANTINED}),
}
RECOMMENDED_ACTION = {
    State.TRUSTED: "none", State.SUSPICIOUS: "increase monitoring",
    State.QUARANTINED: "quarantine recommended (not enforced in Phase 4)",
    State.RECOVERING: "recovery in progress", State.VERIFIED: "trust rebuild pending", State.RECOVERED: "trust rebuilt",
}


def is_legal(prev: State | None, new: State) -> bool:
    if prev is None:
        return new in (State.TRUSTED, State.SUSPICIOUS, State.QUARANTINED)
    return new == prev or new in TRANSITIONS[prev]


def assert_legal(prev: State | None, new: State) -> None:
    if not is_legal(prev, new):
        raise IllegalTransition(f"{prev.value if prev else None} -> {new.value} is not a legal transition")


def automatic_state(cfg: TrustConfig, prev: State | None, score: int, revoked: bool, recovery_fault: bool = False) -> State:
    """State implied by the score. Only TRUSTED <-> SUSPICIOUS and entry into QUARANTINED are automatic.

    RECOVERING and VERIFIED are NOT dropped merely because the score is still low (a device that has just been
    remediated still carries its decaying penalties; the score can only rise through fresh authenticated evidence,
    which needs the device to stay in the recovery path). They regress to QUARANTINED only on revocation or on a
    fresh authenticated violation report (`recovery_fault`), or by an explicit validated transition (a failed check).
    RECOVERED is a claim that trust was rebuilt, so it falls back to QUARANTINED below the quarantine threshold."""
    if revoked:
        return State.QUARANTINED
    if prev is None:
        return State.TRUSTED if score >= cfg.trusted_min else (State.SUSPICIOUS if score >= cfg.quarantine_below else State.QUARANTINED)
    if prev is State.QUARANTINED:
        return State.QUARANTINED                      # sticky: leaving needs an explicit, validated transition
    if prev in (State.RECOVERING, State.VERIFIED):
        return State.QUARANTINED if recovery_fault else prev
    if score < cfg.quarantine_below:
        return State.QUARANTINED
    if prev is State.TRUSTED:
        return State.SUSPICIOUS if score < cfg.trusted_min else State.TRUSTED
    if prev is State.SUSPICIOUS:
        return State.TRUSTED if score >= cfg.trusted_reentry_min else State.SUSPICIOUS
    return prev                                       # RECOVERED: leaves only through a validated transition


def transition_guard(cfg: TrustConfig, prev: State | None, target: State, score: int | None, revoked: bool) -> None:
    """Score/revocation preconditions for an *explicit* transition (in addition to graph legality)."""
    if target is State.QUARANTINED:
        return                                        # failing safe is always allowed
    if revoked:
        raise IllegalTransition("a revoked device cannot leave QUARANTINED without re-enrolment")
    if score is None:
        raise IllegalTransition("device has no score")
    if prev is State.VERIFIED and target is State.RECOVERED and score < cfg.quarantine_below:
        raise IllegalTransition(f"VERIFIED -> RECOVERED needs score >= {cfg.quarantine_below} (dynamic trust has not been rebuilt; score {score})")
    if prev is State.RECOVERED and target is State.TRUSTED and score < cfg.trusted_reentry_min:
        raise IllegalTransition(f"RECOVERED -> TRUSTED needs score >= {cfg.trusted_reentry_min} (score {score})")
    if prev is State.RECOVERED and target is State.SUSPICIOUS and score < cfg.quarantine_below:
        raise IllegalTransition(f"RECOVERED -> SUSPICIOUS needs score >= {cfg.quarantine_below} (score {score})")
