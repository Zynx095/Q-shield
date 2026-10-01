// Incidents: correlated evidence the trust engine confirmed, newest first; active ones on top.
import { html } from "../lib/html.js";
import { S } from "../store.js";
import { fleet } from "../model.js";
import { incidentCard } from "../components/incident.js";
import { empty, loadingPanel } from "../components/states.js";

export function render() {
  const f = S.loaded ? fleet() : null;
  const head = html`<div class="page-head"><div><h1 class="h-page">Incidents</h1>
    <p class="lead">An incident is confirmed only when independent evidence agrees inside the correlation window, such as an authenticated tamper report and a signed camera observation.</p></div></div>`;
  if (!f) return html`${head}${loadingPanel(6)}`;
  if (!f.incidents.length) {
    return html`${head}<section class="panel">${empty({ title: "All clear. No security incidents.", text: "Single signals lower trust, but an incident needs two independent kinds of evidence. None has been correlated.", iconName: "shieldCheck", ok: true })}</section>`;
  }
  const order = { open: 0, recovering: 1, resolved: 2 };
  const list = [...f.incidents].sort((a, b) => order[a.status] - order[b.status] || b.started - a.started);
  const open = list.filter((i) => i.status !== "resolved");
  const past = list.filter((i) => i.status === "resolved");
  return html`${head}
    <div class="stack">
      ${open.length ? html`<h2 class="h-section">Active</h2>${open.map((i) => incidentCard(i))}` : html`<section class="panel">${empty({ title: "No active incidents", text: "Every recorded incident has been resolved by a completed recovery.", iconName: "shieldCheck", ok: true })}</section>`}
      ${past.length ? html`<h2 class="h-section" style="margin-top:8px">Resolved</h2>${past.map((i) => incidentCard(i))}` : ""}
    </div>`;
}
