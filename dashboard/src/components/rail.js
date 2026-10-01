// The device story rail (TRUSTED -> ... -> TRUSTED) and the enforcement channels that quarantine actually controls.
import { html } from "../lib/html.js";
import { STORY, stateMeta } from "../lib/copy.js";
import { clock } from "../lib/format.js";
import { icon } from "./icons.js";

/**
 * Map the states a device actually passed through onto the seven-step story. Only states that really happened are
 * marked; the current one is highlighted. A fresh cycle (e.g. a second incident) restarts from the last TRUSTED.
 */
export function storyProgress(path, current) {
  // find the start of the latest cycle: the last TRUSTED entry that is followed by a non-TRUSTED state, if any
  let start = 0;
  for (let i = 0; i < path.length; i++) if (path[i].state === "TRUSTED" && i < path.length - 1) start = i;
  const cycle = path.slice(start);
  const marks = STORY.map(() => null);
  let pos = -1;
  for (const p of cycle) {
    const from = pos + 1;
    let idx = STORY.indexOf(p.state, from);
    if (idx === -1) idx = STORY.lastIndexOf(p.state);
    if (idx === -1) continue;
    if (idx < pos) { for (let k = idx + 1; k < marks.length; k++) marks[k] = null; }   // went backwards (e.g. back to quarantine)
    marks[idx] = p.ts;
    pos = idx;
  }
  if (pos === -1 && current) pos = Math.max(0, STORY.indexOf(current));
  return { marks, pos };
}

export function stateRail(path, current) {
  const { marks, pos } = storyProgress(path, current);
  return html`<ol class="rail" aria-label="Security story: where this device is now">${STORY.map((s, i) => {
    const m = stateMeta(s);
    const now = i === pos;
    const past = !now && marks[i] !== null && i < pos;
    return html`<li class="rail-step ${now ? "is-now" : past ? "is-past" : ""}" data-tone="${m.tone}" ${now ? html`aria-current="step"` : ""}>
      <span class="rail-node">${icon(now || past ? m.icon : "dot")}</span>
      <span class="rail-label">${s}</span>
      <span class="rail-when">${marks[i] !== null && (now || past) ? clock(marks[i]) : ""}</span>
    </li>`;
  })}</ol>`;
}

const REASONS = {
  ok: "Traffic accepted",
  device_quarantined: "Blocked: device is quarantined",
  recovery_channel_not_open: "Opens only during quarantine and recovery",
};

const BLOCKED_WHY = { QUARANTINED: "Blocked: device is quarantined", RECOVERING: "Blocked until recovery restores access", VERIFIED: "Blocked until trust is rebuilt" };

/** `change`: the state the device has just moved to (model.flashTo); drives the one-shot seal / open / restore moment. */
export function channels(access, { change = null } = {}) {
  if (!access) return html`<div class="channels"><div class="channel"><span class="channel-icon">${icon("minus")}</span><span class="channel-name">Normal channel</span><span class="channel-state">Unknown</span></div><div class="channel"><span class="channel-icon">${icon("minus")}</span><span class="channel-name">Recovery channel</span><span class="channel-state">Unknown</span></div></div>`;
  const n = access.normal || {}, r = access.recovery || {};
  const sealing = change === "QUARANTINED", restoring = change === "RECOVERED";
  return html`<div class="channels" role="group" aria-label="Gateway enforcement">
    <div class="channel ${n.allowed ? "is-open" : "is-blocked"} ${sealing && !n.allowed ? "is-sealing" : ""} ${restoring && n.allowed ? "is-restoring" : ""}">
      <span class="channel-icon">${icon(n.allowed ? "check" : "x")}</span>
      <span class="channel-name">Normal channel</span>
      <span class="channel-state">${n.allowed ? "Open" : "Blocked"}</span>
      <span class="channel-why">${!n.allowed && BLOCKED_WHY[access.trust_state] ? BLOCKED_WHY[access.trust_state] : REASONS[n.reason] || n.reason || ""}</span>
    </div>
    <div class="channel ${r.allowed ? "is-open" : "is-closed"} ${sealing && r.allowed ? "is-opening" : ""}">
      <span class="channel-icon">${icon(r.allowed ? "refresh" : "minus")}</span>
      <span class="channel-name">Recovery channel</span>
      <span class="channel-state">${r.allowed ? "Available" : "Closed"}</span>
      <span class="channel-why">${r.allowed ? "Remediation and health checks only" : REASONS[r.reason] || r.reason || ""}</span>
    </div>
  </div>`;
}
