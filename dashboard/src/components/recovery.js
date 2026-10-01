// Recovery stepper: QUARANTINED -> recovery -> remediation -> health checks -> VERIFIED -> trust ramp ->
// access restored -> TRUSTED. ✓ done, ● active, ○ pending, × failed.
import { html } from "../lib/html.js";
import { icon } from "./icons.js";

/** `advancing`: the device has just moved forward (model.advancedTo); the active step pulses once. */
export function stepper(steps, { compact = false, advancing = false } = {}) {
  return html`<ol class="stepper ${advancing ? "is-advancing" : ""}" aria-label="Recovery progress">${steps.map((s) => {
    const label = { done: "completed", active: "in progress", pending: "pending", failed: "failed" }[s.status];
    return html`<li class="step is-${s.status}" data-key="st-${s.key}" ${s.status === "active" ? html`aria-current="step"` : ""}>
      <span class="step-node" aria-hidden="true">${s.status === "done" ? icon("check") : s.status === "failed" ? icon("x") : s.status === "active" ? "" : s.idx}</span>
      <div class="step-text">
        <div class="step-title">${s.title}<span class="sr-only"> (${label})</span>
          ${s.pips ? html`<span class="pips" aria-hidden="true">${Array.from({ length: s.pips.of }, (_, i) => html`<i class="${i < s.pips.on ? "on" : ""}"></i>`)}</span>` : ""}
        </div>
        ${!compact || s.status === "active" || s.status === "failed" ? html`<div class="step-sub">${s.sub}</div>` : ""}
        ${s.progress && (s.status === "active") ? html`<div class="progress" style="margin-top:8px;max-width:280px" role="progressbar" aria-valuemin="0" aria-valuemax="${s.progress.target}" aria-valuenow="${Math.min(s.progress.value, s.progress.target)}" aria-label="${s.title}: ${s.progress.value} of ${s.progress.target}">
          <i style="width:${Math.min(100, (s.progress.value / s.progress.target) * 100).toFixed(1)}%"></i></div>
          <div class="caption" style="margin-top:4px">Trust ${s.progress.value} of ${s.progress.target}</div>` : ""}
      </div>
    </li>`;
  })}</ol>`;
}
