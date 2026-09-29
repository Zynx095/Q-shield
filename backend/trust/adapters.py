"""Feature extraction: gateway records -> validated trust Signals.

This is the ONLY place that interprets gateway records. It assigns each signal its authenticity class from how the
record was authenticated, never from anything the sender claims, and it refuses to invent signals:
  * operator / ingest-token failures are not device-trust signals (operator authentication != device trust);
  * gateway-side faults are not device evidence;
  * events that cannot be attributed to a device (unknown device, unknown signer) are counted, not scored;
  * unmapped event types produce a diagnostic, never a score change.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.trust.config import TrustConfig
from backend.trust.model import Auth, Kind, Signal

# security event type -> (Kind, Auth). Pressure kinds are UNAUTHENTICATED by definition: any network party can cause them.
_U, _S, _H = Auth.UNAUTHENTICATED, Auth.SIGNER_MLDSA, Auth.DEVICE_HMAC
EVENT_MAP: dict[str, tuple[Kind, Auth]] = {
    "invalid_tag": (Kind.INVALID_TAG, _U),
    "replay_or_stale_counter": (Kind.DEVICE_REPLAY, _U),
    "auth_profile_mismatch": (Kind.AUTH_PROFILE_MISMATCH, _U),
    "malformed_payload": (Kind.MALFORMED_PAYLOAD, _H),                    # device path: raised only after the HMAC verified
    "pqc_invalid_signature": (Kind.INVALID_SIGNATURE, _U),
    "pqc_malformed_signature": (Kind.INVALID_SIGNATURE, _U),
    "pqc_signer_algorithm_mismatch": (Kind.INVALID_SIGNATURE, _U),
    "pqc_signer_retired": (Kind.INVALID_SIGNATURE, _U),
    "pqc_signer_revoked": (Kind.INVALID_SIGNATURE, _U),
    "pqc_signer_session_mismatch": (Kind.INVALID_SIGNATURE, _U),
    "pqc_stale_timestamp": (Kind.STALE_OBSERVATION, _U),
    "pqc_future_timestamp": (Kind.STALE_OBSERVATION, _U),
    "pqc_malformed_timestamp": (Kind.STALE_OBSERVATION, _U),
    "pqc_observation_replay": (Kind.OBSERVATION_REPLAY, _U),
    "pqc_handshake_replay": (Kind.HANDSHAKE_REPLAY, _U),
    "pqc_handshake_invalid_signature": (Kind.INVALID_SIGNATURE, _U),
    "pqc_handshake_stale_or_future_handshake": (Kind.STALE_OBSERVATION, _U),
    "pqc_session_decryption_failed": (Kind.INVALID_SIGNATURE, _U),
    "pqc_session_replayed_or_reordered_message": (Kind.OBSERVATION_REPLAY, _U),
    "pqc_payload_metadata_mismatch": (Kind.AUTH_MISBEHAVIOR, _S),         # raised after the signature verified
    "pqc_signer_not_authorised": (Kind.AUTH_MISBEHAVIOR, _S),
    "pqc_malformed_payload": (Kind.MALFORMED_PAYLOAD, _S),
}
UNATTRIBUTED = {"unknown_device": "unknown device (attacker-chosen identity)", "pqc_unknown_signer": "unknown signer",
                "pqc_observation_unknown_device": "signer reported on an unknown/revoked device",
                "observation_rejected_device": "unknown/revoked device in token-path observation"}
EXCLUDED = {  # not device-trust evidence (operator/service authentication, gateway faults, benign protocol noise)
    "operator_auth_failed": "operator authentication", "ingest_auth_failed": "ingest-service authentication",
    "credential_unreadable": "gateway credential-store fault", "credential_missing": "gateway credential-store fault",
    "auth_profile_not_implemented": "gateway limitation", "revoked_device": "handled by the revocation gate",
    "unsupported_protocol_version": "protocol noise", "message_type_mismatch": "protocol noise", "unknown_auth_profile": "protocol noise",
    "pqc_unsupported_protocol_version": "protocol noise", "pqc_unsupported_algorithm": "protocol noise",
    "pqc_unknown_gateway_key": "protocol noise", "pqc_too_many_sessions": "gateway limit", "pqc_unknown_session": "protocol noise",
    "pqc_session_session_expired": "protocol noise", "pqc_session_expired": "protocol noise",
    # Enforcement / recovery / control-plane records describe the gateway's own actions, not new device evidence.
    # Scoring them would feed quarantine back into itself.
    "quarantine_access_blocked": "enforcement action (consequence of trust, not evidence)",
    "recovery_channel_denied": "enforcement action (consequence of trust, not evidence)",
    "trust_engine_error": "gateway fault",
    "recovery_started": "control-plane action", "recovery_failed": "control-plane action",
    "recovery_verified": "control-plane action", "recovery_completed": "control-plane action",
    "twin_expected_updated": "control-plane action",
}


@dataclass
class Adapted:
    signals: list
    note: str | None = None        # why no signal was produced (recorded as a diagnostic, never a score change)
    device_id: str | None = None


def _json(text, default):
    try:
        return json.loads(text) if isinstance(text, str) else (text or default)
    except (TypeError, ValueError):
        return default


def _device_for_event(row, details: dict, store) -> str | None:
    """Attribution: explicit device id (validated at the gateway) first; else the claimed signer, but only when that
    signer is authorised for exactly one device. Never guess."""
    if row["device_id"]:
        return row["device_id"]
    if details.get("device_id"):
        return details["device_id"]
    sid = details.get("claimed_signer_id")
    if sid:
        signer = store.get_signer(sid)
        if signer is not None and len(signer.allowed_devices) == 1:
            return signer.allowed_devices[0]
    return None


def from_security_event(row, store) -> Adapted:
    et = row["event_type"]
    details = _json(row["details"], {})
    if et in EXCLUDED:
        return Adapted([], f"excluded: {EXCLUDED[et]}")
    if et in UNATTRIBUTED:
        return Adapted([], f"unattributed: {UNATTRIBUTED[et]}")
    if et not in EVENT_MAP:
        return Adapted([], f"unmapped_event_type:{et}")
    kind, auth = EVENT_MAP[et]
    dev = _device_for_event(row, details, store)
    if dev is None:
        return Adapted([], f"unattributed: {et} (no device or single-device signer)")
    return Adapted([Signal(f"event:{row['id']}", dev, kind, row["received_at"], auth, source_ref=f"security_event:{row['id']}")], device_id=dev)


def _parse_iso(ts: str) -> float | None:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.timestamp() if dt.tzinfo else None
    except (AttributeError, ValueError):
        return None


def from_observation(row, cfg: TrustConfig) -> Adapted:
    body = _json(row["body"], None)
    if not isinstance(body, dict):
        return Adapted([], "malformed_observation_record")
    label = row["auth"]
    if label == "ingest-token":
        auth = Auth.TOKEN_ONLY
    elif isinstance(label, str) and label.startswith("ML-DSA"):
        auth = Auth.SIGNER_MLDSA
    else:
        return Adapted([], f"unknown_observation_authenticity_label:{label}")
    dev, oid = body.get("device_id"), body.get("observation_id")
    if not dev or not oid:
        return Adapted([], "observation_missing_identity")
    ts, sid, ref = row["received_at"], f"obs:{oid}", f"observation:{oid}"
    observed = _parse_iso(body.get("timestamp", ""))
    if observed is None or abs(ts - observed) > cfg.observation_freshness_s:
        return Adapted([Signal(sid, dev, Kind.STALE_OBSERVATION, ts, auth, source_ref=ref)], device_id=dev)   # not scored
    et = body.get("event_type")
    if et == "visual_observation":
        if body.get("anomaly") is True:
            return Adapted([Signal(sid, dev, Kind.VISUAL_RULE_VIOLATION, ts, auth, confidence=body.get("confidence"),
                                   value={"zone": body.get("zone"), "object": body.get("object")}, source_ref=ref)], device_id=dev)
        return Adapted([Signal(sid, dev, Kind.VISUAL_CLEAR, ts, auth, confidence=body.get("confidence"), source_ref=ref)], device_id=dev)
    if et == "camera_health":
        state = (body.get("details") or {}).get("state")
        kind = {"obstructed": Kind.CAMERA_OBSTRUCTED, "source_lost": Kind.CAMERA_SOURCE_LOST, "ok": Kind.CAMERA_OK}.get(state)
        if kind is None:
            return Adapted([], f"unknown_camera_state:{state}")
        return Adapted([Signal(sid, dev, kind, ts, auth, source_ref=ref)], device_id=dev)
    return Adapted([], f"unmapped_observation_type:{et}")


def _out_of_range(value, lo, hi) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return True                                            # fail closed: unreadable value in a limited field
    return (lo is not None and value < lo) or (hi is not None and value > hi)


TELEMETRY_KINDS = ("telemetry", "recovery")    # recovery-channel reports carry the same authenticated telemetry fields


def from_device_message(row, cfg: TrustConfig, hw: str | None, expect: dict | None = None) -> Adapted:
    """`expect`: per-device expectations from the digital twin (sensor_limits / expected_fw_version /
    expected_cfg_hash). When a key is present it overrides the global trust configuration for this device."""
    expect = expect or {}
    limits = expect.get("sensor_limits", cfg.sensor_limits)
    exp_fw = expect.get("expected_fw_version", cfg.expected_fw_version)
    exp_cfg = expect.get("expected_cfg_hash", cfg.expected_cfg_hash)
    dev, kind, ts = row["device_id"], row["kind"], row["received_at"]
    payload = _json(row["payload"], {})
    prov = "simulated by software-agent" if hw == "software-agent" else "self-reported by device"
    mid = f"msg:{row['id']}"
    sigs = [Signal(mid, dev, Kind.DEVICE_EVIDENCE, ts, Auth.DEVICE_HMAC, source_ref=f"device_message:{row['id']}",
                   provenance=prov if hw == "software-agent" else "")]
    if kind in TELEMETRY_KINDS and isinstance(payload, dict):
        if isinstance(payload.get("tamper"), bool):
            sigs.append(Signal(f"{mid}:tamper", dev, Kind.PHYSICAL_TAMPER, ts, Auth.DEVICE_HMAC, value={"active": payload["tamper"]},
                               source_ref=f"device_message:{row['id']}", provenance=prov))
        present = [f for f in limits if f in payload and payload[f] is not None]
        if present:
            bad = [f for f in present if _out_of_range(payload[f], *limits[f])]
            sigs.append(Signal(f"{mid}:sensor", dev, Kind.SENSOR_OUT_OF_RANGE, ts, Auth.DEVICE_HMAC,
                               value={"active": bool(bad), "fields": bad}, source_ref=f"device_message:{row['id']}", provenance=prov))
        checks = []
        if exp_fw is not None and payload.get("fw_version") is not None:
            checks.append(payload["fw_version"] != exp_fw)
        if exp_cfg is not None and payload.get("cfg_hash") is not None:
            checks.append(payload["cfg_hash"] != exp_cfg)
        if checks:
            sigs.append(Signal(f"{mid}:integrity", dev, Kind.INTEGRITY_MISMATCH, ts, Auth.DEVICE_HMAC, value={"mismatch": any(checks)},
                               source_ref=f"device_message:{row['id']}", provenance="self-reported, not proof of integrity"))
    return Adapted(sigs, device_id=dev)
