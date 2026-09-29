"""Envelope authentication for device messages.

Order matters: identity lookup -> profile check -> tag verification -> replay check.
The replay counter is advanced only after the tag verifies, so an unauthenticated sender
cannot burn a device's counter. Failures return a reason code that is stored as a
security event; the HTTP layer never reveals the reason to the caller.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.devices.store import DeviceRecord, Store
from backend.security.credentials import CredentialError, CredentialStore
from backend.protocol.envelope import (
    AUTH_HMAC, AUTH_PQC, MESSAGE_TYPES, PROTO_VERSION, Envelope, check_hmac_tag,
)


class AuthError(Exception):
    def __init__(self, reason: str, severity: str = "medium"):
        super().__init__(reason)
        self.reason = reason
        self.severity = severity


@dataclass(frozen=True)
class Authenticated:
    device: DeviceRecord
    envelope: Envelope


def authenticate(store: Store, creds: CredentialStore, env: Envelope, expected_type: str) -> Authenticated:
    if env.proto != PROTO_VERSION:
        raise AuthError("unsupported_protocol_version", "low")
    if env.type not in MESSAGE_TYPES or env.type != expected_type:
        raise AuthError("message_type_mismatch", "low")

    device = store.get_device(env.device_id)
    if device is None:
        raise AuthError("unknown_device", "high")
    if device.revoked:
        raise AuthError("revoked_device", "high")
    if env.auth != device.auth_profile:
        # Also blocks downgrade: a device enrolled for one profile cannot use another.
        raise AuthError("auth_profile_mismatch", "high")

    if env.auth == AUTH_HMAC:
        try:
            secret = creds.get(env.device_id)
        except CredentialError:
            raise AuthError("credential_unreadable", "high")
        if secret is None:
            raise AuthError("credential_missing", "high")
        if not check_hmac_tag(secret, env):
            raise AuthError("invalid_tag", "high")
    elif env.auth == AUTH_PQC:
        # Phase 3. Refuse rather than pretend to verify.
        raise AuthError("auth_profile_not_implemented", "low")
    else:
        raise AuthError("unknown_auth_profile", "low")

    if not store.advance_counter(env.device_id, env.counter):
        raise AuthError("replay_or_stale_counter", "high")
    return Authenticated(device, env)
