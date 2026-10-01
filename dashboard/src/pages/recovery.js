// Recovery: the orchestrated path from QUARANTINED back to TRUSTED, with the operator controls that drive it.
import { html } from "../lib/html.js";
import { STAGES, failureLabel, stateMeta } from "../lib/copy.js";
import { clock, countdown, dateTime, duration } from "../lib/format.js";
import { S, focusId, gatewayNow } from "../store.js";
import { deviceModel, flashTo } from "../model.js";
import { icon } from "../components/icons.js";
import { stepper } from "../components/recovery.js";
import { channels } from "../components/rail.js";
import { banner, empty, loadingPanel } from "../components/states.js";
import { stateBadge, st } from "../components/status.js";
import { devicePicker } from "./overview.js";
import { actionButtons } from "./device.js";

const STATUS = { active: ["proc", "refresh", "In progress"], completed: ["ok", "checkCircle", "Completed"], failed: ["crit", "xCircle", "Failed"] };

function deadlineRow(r) {
  if (r.status !== "active") return "";
  const now = gatewayNow();
  const verifying = r.stage === "remediation_pending" || r.stage === "health_checks";
  const due = verifying ? r.deadline : r.ramp_deadline;
  if (!Number.isFinite(due)) return "";
  const left = due - now;
  return html`<dt>${verifying ? "Must verify within" : "Trust must rebuild within"}</dt>
    <dd><span class="num strong" style="${left < 120 ? "color:var(--crit)" : ""}">${left > 0 ? countdown(left) : "overdue"}</span> <span class="caption">gateway clock, by ${clock(due)}; missing it returns the device to quarantine</span></dd>`;
}

function currentPanel(m) {
  const r = m.recovery;
  const state = m.snapshot && m.snapshot.state;
  if (!r || (r.status === "completed" && state === "QUARANTINED")) {
    return html`<section class="panel" data-reveal>${state === "QUARANTINED"
      ? empty({ title: "Ready to recover", text: "The device is quarantined. Starting recovery opens remediation over the recovery channel; normal access stays blocked until it is verified and trusted again.", iconName: "refresh" })
      : empty({ title: "No recovery needed", text: `Recovery cannot be started while the device is not quarantined. It is currently ${stateMeta(state).label.toLowerCase()}.`, iconName: "shieldCheck", ok: state === "TRUSTED" })}</section>`;
  }
  const [tone, ic, word] = STATUS[r.status] || STATUS.active;
  const cmd = r.command || {};
  return html`<section class="panel" aria-labelledby="rc-title" data-reveal>
    <div class="panel-head"><h2 class="panel-title" id="rc-title">${icon("refresh")}<span class="mono">${r.recovery_id}</span></h2><span class="badge tone-${tone}">${icon(ic)}${word}</span></div>
    <div class="panel-body stack">
      ${r.status === "failed" ? banner("crit", "xCircle", "Recovery failed.", failureLabel(r.failure_reason)) : ""}
      <dl class="kv">
        <dt>Started</dt><dd>${dateTime(r.started_at)} by <span class="strong">${r.requested_by || "operator"}</span></dd>
        <dt>Reason</dt><dd>${r.reason}</dd>
        <dt>Stage</dt><dd>${r.status === "completed" ? "Completed" : STAGES[r.stage] || r.stage}</dd>
        ${deadlineRow(r)}
        <dt>Remediation</dt><dd><span class="mono">${cmd.action}</span> to <span class="mono">${cmd.cfg_hash || "—"}</span> / <span class="mono">${cmd.fw_version || "—"}</span>
          <div>${r.command_acked ? st("ok", "Acknowledged by the device") : st("na", "Waiting for the device to acknowledge")}</div>
          ${cmd.note ? html`<div class="caption">${cmd.note}</div>` : ""}</dd>
        <dt>Health checks</dt><dd>${(r.health || []).length
          ? html`<ul class="stack-sm" style="gap:4px">${r.health.slice(-6).map((h) => html`<li class="row" style="gap:8px">${h.clean ? st("ok", "Clean") : st("crit", "Not clean")}<span class="caption">${clock(h.t)}: tamper ${h.tamper === false ? "closed" : h.tamper ? "OPEN" : "not reported"}, twin ${String(h.twin).toLowerCase()}</span></li>`)}</ul>`
          : html`<span class="caption">None yet. Checks start after the device acknowledges remediation.</span>`}</dd>
        <dt>Current trust</dt><dd>${stateBadge(m.snapshot && m.snapshot.state)} <span class="num strong">${m.snapshot ? m.snapshot.score : "—"}</span></dd>
      </dl>
      ${channels(m.access, { change: flashTo(m.id) })}
    </div>
  </section>`;
}

export function render() {
  const head = (id) => html`<div class="page-head"><div><h1 class="h-page">Recovery</h1>
    <p class="lead">Self-healing here means software remediation and earned trust: the device is reconfigured, checked against its known-good state and must rebuild trust from clean evidence. It cannot repair hardware.</p></div>
    <div class="stack-sm" style="align-items:flex-end">${id ? devicePicker(id) : ""}${id ? actionButtons(id) : ""}</div></div>`;
  if (!S.loaded) return html`${head(null)}${loadingPanel(8)}`;
  const id = focusId();
  if (!id) return html`${head(null)}<section class="panel">${empty({ title: "No devices enrolled", iconName: "devices" })}</section>`;
  const m = deviceModel(id);
  if (m.recoveryUnavailable) return html`${head(null)}<section class="panel">${empty({ title: "Recovery is not enabled on this gateway", text: "Start the gateway with the trust engine and recovery orchestrator enabled.", iconName: "refresh" })}</section>`;
  const past = (m.recoveries || []).filter((r) => !m.recovery || r.recovery_id !== m.recovery.recovery_id || r.status !== "active");
  return html`${head(id)}
    <div class="grid split-5-7">
      <section class="panel" aria-labelledby="steps-title" data-reveal>
        <div class="panel-head"><h2 class="panel-title" id="steps-title">${icon("refresh")}${id}: path back to trusted</h2></div>
        <div class="panel-body">${stepper(m.steps)}</div>
      </section>
      ${currentPanel(m)}
    </div>
    ${past.length ? html`<section class="panel section" data-reveal><div class="panel-head"><h2 class="panel-title">${icon("clock")}Recovery history</h2></div>
      <div class="panel-body table-wrap"><table class="table"><caption class="sr-only">Previous recoveries</caption>
        <thead><tr><th scope="col">Recovery</th><th scope="col">Started</th><th scope="col">By</th><th scope="col">Outcome</th><th scope="col">Duration</th></tr></thead>
        <tbody>${past.slice().reverse().map((r) => html`<tr data-key="rh-${r.recovery_id}"><td class="mono">${r.recovery_id}</td><td>${dateTime(r.started_at)}</td><td>${r.requested_by || "—"}</td>
          <td>${r.status === "completed" ? st("ok", "Completed") : r.status === "failed" ? html`${st("crit", "Failed")} <span class="caption">${failureLabel(r.failure_reason)}</span>` : st("na", "In progress")}</td>
          <td class="num">${duration((r.updated_at || r.started_at) - r.started_at)}</td></tr>`)}</tbody></table></div></section>` : ""}`;
}
