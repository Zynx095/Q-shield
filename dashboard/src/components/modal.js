// Operator action dialog. Imperative (it owns its DOM) so the 2-second refresh never disturbs typing.
// Shows the gateway's real response: success only when the API said so, otherwise its refusal, verbatim.
import { html, raw } from "../lib/html.js";
import { render } from "../lib/morph.js";
import { explain } from "../lib/api.js";
import { icon } from "./icons.js";
import { stateBadge } from "./status.js";

let current = null;

function root() {
  let r = document.getElementById("modal-root");
  if (!r) { r = document.createElement("div"); r.id = "modal-root"; document.body.appendChild(r); }
  return r;
}

function fieldView(f, value, error) {
  const id = `mf-${f.name}`;
  const common = `id="${id}" name="${f.name}" ${f.required ? "required" : ""} ${f.maxLength ? `maxlength="${f.maxLength}"` : ""} aria-describedby="${id}-h"`;
  return html`<div class="field ${error ? "has-error" : ""}">
    <label for="${id}">${f.label}${f.required ? "" : html` <span class="caption">(optional)</span>`}</label>
    ${f.type === "textarea"
      ? html`<textarea class="textarea" ${raw(common)} placeholder="${f.placeholder || ""}">${value}</textarea>`
      : html`<input class="input ${f.mono ? "mono" : ""}" type="text" ${raw(common)} value="${value}" placeholder="${f.placeholder || ""}" autocomplete="off" spellcheck="false">`}
    <span class="hint" id="${id}-h">${f.hint || ""}</span>
    ${error ? html`<span class="field-error">${error}</span>` : ""}
  </div>`;
}

function view(m) {
  const busy = m.phase === "busy", done = m.phase === "done";
  return html`<div class="modal-backdrop" data-modal-backdrop>
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" aria-describedby="modal-intro">
      <div class="modal-head">
        <span class="modal-icon ${m.tone === "crit" ? "crit" : ""}">${icon(m.icon)}</span>
        <div>
          <h2 class="h-section" id="modal-title">${m.title}</h2>
          <p class="meta" id="modal-intro" style="margin-top:4px">${m.intro}</p>
        </div>
      </div>
      <form class="modal-body" novalidate data-modal-form>
        <dl class="kv">
          <dt>Device</dt><dd class="strong">${m.deviceId}</dd>
          <dt>Current state</dt><dd>${stateBadge(m.state)}</dd>
          ${m.context || ""}
        </dl>
        ${done ? "" : m.fields.map((f) => fieldView(f, m.values[f.name] ?? "", m.errors[f.name]))}
        ${m.result ? html`<div class="result ${m.result.ok ? "ok" : "crit"}" role="${m.result.ok ? "status" : "alert"}">
          <div class="row" style="gap:8px">${icon(m.result.ok ? "checkCircle" : "xCircle", 'style="width:18px;height:18px"')}<b>${m.result.title}</b></div>
          <div style="margin-top:4px;color:var(--ink-2)">${m.result.text}</div>
          ${m.result.raw ? html`<pre>${m.result.raw}</pre>` : ""}
        </div>` : ""}
        <button type="submit" hidden></button>
      </form>
      <div class="modal-foot">
        ${done
          ? html`<button class="btn primary" type="button" data-modal-close>Done</button>`
          : html`<button class="btn ghost" type="button" data-modal-close ${busy ? "disabled" : ""}>Cancel</button>
                 <button class="btn ${m.tone === "crit" ? "danger-solid" : "accent"}" type="button" data-modal-submit ${busy ? "disabled" : ""}>
                   ${busy ? html`<span class="spinner" aria-hidden="true"></span>${m.busyLabel}` : html`${icon(m.icon)}${m.confirmLabel}`}</button>`}
      </div>
    </div>
  </div>`;
}

function paint() {
  if (!current) { render(root(), html``); return; }
  render(root(), view(current));
}

function readValues() {
  const form = root().querySelector("[data-modal-form]");
  if (!form) return;
  for (const f of current.fields) {
    const el = form.elements.namedItem(f.name);
    if (el) current.values[f.name] = el.value;
  }
}

function validate() {
  const errors = {};
  for (const f of current.fields) {
    const v = String(current.values[f.name] ?? "").trim();
    if (f.required && !v) errors[f.name] = `${f.label} is required.`;
    else if (v && f.minLength && v.length < f.minLength) errors[f.name] = `Use at least ${f.minLength} characters.`;
    else if (v && f.maxLength && v.length > f.maxLength) errors[f.name] = `Use at most ${f.maxLength} characters.`;
  }
  if (current.validate) Object.assign(errors, current.validate(current.values) || {});
  current.errors = errors;
  return !Object.keys(errors).length;
}

async function submit() {
  if (!current || current.phase === "busy" || current.phase === "done") return;
  readValues();
  if (!validate()) { current.result = null; paint(); focusFirstError(); return; }
  current.phase = "busy"; current.result = null; paint();
  const m = current;
  try {
    const res = await m.submit(Object.fromEntries(Object.entries(m.values).map(([k, v]) => [k, String(v).trim()])));
    if (current !== m) return;
    m.phase = "done";
    m.result = { ok: true, ...m.describe(res), raw: JSON.stringify(res, null, 2).slice(0, 2000) };
  } catch (err) {
    if (current !== m) return;
    m.phase = "form";
    m.result = { ok: false, title: "The gateway refused this action", text: explain(err),
      raw: err && err.status ? `HTTP ${err.status}: ${typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail)}` : "" };
  }
  paint();
  const target = root().querySelector(m.phase === "done" ? "[data-modal-close]" : ".result");
  if (target) {
    if (!target.matches("button")) target.setAttribute("tabindex", "-1");
    target.focus();
  }
}

function focusFirstError() {
  const el = root().querySelector(".has-error .input, .has-error .textarea");
  if (el) el.focus();
}

export function closeModal() {
  if (!current || current.phase === "busy") return;
  const back = current.returnFocus;
  current = null;
  paint();
  document.removeEventListener("keydown", onKey, true);
  if (back && document.contains(back)) back.focus();
}

function onKey(e) {
  if (!current) return;
  if (e.key === "Escape") { e.preventDefault(); closeModal(); return; }
  if (e.key === "Tab") {
    const nodes = [...root().querySelectorAll("button:not([disabled]):not([hidden]), input, textarea, [href]")].filter((n) => n.offsetParent !== null);
    if (!nodes.length) return;
    const first = nodes[0], last = nodes[nodes.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
}

/** Open an operator action dialog. */
export function openActionModal(cfg) {
  current = { phase: "form", values: {}, errors: {}, result: null, returnFocus: document.activeElement, ...cfg };
  for (const f of current.fields) if (f.value !== undefined) current.values[f.name] = f.value;
  paint();
  document.addEventListener("keydown", onKey, true);
  const first = root().querySelector("input, textarea");
  (first || root().querySelector("[data-modal-submit]"))?.focus();
}

export function isModalOpen() { return !!current; }

export function installModal() {
  const r = root();
  r.addEventListener("click", (e) => {
    if (e.target.closest("[data-modal-close]")) closeModal();
    else if (e.target.closest("[data-modal-submit]")) submit();
    else if (e.target.matches("[data-modal-backdrop]")) closeModal();
  });
  r.addEventListener("submit", (e) => { e.preventDefault(); submit(); });
  r.addEventListener("input", (e) => {
    if (current && e.target.name) { current.values[e.target.name] = e.target.value; }
  });
}
