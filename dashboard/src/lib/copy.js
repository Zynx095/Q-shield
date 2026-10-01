// Human language for system identifiers. The raw identifier always stays available in detail views.

export const STATES = ["TRUSTED", "SUSPICIOUS", "QUARANTINED", "RECOVERING", "VERIFIED", "RECOVERED"];

/** The canonical security story, in order: attack -> containment -> recovery -> restored trust. */
export const STORY = ["TRUSTED", "SUSPICIOUS", "QUARANTINED", "RECOVERING", "VERIFIED", "RECOVERED", "TRUSTED"];

export const STATE_META = {
  TRUSTED: { tone: "ok", icon: "shieldCheck", label: "Trusted", line: "Normal operation. All channels open." },
  SUSPICIOUS: { tone: "warn", icon: "alert", label: "Suspicious", line: "Adverse evidence. Watched closely; access still allowed." },
  QUARANTINED: { tone: "crit", icon: "lock", label: "Quarantined", line: "Normal channel blocked at the gateway. Only the recovery channel is open." },
  RECOVERING: { tone: "proc", icon: "refresh", label: "Recovering", line: "Remediation and health checks in progress over the recovery channel." },
  VERIFIED: { tone: "proc", icon: "badgeCheck", label: "Verified", line: "Health checks passed. Trust must still be rebuilt before access returns." },
  RECOVERED: { tone: "ok-soft", icon: "unlock", label: "Recovered", line: "Access restored. Trust is rebuilding toward fully trusted." },
};
export const NO_STATE = { tone: "neutral", icon: "dot", label: "No data", line: "No trust evidence recorded yet." };
export const stateMeta = (s) => STATE_META[s] || NO_STATE;

export const FACTORS = [
  { key: "identity_crypto", label: "Identity", icon: "fingerprint", desc: "Authenticated messages and signatures (HMAC-SHA256, ML-DSA-65)" },
  { key: "physical", label: "Physical", icon: "box", desc: "Enclosure tamper switch" },
  { key: "config_integrity", label: "Configuration", icon: "fileCheck", desc: "Firmware and configuration against the known-good state" },
  { key: "sensor_consistency", label: "Sensor", icon: "thermo", desc: "Sensor readings within expected ranges" },
  { key: "visual", label: "Vision", icon: "eye", desc: "Signed camera observations (YOLO11n)" },
  { key: "network", label: "Network", icon: "signal", desc: "Liveness: time since the last authenticated message" },
];
export const factorLabel = (k) => (FACTORS.find((f) => f.key === k) || {}).label || k;

// Trust-engine signals (reasons[].signal)
const SIGNALS = {
  physical_tamper: "Physical tamper signal detected",
  visual_rule_violation: "Restricted visual condition detected",
  visual_clear: "Camera view clear",
  camera_obstructed: "Camera view obstructed",
  camera_source_lost: "Camera source lost",
  camera_ok: "Camera feed healthy",
  sensor_out_of_range: "Sensor reading out of range",
  integrity_mismatch: "Configuration differs from known-good state",
  invalid_tag: "Message failed device authentication",
  invalid_signature: "Forged signature rejected",
  auth_profile_mismatch: "Authentication downgrade attempt rejected",
  device_replay: "Replayed device message rejected",
  observation_replay: "Replayed observation rejected",
  handshake_replay: "Replayed session handshake rejected",
  stale_observation: "Stale observation rejected",
  auth_misbehavior: "Signer acted outside its authorisation",
  malformed_payload: "Malformed payload rejected",
  device_revoked: "Device credential revoked",
  device_evidence: "Authenticated device evidence",
  healthy_evidence: "Clean authenticated evidence",
  healthy_evidence_recovery: "Trust rebuilt from clean evidence",
  network_liveness: "Liveness changed",
  state_transition_request: "Explicit state transition",
  coverage_change: "Evidence coverage changed",
  bounds: "Score bounds applied",
  unattributed_residual: "Rounding residual",
};
export function signalLabel(sig) {
  if (!sig) return "Trust update";
  if (sig.startsWith("cap:")) return `${capLabel(sig.slice(4))} ceiling`;
  return SIGNALS[sig] || humanize(sig);
}

const CAPS = {
  confirmed_incident: "Confirmed-incident",
  correlated_incident: "Correlated-incident",
  physical_tamper: "Tamper",
  repeated_replay: "Repeated-replay",
  auth_violation: "Authorisation-violation",
  integrity_mismatch: "Integrity-mismatch",
  stale_device: "Stale-device",
  revoked_device: "Revocation",
};
export const capLabel = (c) => CAPS[c] || humanize(c);

// Gateway security events (security_events.event_type)
const EVENTS = {
  invalid_tag: "Device message failed authentication",
  replay_or_stale_counter: "Replayed device message rejected",
  auth_profile_mismatch: "Authentication downgrade rejected",
  malformed_payload: "Malformed device payload rejected",
  unknown_device: "Message from an unknown device",
  revoked_device: "Message from a revoked device",
  pqc_invalid_signature: "Forged observation rejected",
  pqc_malformed_signature: "Malformed signature rejected",
  pqc_observation_replay: "Replayed observation rejected",
  pqc_stale_timestamp: "Stale observation rejected",
  pqc_future_timestamp: "Future-dated observation rejected",
  pqc_handshake_replay: "Replayed session handshake rejected",
  pqc_handshake_invalid_signature: "Session handshake signature invalid",
  pqc_session_decryption_failed: "Encrypted session message failed to decrypt",
  pqc_session_replayed_or_reordered_message: "Replayed session message rejected",
  pqc_unknown_signer: "Observation from an unknown signer",
  pqc_observation_unknown_device: "Signed observation for an unknown device",
  pqc_signer_not_authorised: "Signer not authorised for this device",
  quarantine_access_blocked: "Normal channel blocked by quarantine",
  recovery_channel_denied: "Recovery channel request denied",
  operator_auth_failed: "Operator sign-in failed",
  ingest_auth_failed: "Vision service authentication failed",
  operator_forbidden: "Operator action denied by role",
  operator_action: "Operator action",
  recovery_started: "Recovery started",
  recovery_verified: "Device verified: health checks passed",
  recovery_completed: "Recovery complete",
  recovery_failed: "Recovery failed",
  twin_expected_updated: "Known-good state updated",
  trust_engine_error: "Trust engine error",
  recovery_timer_error: "Recovery timer error",
  observation_rejected_device: "Observation for an unknown device rejected",
};
export const eventLabel = (t) => EVENTS[t] || humanize(t);

// Evidence-chain event types
const EVIDENCE = {
  trust_state_transition: "Trust state changed",
  trust_score_change: "Trust score changed",
  quarantine_access_blocked: "Quarantine enforced on a message",
  recovery_channel_denied: "Recovery channel request denied",
  recovery_started: "Recovery started",
  remediation_acknowledged: "Remediation acknowledged by device",
  recovery_verified: "Health checks passed",
  access_restored: "Access restored",
  recovery_completed: "Recovery completed",
  recovery_failed: "Recovery failed",
  operator_action: "Operator action",
  twin_expected_updated: "Known-good state updated",
};
export const evidenceLabel = (t) => EVIDENCE[t] || eventLabel(t);

export const OPERATOR_ACTIONS = {
  START_RECOVERY: "started recovery",
  ABORT_RECOVERY: "aborted recovery",
  SET_EXPECTED_STATE: "set the known-good state",
  QUARANTINE: "quarantined the device",
  CREATE_OPERATOR: "created an operator",
  REVOKE_OPERATOR: "revoked an operator",
};

export const AUTH = {
  DEVICE_HMAC: { label: "Device HMAC-SHA256", tag: "hmac" },
  SIGNER_MLDSA: { label: "ML-DSA-65 signature", tag: "pqc" },
  TOKEN_ONLY: { label: "Ingest token only (not PQC)", tag: "" },
  UNAUTHENTICATED: { label: "Unauthenticated (any network party)", tag: "crit" },
  GATEWAY_LOCAL: { label: "Gateway record", tag: "" },
};

export const AUTH_PROFILES = { "hmac-sha256-psk": "HMAC-SHA256 (pre-shared key)" };

export const STAGES = {
  remediation_pending: "Remediation issued",
  health_checks: "Health checks",
  trust_ramp: "Trust ramp",
  restoring: "Access restored",
};

export const FAILURES = {
  deadline_exceeded_before_verification: "Recovery deadline passed before the device was verified",
  trust_ramp_timeout: "Trust was not rebuilt in time",
  credential_revoked: "Device credential was revoked",
};
export function failureLabel(reason) {
  if (!reason) return "";
  if (reason.startsWith("aborted:")) return `Aborted by operator: ${reason.slice(8).trim()}`;
  if (reason.startsWith("fault_reported_during_recovery")) return "A fault was reported during recovery; the device returned to quarantine";
  return FAILURES[reason] || humanize(reason);
}

export const INCIDENT_CLASSES = {
  confirmed_incident: "Physical + visual correlation",
  correlated_incident: "Correlated evidence",
};
export const MODALITIES = { PHYSICAL: "Physical tamper", VISUAL: "Signed visual violation", SENSOR: "Sensor anomaly" };

export function humanize(id) {
  const s = String(id || "").replace(/^pqc_/, "").replace(/[_:]+/g, " ").trim();
  return s ? s[0].toUpperCase() + s.slice(1) : "Event";
}
