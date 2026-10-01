// Incident card: what was correlated, how trust fell, what the gateway did about it, and where it stands now.
import { html } from "../lib/html.js";
import { MODALITIES } from "../lib/copy.js";
import { clock, dateTime, duration } from "../lib/format.js";
import { authTag, simTag, stateBadge } from "./status.js";
import { icon } from "./icons.js";

const STATUS = {
  open: { tone: "crit", icon: "lock", text: "Open" },
  recovering: { tone: "proc", icon: "refresh", text: "In recovery" },
  resolved: { tone: "ok", icon: "checkCircle", text: "Resolved" },
};

/** Two evidence streams converging into one incident, then into the gateway's action. */
function convergence(inc) {
  const [a, b] = inc.members;
  const name = (m) => (m ? (MODALITIES[m.modality] || m.modality) : "");
  const actionText = inc.enforced ? "Quarantine enforced" : "Recorded";
  return html`<figure class="converge" aria-label="${name(a)} and ${name(b)} correlated into ${inc.id}; ${actionText}">
    <svg viewBox="0 0 520 120" role="presentation">
      <defs><marker id="cv-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path class="cv-head" d="M0 0L10 5L0 10z"/></marker></defs>
      <rect class="cv-box" x="1" y="8" width="150" height="40" rx="8"/>
      <text class="cv-text" x="76" y="33" text-anchor="middle">${name(a)}</text>
      <rect class="cv-box" x="1" y="72" width="150" height="40" rx="8"/>
      <text class="cv-text" x="76" y="97" text-anchor="middle">${name(b)}</text>
      <path class="cv-path" d="M151 28 C 196 28 196 60 236 60 M151 92 C 196 92 196 60 236 60"/>
      <path class="cv-inc" d="M236 60 L276 38 L316 60 L276 82 Z"/>
      <text class="cv-inc-text" x="276" y="64" text-anchor="middle">INCIDENT</text>
      <path class="cv-path" d="M316 60 H 356" marker-end="url(#cv-arrow)"/>
      <rect class="cv-act ${inc.enforced ? "on" : ""}" x="362" y="40" width="156" height="40" rx="8"/>
      <text class="cv-act-text ${inc.enforced ? "on" : ""}" x="440" y="65" text-anchor="middle">${actionText}</text>
    </svg>
  </figure>`;
}

export function incidentCard(inc, { compact = false } = {}) {
  const st = STATUS[inc.status] || STATUS.open;
  const statusLine = inc.status === "resolved"
    ? `Resolved by ${inc.recovery.recovery_id} at ${clock(inc.resolvedAt)}`
    : inc.status === "recovering" ? `Recovery ${inc.recovery.recovery_id} in progress` : "Waiting for an operator to start recovery";
  return html`<article class="incident is-${inc.status === "open" ? "active" : inc.status} ${compact ? "is-compact" : ""}" data-key="inc-${inc.id}" aria-labelledby="inc-${inc.id}-t">
    <div class="incident-bar"></div>
    <header class="incident-head">
      <div class="stack-sm" style="gap:4px">
        <div class="row" style="gap:8px">
          <span class="badge tone-crit">${icon("alert")}${inc.cls === "confirmed_incident" ? "Confirmed incident" : "Correlated incident"}</span>
          <span class="badge tone-${st.tone}">${icon(st.icon)}${st.text}</span>
        </div>
        <h3 class="h-section" id="inc-${inc.id}-t">${inc.title}</h3>
        <div class="incident-id">${inc.id} on <a href="#/devices/${encodeURIComponent(inc.deviceId)}">${inc.deviceId}</a>, ${dateTime(inc.started)}</div>
      </div>
      <div class="stack-sm" style="align-items:flex-end;gap:4px">
        <span class="caption">Severity</span>
        <span class="strong" style="color:var(--crit)">${inc.severity}</span>
      </div>
    </header>
    <div class="incident-body">
      <div class="stack">
        ${Number.isFinite(inc.scoreAfter) ? html`<div>
          <div class="caption">Trust when the incident was confirmed</div>
          <div class="scorepair"><span class="from">${inc.scoreBefore}</span>${icon("arrowRight")}<span class="to">${inc.scoreAfter}</span>${inc.stateAfter ? stateBadge(inc.stateAfter) : ""}</div>
        </div>` : ""}
        <div>
          <div class="caption" style="margin-bottom:8px">Evidence</div>
          <ul class="checklist">
            ${inc.members.map((m) => html`<li>${icon("checkCircle")}<div>
              <span class="strong">${MODALITIES[m.modality] || m.modality}</span>: ${m.label} ${authTag(m.auth)}
              <span class="caption">${m.detail}${m.ts ? `, ${clock(m.ts)}` : ""}</span>
              ${m.provenance && /simulat|synthetic/i.test(m.provenance) ? html`<span class="caption">${simTag(m.provenance)} ${m.provenance}</span>` : ""}
            </div></li>`)}
            <li>${icon("checkCircle")}<div><span class="strong">Correlation window satisfied</span>
              <span class="caption">${Number.isFinite(inc.spanS) ? (inc.spanS < 1 ? "Both signals less than a second apart" : `Both signals within ${duration(inc.spanS)}`) : "Both modalities present"}; window ${duration(inc.windowS)}</span></div></li>
          </ul>
        </div>
      </div>
      <div class="stack">
        ${compact ? "" : convergence(inc)}
        <div>
          <div class="caption" style="margin-bottom:6px">Action</div>
          ${inc.enforced
            ? html`<div class="banner crit">${icon("lock")}<div><b>Quarantine enforced at ${clock(inc.enforcedAt)}</b> <span class="banner-text">Normal channel blocked${inc.blocked ? `; ${inc.blocked} message${inc.blocked > 1 ? "s" : ""} refused since` : ""}. Recovery channel kept open.</span></div></div>`
            : html`<div class="banner">${icon("info")}<div class="banner-text">Recorded; the device was not quarantined by this incident.</div></div>`}
        </div>
        <div>
          <div class="caption" style="margin-bottom:6px">Status</div>
          <div class="row"><span class="strong">${statusLine}</span>${inc.failedAttempts ? html`<span class="caption">${inc.failedAttempts} earlier attempt${inc.failedAttempts > 1 ? "s" : ""} failed</span>` : ""}</div>
          ${inc.status !== "resolved" ? html`<div style="margin-top:10px"><a class="btn sm" href="#/recovery">${icon("refresh")}Open recovery</a></div>` : ""}
        </div>
      </div>
    </div>
  </article>`;
}
