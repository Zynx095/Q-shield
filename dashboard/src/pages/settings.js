// Settings: connection, the signed-in operator, and (for admins) the operator roster.
import { html } from "../lib/html.js";
import { dateTime, duration } from "../lib/format.js";
import { explain } from "../lib/api.js";
import { S, listOperators } from "../store.js";
import { icon } from "../components/icons.js";
import { ambientEnabled } from "../components/ambient.js";
import { banner, loadingPanel } from "../components/states.js";
import { st } from "../components/status.js";

const roster = { data: null, error: null, at: 0, loading: false };

function loadRoster(rerender) {
  if (roster.loading || Date.now() - roster.at < 10000) return;
  roster.loading = true;
  listOperators().then((d) => { roster.data = d; roster.error = null; }, (e) => { roster.error = e; })
    .finally(() => { roster.loading = false; roster.at = Date.now(); rerender(); });
}

const ROLE = { viewer: "View only", operator: "View and act", admin: "View, act and manage operators" };

export function render({ rerender }) {
  const me = S.me || {};
  const sys = S.system || {};
  const tls = sys.transport === "https";
  if (me.role === "admin") loadRoster(rerender);
  return html`<div class="page-head"><div><h1 class="h-page">Settings</h1><p class="lead">Your session, this gateway connection and who can operate it.</p></div></div>
  <div class="grid grid-2">
    <section class="panel"><div class="panel-head"><h2 class="panel-title">${icon("user")}Signed in</h2></div>
      <div class="panel-body stack">
        <dl class="kv">
          <dt>Operator</dt><dd class="strong">${me.operator_id}</dd>
          <dt>Name</dt><dd>${me.display_name}</dd>
          <dt>Role</dt><dd>${me.role} <span class="caption">${ROLE[me.role] || ""}</span></dd>
          <dt>Expires</dt><dd>${me.expires_at ? dateTime(me.expires_at) : "No expiry"}</dd>
        </dl>
        ${me.bootstrap ? banner("warn", "alert", "Shared bootstrap token.", "Actions are attributed to bootstrap-admin, not to a person. Create named operators (python scripts/operators.py create) and disable the shared token.") : ""}
        <div><button class="btn" type="button" data-action="signout">${icon("logout")}Sign out</button></div>
        <p class="caption">Your token is kept only in this browser tab's session storage and is never shown on screen.</p>
      </div></section>
    <section class="panel"><div class="panel-head"><h2 class="panel-title">${icon("server")}Gateway connection</h2></div>
      <div class="panel-body stack">
        <dl class="kv">
          <dt>Gateway</dt><dd class="mono">${location.origin}</dd>
          <dt>Transport</dt><dd>${tls ? st("ok", "HTTPS") : st("warn", "HTTP, cleartext")}</dd>
          <dt>Status</dt><dd>${S.connected ? st("ok", "Online") : S.connected === false ? st("crit", "Offline") : "Connecting"}</dd>
          <dt>Refresh</dt><dd>Every 2 s</dd>
          <dt>Gateway clock</dt><dd>${Math.abs(S.clockOffset) > 120 ? `${duration(Math.abs(S.clockOffset))} ${S.clockOffset > 0 ? "ahead of" : "behind"} this browser (time-lapse)` : "In step with this browser"}</dd>
          <dt>Recovery timer</dt><dd>${sys.recovery && sys.recovery.background_timer_s ? `Deadlines checked every ${sys.recovery.background_timer_s} s` : "Request-driven only"}</dd>
        </dl>
        ${!tls ? banner("warn", "alert", "Not encrypted.", "Use HTTPS (QSHIELD_TLS_CERT, QSHIELD_TLS_KEY) outside a trusted network.") : ""}
      </div></section>
  </div>
  <section class="panel section"><div class="panel-head"><h2 class="panel-title">${icon("eye")}Display</h2></div>
    <div class="panel-body stack-sm">
      <label class="check-row"><input type="checkbox" data-action="ambient" ${ambientEnabled() ? "checked" : ""}>
        <span><span class="strong">Ambient background</span>
        <span class="caption">Faint algorithm names drifting behind the panels, tinted by the security posture. Turn it off on low-power machines. Remembered for this tab.</span></span></label>
      ${matchMedia("(prefers-reduced-motion: reduce)").matches ? html`<p class="caption">This system asks for reduced motion: the background stays still and sections appear without animation.</p>` : ""}
    </div></section>
  ${me.role === "admin" ? html`<section class="panel section"><div class="panel-head"><h2 class="panel-title">${icon("user")}Operators</h2><span class="meta">Managed with python scripts/operators.py or the admin API</span></div>
    <div class="panel-body table-wrap">${roster.error ? banner("crit", "xCircle", "Could not load operators.", explain(roster.error))
      : !roster.data ? loadingPanel(3)
      : roster.data.length ? html`<table class="table"><caption class="sr-only">Named operators</caption>
        <thead><tr><th scope="col">Operator</th><th scope="col">Name</th><th scope="col">Role</th><th scope="col">Status</th><th scope="col">Created</th><th scope="col">Expires</th></tr></thead>
        <tbody>${roster.data.map((o) => html`<tr data-key="op-${o.operator_id}"><td class="mono">${o.operator_id}</td><td>${o.display_name}</td><td>${o.role}</td>
          <td>${o.status === "active" ? st("ok", "Active") : st("crit", `Revoked${o.revoked_by ? ` by ${o.revoked_by}` : ""}`)}</td>
          <td>${dateTime(o.created_at)}${o.created_by ? html` <span class="caption">by ${o.created_by}</span>` : ""}</td><td>${o.expires_at ? dateTime(o.expires_at) : "Never"}</td></tr>`)}</tbody></table>`
      : html`<p class="meta">No named operators yet. Only the shared bootstrap token can sign in.</p>`}</div></section>` : ""}`;
}
