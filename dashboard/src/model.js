// View models: everything a screen needs about a device, derived from the live store in one place.
import { S, gatewayNow } from "./store.js";
import {
  buildIncidents, buildTimeline, chainView, connectionView, factorView, posture, recoverySteps, scoreBreakdown, scoreSeries,
  statePath,
} from "./lib/derive.js";

export const UI = {
  expanded: new Set(),
  limits: {},
  chartMode: "sequence",
  chartWidth: {},
  evidenceFilter: "all",
  evidenceDevice: "all",
  evidenceLimit: 40,
  menuOpen: false,
  flash: null,               // { deviceId, until }
  showMath: false,
};

export const limitOf = (key, dflt) => UI.limits[key] ?? dflt;

/** The state a device just changed to, while the transition is fresh (UI.flash, set in main.js); otherwise null. */
export function flashTo(id) {
  const f = UI.flash;
  return f && f.deviceId === id && f.until > Date.now() ? f.to : null;
}

/** Has the device just moved forward along the recovery path (into RECOVERING or VERIFIED)? */
export const advancedTo = (id) => ["RECOVERING", "VERIFIED"].includes(flashTo(id));

export function thresholds() {
  const t = S.system && S.system.trust;
  return t && t.enabled ? t : null;
}

export function recoveryCfg() {
  return { ...((S.system && S.system.recovery) || {}), ...(thresholds() || {}) };
}

export function deviceModel(id) {
  if (!id) return null;
  const device = S.devices.find((d) => d.device_id === id) || null;
  const snapshot = S.trust.get(id) || null;
  const d = S.detail.get(id) || {};
  const history = d.history || [];
  const rec = d.recovery || null;
  const current = rec ? rec.current : null;
  const recoveries = rec ? rec.history || [] : [];
  const evIndex = S.evidence.index;
  const sigAlg = (S.system && S.system.pqc && S.system.pqc.sig_algorithm) || "ML-DSA";
  const timeline = buildTimeline({ history, events: S.events, deviceId: id, evidenceByTrustEvent: evIndex, sigAlg });
  const incidents = buildIncidents({ deviceId: id, history, snapshot, recoveries, events: S.events, observations: S.observations,
    windowS: thresholds() ? thresholds().correlation_window_s : 60 });
  return {
    id, device, snapshot, history, access: d.access || null, twin: d.twin || null,
    recovery: current, recoveries, recoveryUnavailable: !!d.unavailable,
    factors: factorView(snapshot, history),
    connection: connectionView({ device, state: snapshot && snapshot.state, events: S.events, now: gatewayNow() }),
    sigAlg,
    breakdown: scoreBreakdown(snapshot),
    timeline, incidents,
    path: statePath(history),
    steps: recoverySteps({ rec: current, state: snapshot && snapshot.state, score: snapshot && snapshot.score, cfg: recoveryCfg() }),
    series: scoreSeries(history, snapshot, gatewayNow()),
    loaded: S.detail.has(id),
  };
}

export function fleet() {
  const models = S.devices.map((d) => deviceModel(d.device_id));
  const incidents = models.flatMap((m) => m.incidents);
  const open = incidents.filter((i) => i.status !== "resolved");
  const activeRecoveries = models.filter((m) => m.recovery && m.recovery.status === "active");
  const simulated = S.devices.filter((d) => d.hw === "software-agent").map((d) => d.device_id);
  return {
    models, incidents, open, activeRecoveries, simulated,
    posture: posture({ connected: S.connected !== false, trustList: [...S.trust.values()], openIncidents: open.length }),
  };
}

export function evidenceBlocks() {
  return chainView(S.evidence.entries, S.evidence.verify);
}
