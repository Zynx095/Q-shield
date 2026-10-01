// Pure derivations from real API payloads. No DOM, no fetch: unit-tested under Node (dashboard/tests).
// Nothing here invents data: every value is computed from a gateway record, and when a record is missing the
// result says so (null / "unknown") instead of filling in a plausible number.

import {
  AUTH, FACTORS, INCIDENT_CLASSES, MODALITIES, OPERATOR_ACTIONS, eventLabel, failureLabel, signalLabel, stateMeta,
} from "./copy.js";

const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);
const RANK = { QUARANTINED: 0, SUSPICIOUS: 1, RECOVERING: 2, VERIFIED: 3, RECOVERED: 4, TRUSTED: 5 };
export const rankOf = (state) => (state in RANK ? RANK[state] : 6);

export function parsePayload(p) {
  if (p && typeof p === "object") return p;
  try { return JSON.parse(p || "{}"); } catch { return {}; }
}

/** Device that most needs attention (worst state, then lowest score). */
export function attentionOrder(trustList) {
  return [...(trustList || [])].sort((a, b) => rankOf(a.state) - rankOf(b.state) || (a.score ?? 101) - (b.score ?? 101)
    || String(a.device_id).localeCompare(String(b.device_id)));
}

// ---------------------------------------------------------------------------------------------- posture
/** "Is my system secure right now?" answered from trust states, open incidents and gateway reachability. */
export function posture({ connected, trustList = [], openIncidents = 0 }) {
  if (!connected) {
    return { tone: "neutral", icon: "plugOff", title: "Gateway connection lost", line: "Showing the last data received. Security state may have changed." };
  }
  const tracked = trustList.filter((t) => t.state);
  if (!tracked.length) return { tone: "neutral", icon: "dot", title: "No devices reporting", line: "No device has produced trust evidence yet." };
  const by = (s) => tracked.filter((t) => t.state === s).map((t) => t.device_id);
  const q = by("QUARANTINED"), rec = [...by("RECOVERING"), ...by("VERIFIED")], sus = by("SUSPICIOUS"), restored = by("RECOVERED");
  const names = (ids) => (ids.length === 1 ? ids[0] : `${ids.length} devices`);
  if (q.length) {
    return { tone: "crit", icon: "lock", title: "Threat contained",
      line: `${names(q)} ${q.length === 1 ? "is" : "are"} quarantined. Normal traffic is blocked at the gateway; only the recovery channel is open.` };
  }
  if (rec.length) {
    return { tone: "proc", icon: "refresh", title: "Recovery in progress",
      line: `${names(rec)} ${rec.length === 1 ? "is" : "are"} being remediated and verified before access returns.` };
  }
  if (sus.length) {
    return { tone: "warn", icon: "alert", title: "Under observation",
      line: `${names(sus)} reported adverse evidence. Access is still allowed while the evidence is assessed.` };
  }
  if (restored.length) {
    return { tone: "ok-soft", icon: "unlock", title: "Access restored",
      line: `${names(restored)} ${restored.length === 1 ? "is" : "are"} back on the normal channel; trust is still rebuilding.` };
  }
  if (openIncidents) {
    return { tone: "warn", icon: "alert", title: "Incident open", line: "An incident is recorded but no device is currently contained." };
  }
  return { tone: "ok", icon: "shieldCheck", title: "All devices trusted",
    line: `${tracked.length === 1 ? "The device is" : `All ${tracked.length} devices are`} authenticated, consistent and on the normal channel.` };
}

// ---------------------------------------------------------------------------------------------- factors
/** Severity by the points a factor currently removes from the score (not by raw penalty). */
export function factorLevel(available, loss) {
  if (!available) return "na";
  if (loss < 0.5) return "clear";
  if (loss < 15) return "hit";
  return "severe";
}

export function factorView(snapshot, historyDesc = []) {
  const f = (snapshot && snapshot.factors) || {};
  return FACTORS.map((meta) => {
    const x = f[meta.key] || {};
    const available = !!x.available;
    const penalty = available ? Math.max(0, Math.min(100, x.penalty || 0)) : null;
    const weight = available ? x.effective_weight : null;
    let last = null;
    for (const c of historyDesc) {
      const r = (c.reasons || []).find((r) => r.factor === meta.key && r.signal);
      if (r) { last = { ts: c.timestamp, signal: r.signal, impact: r.impact, auth: r.authenticity, confidence: r.confidence }; break; }
    }
    return {
      ...meta, available, penalty, weight, nominalWeight: x.nominal_weight ?? null,
      health: available ? 100 - penalty : null,
      contribution: available ? weight * (100 - penalty) : null,
      loss: available ? weight * penalty : null,
      level: factorLevel(available, available ? weight * penalty : 0),
      last,
    };
  });
}

/** How the displayed score is produced: sum of weighted factor health, minus attack pressure, under any ceiling. */
export function scoreBreakdown(snapshot) {
  if (!snapshot || snapshot.status !== "TRACKED") return null;
  const caps = snapshot.caps || [];
  const ceiling = caps.length ? Math.min(...caps.map((c) => c.ceiling)) : null;
  return { raw: snapshot.raw, pressure: snapshot.pressure, uncapped: snapshot.uncapped, caps, ceiling,
    capped: ceiling !== null && snapshot.uncapped > ceiling, final: snapshot.score, exact: snapshot.score_exact,
    coverage: snapshot.coverage, unavailable: snapshot.unavailable || [] };
}

// ---------------------------------------------------------------------------------------------- timeline
const TRANSITION_TITLE = {
  SUSPICIOUS: "Trust dropped to suspicious",
  QUARANTINED: "Device entered quarantine",
  RECOVERING: "Recovery started",
  VERIFIED: "Device verified",
  RECOVERED: "Access restored",
  TRUSTED: "Trust restored",
};
function transitionTitle(from, to, kind) {
  if (kind === "created") return to === "TRUSTED" ? "Device joined and is trusted" : `Trust record created: ${stateMeta(to).label.toLowerCase()}`;
  if (to === "QUARANTINED" && (from === "RECOVERING" || from === "VERIFIED" || from === "RECOVERED")) return "Returned to quarantine";
  if (to === "TRUSTED" && from === "RECOVERED") return "Trust fully restored";
  return TRANSITION_TITLE[to] || `State changed to ${stateMeta(to).label}`;
}

const REBUILD_SIGNALS = new Set(["healthy_evidence_recovery", "network_liveness", "coverage_change", "bounds", "unattributed_residual"]);
const RECOVERY_EVENTS = new Set(["recovery_started", "recovery_verified", "recovery_completed", "recovery_failed"]);

/** Orchestrator reasons arrive as "recovery started: <operator reason>" / "recovery failed: <code>". */
function cleanReason(reason) {
  const m = /^recovery (started|failed): (.*)$/i.exec(reason || "");
  if (!m) return reason;
  return m[1].toLowerCase() === "failed" ? failureLabel(m[2]) : m[2];
}

function primaryReason(reasons) {
  const real = (reasons || []).filter((r) => r.signal && !r.signal.startsWith("cap:"));
  const pool = real.length ? real : reasons || [];
  return [...pool].sort((a, b) => Math.abs(b.impact || 0) - Math.abs(a.impact || 0))[0] || null;
}

/**
 * Messages the gateway REJECTED and the trust engine counts only as bounded attack pressure (their authenticity class
 * is UNAUTHENTICATED: any network party could have sent them). The note says what the gateway actually checked.
 */
export function rejectionNote(eventType, sigAlg = "ML-DSA") {
  switch (eventType) {
    case "pqc_invalid_signature":
    case "pqc_handshake_invalid_signature":
      return `${sigAlg} signature did not verify; bounded pressure only.`;
    case "pqc_malformed_signature":
      return "Signature could not be parsed; bounded pressure only.";
    case "pqc_observation_replay":
      return "Previously accepted signed observation was replayed; replay rejected.";
    case "pqc_handshake_replay":
      return "Session handshake was replayed; replay rejected.";
    case "pqc_session_replayed_or_reordered_message":
      return "Encrypted session message was replayed or reordered; rejected.";
    case "pqc_session_decryption_failed":
      return "Session message failed AES-256-GCM authentication; rejected.";
    case "invalid_tag":
      return "HMAC-SHA256 tag did not verify (forged or corrupted message); bounded pressure only.";
    case "replay_or_stale_counter":
      return "Device message counter was replayed or stale; replay rejected.";
    case "auth_profile_mismatch":
      return "Message used a different authentication profile than the device enrolled with; rejected.";
    default:
      return null;
  }
}

function changeItem(c, eventsById, consumed, evidenceByTrustEvent, sigAlg) {
  const stateChange = c.kind === "created" || c.previous_state !== c.new_state;
  const primary = primaryReason(c.reasons);
  const linked = [];
  for (const r of c.reasons || []) {
    const m = /^security_event:(\d+)$/.exec(r.source_ref || "");
    if (m && eventsById.has(Number(m[1]))) { linked.push(eventsById.get(Number(m[1]))); consumed.add(Number(m[1])); }
  }
  const delta = (c.new_score ?? 0) - (c.previous_score ?? c.new_score ?? 0);
  const rejectedBy = linked.find((e) => rejectionNote(e.event_type));
  const rejected = !!rejectedBy || (primary && primary.authenticity === "UNAUTHENTICATED");
  let title, sub = null, tone;
  if (stateChange) {
    title = transitionTitle(c.previous_state, c.new_state, c.kind);
    tone = stateMeta(c.new_state).tone;
    if (primary && primary.signal !== "state_transition_request") sub = linked[0] ? eventLabel(linked[0].event_type) : signalLabel(primary.signal);
    else if (primary && primary.reason) sub = cleanReason(primary.reason);
  } else {
    title = linked[0] ? eventLabel(linked[0].event_type) : signalLabel(primary && primary.signal);
    if (rejectedBy) sub = rejectionNote(rejectedBy.event_type, sigAlg);
    if (primary && primary.signal === "network_liveness") {
      title = primary.impact < 0 ? "Liveness fading: no accepted device messages" : "Liveness restored";
    }
    tone = delta < 0 ? "warn" : delta > 0 ? "ok" : "neutral";
  }
  return {
    key: c.event_id, ts: c.timestamp, type: stateChange ? "state" : "score", title, sub: cap(sub), tone, rejected,
    isState: stateChange, stateFrom: c.previous_state, stateTo: c.new_state,
    scoreFrom: c.previous_score, scoreTo: c.new_score, delta,
    signals: (c.reasons || []).map((r) => ({ ...r, label: signalLabel(r.signal), authLabel: r.authenticity ? (AUTH[r.authenticity] || {}).label || r.authenticity : null })),
    triggers: c.trigger_signals || [], caps: c.caps_active || [], incident: c.incident || null,
    events: linked, evidence: evidenceByTrustEvent ? evidenceByTrustEvent.get(c.event_id) || null : null,
    recoveryId: ((c.trigger_signals || []).find((t) => t.startsWith("recovery:")) || "").slice(9) || null,
    operator: null, related: [],
  };
}

function eventItem(e, sigAlg) {
  const d = e.details || {};
  let title = eventLabel(e.event_type), sub = rejectionNote(e.event_type, sigAlg);
  let tone = e.severity === "high" ? "crit" : e.severity === "medium" ? "warn" : "neutral";
  if (e.event_type === "operator_action") {
    title = `${d.operator_id || "Operator"} ${OPERATOR_ACTIONS[d.action] || String(d.action || "acted").toLowerCase()}`;
    tone = d.result === "success" ? "proc" : "warn";
    sub = d.result === "success" ? d.reason || null : `Refused: ${d.error || "rejected by the gateway"}`;
  } else if (e.event_type === "quarantine_access_blocked") {
    tone = "crit"; sub = "A message on the normal channel was refused at the gateway";
  } else if (e.event_type === "twin_expected_updated") {
    tone = "proc"; sub = d.operator_id ? `Set by ${d.operator_id}` : null;
  } else if (e.event_type === "recovery_failed") {
    tone = "crit"; sub = failureLabel(d.reason);
  } else if (e.event_type === "recovery_completed") {
    tone = "ok";
  }
  return { key: `ev-${e.id}`, ts: e.received_at, type: "event", title, sub, tone, rejected: !!rejectionNote(e.event_type), isState: false, events: [e],
    signals: [], triggers: [], caps: [], evidence: null, operator: d.operator_id || null, related: [] };
}

/**
 * One chronological story for a device: trust changes joined with the gateway events that caused them, the
 * operator who acted, and the evidence-chain entry that seals each change. Newest first.
 */
export function buildTimeline({ history = [], events = [], deviceId = null, evidenceByTrustEvent = null, includeSystem = false, sigAlg = "ML-DSA" }) {
  const eventsById = new Map(events.map((e) => [e.id, e]));
  const consumed = new Set();
  const asc = [...history].sort((a, b) => a.timestamp - b.timestamp);
  let items = asc.map((c) => changeItem(c, eventsById, consumed, evidenceByTrustEvent, sigAlg));

  // Fold runs of small "clean evidence rebuilt trust" steps into one readable entry.
  const folded = [];
  for (const it of items) {
    const quiet = it.type === "score" && it.delta >= 0 && it.signals.every((s) => REBUILD_SIGNALS.has(s.signal) || s.signal?.startsWith("cap:"));
    const prev = folded[folded.length - 1];
    if (quiet && prev && prev.group) {
      prev.group.count += 1; prev.group.last = it.ts; prev.scoreTo = it.scoreTo; prev.delta = prev.scoreTo - prev.scoreFrom;
      prev.ts = it.ts; prev.group.keys.push(it.key);
      continue;
    }
    if (quiet) {
      folded.push({ ...it, title: it.delta > 0 ? "Trust rebuilt from clean evidence" : it.title, tone: it.delta > 0 ? "ok" : "neutral",
        group: { count: 1, first: it.ts, last: it.ts, keys: [it.key] } });
    } else folded.push(it);
  }
  items = folded;

  const byRecovery = (rid) => items.filter((i) => i.recoveryId === rid);
  const nearest = (cands, ts) => cands.sort((a, b) => Math.abs(a.ts - ts) - Math.abs(b.ts - ts))[0];
  const standalone = [];
  for (const e of [...events].sort((a, b) => a.received_at - b.received_at)) {
    if (consumed.has(e.id)) continue;
    const mine = e.device_id === deviceId || (!deviceId && e.device_id);
    if (!mine && !(includeSystem && !e.device_id)) continue;
    const d = e.details || {};
    if (RECOVERY_EVENTS.has(e.event_type) && d.recovery_id) {
      // same recovery id; the trust engine may stamp the transition with the device's latest evidence time
      const want = { recovery_started: "RECOVERING", recovery_verified: "VERIFIED", recovery_completed: "TRUSTED", recovery_failed: "QUARANTINED" }[e.event_type];
      const target = nearest(byRecovery(d.recovery_id).filter((i) => i.isState && i.stateTo === want && Math.abs(i.ts - e.received_at) < 60), e.received_at);
      if (target) { target.related.push(e); continue; }
    }
    if (e.event_type === "operator_action" && d.result === "success" && (d.action === "START_RECOVERY" || d.action === "ABORT_RECOVERY")) {
      const want = d.action === "START_RECOVERY" ? "RECOVERING" : "QUARANTINED";
      const target = nearest(items.filter((i) => i.isState && i.stateTo === want && Math.abs(i.ts - e.received_at) < 5), e.received_at);
      if (target) { target.operator = d.operator_id; target.related.push(e); continue; }
    }
    if (e.event_type === "operator_action" && d.result === "success" && d.action === "SET_EXPECTED_STATE"
        && events.some((x) => x.event_type === "twin_expected_updated" && x.device_id === e.device_id && Math.abs(x.received_at - e.received_at) < 2)) {
      continue;                                       // the "Known-good state updated" entry already names the operator
    }
    standalone.push(eventItem(e, sigAlg));
  }
  // Enforcement repeats for every refused message: show one entry per containment episode, with the count.
  const episodes = [];
  for (const it of standalone) {
    const e = it.events[0];
    if (e.event_type !== "quarantine_access_blocked") { episodes.push(it); continue; }
    const startedAt = Math.max(-Infinity, ...items.filter((i) => i.isState && i.stateTo === "QUARANTINED" && i.ts <= e.received_at + 1).map((i) => i.ts));
    const prev = episodes.find((x) => x.blockedEpisode === startedAt);
    if (prev) {
      prev.events.push(e);
      const times = prev.events.map((x) => x.received_at);
      prev.ts = Math.max(...times);
      prev.group = { count: prev.events.length, first: Math.min(...times), last: prev.ts, keys: prev.events.map((x) => `ev-${x.id}`) };
      prev.sub = `${prev.events.length} messages on the normal channel were refused at the gateway`;
    } else {
      episodes.push({ ...it, blockedEpisode: startedAt });
    }
  }
  return [...items, ...episodes].sort((a, b) => b.ts - a.ts);
}

// ---------------------------------------------------------------------------------------------- incidents
function memberDetail(modality, ref, { historyAsc, observations }) {
  if (modality === "PHYSICAL") {
    const m = /^msg:(\d+)/.exec(ref || "");
    const change = historyAsc.find((c) => (c.trigger_signals || []).includes(ref));
    const reason = change && (change.reasons || []).find((r) => r.signal === "physical_tamper");
    return { modality, ref, label: "Tamper switch reported open", auth: "DEVICE_HMAC",
      detail: m ? `Device message #${m[1]}, HMAC-SHA256 authenticated` : "Authenticated device message",
      provenance: reason && reason.provenance ? reason.provenance : null, ts: change ? change.timestamp : null };
  }
  if (modality === "VISUAL") {
    const id = (ref || "").replace(/^obs:/, "");
    const o = (observations || []).find((x) => x.observation_id === id);
    const simulated = !!(o && ((o.details && o.details.simulated) || (o.model && o.model.name === "synthetic")));
    return { modality, ref, auth: "SIGNER_MLDSA",
      label: o ? `${o.object || "Object"} in ${String(o.zone || "a restricted zone").replace(/_/g, " ")}` : "Signed visual rule violation",
      detail: o ? `Confidence ${(o.confidence ?? 0).toFixed(2)}, signed ${String(o.auth || "").replace(":", " by ")}` : `Observation ${id.slice(0, 8)}…`,
      provenance: simulated ? "synthetic detection signed with the real vision key" : o ? `${o.model?.name || "model"} ${o.model?.version || ""}`.trim() : null,
      ts: o ? o.received_at : null, observation: o || null };
  }
  return { modality, ref, label: MODALITIES[modality] || modality, detail: ref, auth: null, provenance: null, ts: null };
}

export function buildIncidents({ deviceId, history = [], snapshot = null, recoveries = [], events = [], observations = [], windowS = 60 }) {
  const historyAsc = [...history].sort((a, b) => a.timestamp - b.timestamp);
  const found = new Map();
  for (const c of historyAsc) if (c.incident && !found.has(c.incident.id)) found.set(c.incident.id, { inc: c.incident, change: c });
  if (snapshot && snapshot.incident && !found.has(snapshot.incident.id)) found.set(snapshot.incident.id, { inc: snapshot.incident, change: null });
  const recs = [...recoveries].sort((a, b) => a.started_at - b.started_at);
  const activeCaps = new Set(((snapshot && snapshot.caps) || []).map((c) => c.name));

  return [...found.values()].map(({ inc, change }) => {
    const started = inc.started;
    const quarantinedAt = historyAsc.find((c) => c.timestamp >= started - 0.001 && c.new_state === "QUARANTINED" && c.previous_state !== "QUARANTINED");
    const blocked = events.filter((e) => e.device_id === deviceId && e.event_type === "quarantine_access_blocked" && e.received_at >= started).length;
    const after = recs.filter((r) => r.started_at >= started);
    const done = after.find((r) => r.status === "completed");
    const active = after.find((r) => r.status === "active");
    const failed = after.filter((r) => r.status === "failed");
    const status = done ? "resolved" : active ? "recovering" : "open";
    const members = Object.entries(inc.members || {}).map(([m, ref]) => memberDetail(m, ref, { historyAsc, observations }));
    const times = members.map((m) => m.ts).filter(Number.isFinite);
    return {
      id: inc.id, deviceId, cls: inc.class, title: INCIDENT_CLASSES[inc.class] || inc.class,
      severity: inc.class === "confirmed_incident" ? "Critical" : "High",
      modalities: inc.modalities || [], members, started,
      spanS: times.length > 1 ? Math.max(...times) - Math.min(...times) : null, windowS,
      scoreBefore: change ? change.previous_score : null, scoreAfter: change ? change.new_score : null,
      stateBefore: change ? change.previous_state : null, stateAfter: change ? change.new_state : null,
      enforced: !!quarantinedAt, enforcedAt: quarantinedAt ? quarantinedAt.timestamp : null, blocked,
      ceilingActive: activeCaps.has(inc.class),
      status, recovery: done || active || null, failedAttempts: failed.length,
      resolvedAt: done ? done.updated_at : null,
    };
  }).sort((a, b) => b.started - a.started);
}

// ---------------------------------------------------------------------------------------------- recovery
/**
 * The eight visible steps of QUARANTINED -> TRUSTED, each done / active / pending / failed, derived from the
 * orchestrator record and the trust engine state. Never advances a step the backend has not recorded.
 */
export function recoverySteps({ rec = null, state = null, score = null, cfg = {} }) {
  const need = cfg.health_checks_required ?? null;
  const reentry = cfg.trusted_reentry_min ?? null;
  const restoreAt = cfg.quarantine_below ?? null;
  // A completed recovery followed by a new containment starts a new cycle: do not show the old one as current.
  const live = rec && !(rec.status === "completed" && state === "QUARANTINED") ? rec : null;
  const stage = live ? (live.status === "completed" ? "completed" : live.stage) : null;
  const clean = live ? live.consecutive_clean || 0 : 0;

  const steps = [
    { key: "quarantined", title: "Device quarantined", sub: "Threat contained; normal channel blocked" },
    { key: "started", title: "Recovery started", sub: live ? `By ${live.requested_by || "operator"}: ${live.reason || "no reason recorded"}` : "An operator starts recovery with a reason" },
    { key: "remediation", title: "Remediation", sub: live ? (live.command_acked ? "Known-good configuration applied and acknowledged" : "Command issued over the recovery channel; waiting for the device") : "Apply the known-good configuration" },
    { key: "health", title: "Health checks", sub: need ? `${Math.min(clean, need)} of ${need} consecutive clean reports` : "Consecutive clean authenticated reports", pips: need ? { on: Math.min(clean, need), of: need } : null },
    { key: "verified", title: "Verified", sub: "Digital state matches the known-good state; trust still has to be rebuilt" },
    { key: "ramp", title: "Trust ramp", sub: restoreAt !== null ? `Trust rebuilds from clean evidence; access returns at ${restoreAt}` : "Trust rebuilds from clean evidence", progress: Number.isFinite(score) && restoreAt ? { value: score, target: restoreAt } : null },
    { key: "recovered", title: "Access restored", sub: "Device back on the normal channel" },
    { key: "trusted", title: "Trusted", sub: reentry !== null ? `Trust reaches ${reentry}` : "Trust fully rebuilt", progress: Number.isFinite(score) && reentry ? { value: score, target: reentry } : null },
  ];
  // index of the step that is current for each orchestrator stage
  const CURRENT = { remediation_pending: 2, health_checks: 3, trust_ramp: 5, restoring: 7, completed: 8 };
  const cur = live ? CURRENT[stage] ?? 2 : state === "QUARANTINED" ? 1 : -1;
  return steps.map((s, i) => {
    let status = "pending";
    if (cur >= 0) status = i < cur ? "done" : i === cur ? (live && live.status === "failed" ? "failed" : "active") : "pending";
    return { ...s, status, idx: i + 1 };
  });
}

export function recoverySummary(rec) {
  if (!rec) return null;
  return { ...rec, failure: failureLabel(rec.failure_reason), stageLabel: rec.status === "completed" ? "Completed" : rec.status === "failed" ? "Failed" : rec.stage };
}

// ---------------------------------------------------------------------------------------------- evidence
export function chainView(entries = [], verify = null) {
  const asc = [...entries].sort((a, b) => a.seq - b.seq);
  const bad = new Map(((verify && verify.problems) || []).map((p) => [p.seq, p.reason]));
  return asc.map((e, i) => {
    const prev = asc[i - 1];
    const payload = parsePayload(e.payload);
    return { ...e, payload, linked: !prev || prev.seq !== e.seq - 1 ? null : prev.event_hash === e.prev_hash, problem: bad.get(e.seq) || null };
  });
}

export function evidenceIndex(entries = []) {
  const byTrust = new Map();
  for (const e of entries) {
    const p = parsePayload(e.payload);
    if (p.trust_event_id) byTrust.set(p.trust_event_id, e);
  }
  return byTrust;
}

export const EVIDENCE_GROUPS = {
  trust: ["trust_state_transition", "trust_score_change"],
  enforcement: ["quarantine_access_blocked", "recovery_channel_denied"],
  recovery: ["recovery_started", "remediation_acknowledged", "recovery_verified", "access_restored", "recovery_completed", "recovery_failed"],
  operator: ["operator_action", "twin_expected_updated"],
};

// ---------------------------------------------------------------------------------------------- chart
export function scoreSeries(historyDesc = [], snapshot = null, nowTs = null) {
  const asc = [...historyDesc].sort((a, b) => a.timestamp - b.timestamp);
  const pts = asc.map((c) => {
    const transition = c.kind === "created" || c.previous_state !== c.new_state;
    const p = primaryReason(c.reasons);
    const label = transition ? transitionTitle(c.previous_state, c.new_state, c.kind) : signalLabel(p && p.signal);
    return { ts: c.timestamp, score: c.new_score, state: c.new_state, from: c.previous_state, kind: c.kind, id: c.event_id,
      delta: (c.new_score ?? 0) - (c.previous_score ?? c.new_score ?? 0), transition, label };
  });
  if (snapshot && snapshot.status === "TRACKED" && pts.length) {
    const last = pts[pts.length - 1];
    const ts = Number.isFinite(nowTs) ? Math.max(nowTs, last.ts) : last.ts;
    if (snapshot.score !== last.score || ts > last.ts) pts.push({ ts, score: snapshot.score, state: snapshot.state, now: true, transition: false, label: "Now", delta: 0 });
  }
  return pts;
}

/** States a device actually passed through, in order (consecutive duplicates removed). */
export function statePath(historyDesc = []) {
  const asc = [...historyDesc].sort((a, b) => a.timestamp - b.timestamp);
  const out = [];
  for (const c of asc) {
    if (c.kind !== "created" && c.previous_state === c.new_state) continue;
    out.push({ state: c.new_state, ts: c.timestamp });
  }
  return out;
}

// ---------------------------------------------------------------------------------------------- connection
const RESTRICTED = new Set(["QUARANTINED", "RECOVERING", "VERIFIED"]);

/**
 * What to say about a device's connection. A quarantined device whose normal-channel messages the gateway is
 * refusing is not "offline": the gateway authenticated those messages and logged the refusal (throttled, about one
 * record per 10 s). Only a restricted device that is neither accepted on the recovery channel nor refused recently is
 * reported offline.
 */
export function connectionView({ device = null, state = null, events = [], now = null, windowS = 30 } = {}) {
  if (!device) return { tone: "neutral", label: "—", caption: "" };
  const status = device.status;
  if (RESTRICTED.has(state)) {
    let lastRefused = -Infinity;
    for (const e of events) {
      if (e.device_id === device.device_id && e.event_type === "quarantine_access_blocked") lastRefused = Math.max(lastRefused, e.received_at);
    }
    const refusedRecently = Number.isFinite(now) && now - lastRefused <= windowS;
    if (status === "ONLINE" && state !== "QUARANTINED") {
      return { tone: "crit", label: "Blocked by quarantine", caption: "Reporting on the recovery channel only" };
    }
    if (refusedRecently || status === "ONLINE") {
      return { tone: "crit", label: "Blocked by quarantine", caption: "Normal-channel messages are refused at the gateway" };
    }
    return { tone: "warn", label: "Offline", caption: "Quarantined and silent: no messages received recently" };
  }
  if (status === "ONLINE") return { tone: "ok", label: "Online", caption: "" };
  if (status === "OFFLINE") return { tone: "warn", label: "Offline", caption: "" };
  return { tone: "neutral", label: status === "ENROLLED" ? "Never connected" : status || "—", caption: "" };
}

/**
 * One stored vision observation as the Camera & vision page shows it: only what the gateway stored. `auth` is the
 * gateway's own verdict label ("ML-DSA-65:vision-1" for a verified signature; null when posted with the ingest
 * token). Synthetic detections (attack simulation) are flagged, never passed off as camera output.
 */
export function observationView(o) {
  const auth = o.auth || null;
  const [alg, signer] = auth && auth.includes(":") ? auth.split(":", 2) : [auth, null];
  const health = o.event_type === "camera_health";
  const details = o.details || {};
  return {
    key: o.observation_id,
    ts: o.received_at,
    deviceId: o.device_id,
    health,
    title: health ? `Camera health: ${(details.state || "unknown").replace(/_/g, " ")}` : `${cap(o.object || "object")} detected`,
    confidence: health || !Number.isFinite(o.confidence) ? null : o.confidence,
    zone: o.zone ? `${o.zone.replace(/_/g, " ")}${o.zone_kind && !o.zone.includes(o.zone_kind) ? ` (${o.zone_kind})` : ""}` : null,
    rule: o.anomaly ? (o.anomaly_reason || "rule matched").replace(/_/g, " ") : null,
    model: o.model ? `${o.model.name} ${o.model.version}` : null,
    signed: !!(alg && /ML-DSA/i.test(alg)),
    alg, signer,
    synthetic: !!((o.model && o.model.name === "synthetic") || details.simulated),
  };
}
