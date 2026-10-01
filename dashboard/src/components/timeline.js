// Live security timeline. Each entry is a real trust change or gateway event; expanding it shows its source,
// authentication, cause, trust delta, the evidence-chain entry that seals it, and the raw identifiers.
import { html } from "../lib/html.js";
import { capLabel, eventLabel, factorLabel, stateMeta } from "../lib/copy.js";
import { clock, dateTime, dayKey, dayLabel, duration, fixed, short } from "../lib/format.js";
import { authTag, deltaText, rejectedTag, stateBadge } from "./status.js";
import { icon } from "./icons.js";

function causeList(it) {
  const rows = it.signals.filter((s) => s.signal && s.signal !== "state_transition_request");
  if (!rows.length) return "";
  return html`<ul class="stack-sm" style="gap:6px">${rows.map((s) => html`<li>
    <span class="strong">${s.label}</span>
    ${Number.isFinite(s.impact) && Math.abs(s.impact) >= 0.05 ? html` <span class="delta ${s.impact < 0 ? "neg" : "pos"}">${s.impact > 0 ? "+" : "−"}${fixed(Math.abs(s.impact), 1)}</span>` : ""}
    ${s.factor ? html` <span class="caption">${s.factor === "pressure" ? "attack pressure" : factorLabel(s.factor)}</span>` : ""}
    ${s.authenticity ? html` ${authTag(s.authenticity)}` : ""}
    ${Number.isFinite(s.confidence) ? html` <span class="caption">confidence ${fixed(s.confidence, 2)}</span>` : ""}
    ${s.provenance ? html`<div class="caption">Provenance: ${s.provenance}</div>` : ""}
  </li>`)}</ul>`;
}

function detail(it, deviceId) {
  const reason = it.signals.find((s) => s.reason);
  const ev = it.evidence;
  return html`<dl class="kv">
    <dt>Gateway time</dt><dd>${dateTime(it.ts)}${it.group ? html` <span class="caption">(${it.group.count} updates over ${duration(it.group.last - it.group.first)})</span>` : ""}</dd>
    <dt>Device</dt><dd>${(it.events[0] && it.events[0].device_id) || deviceId || "Not attributed to a device"}</dd>
    ${Number.isFinite(it.scoreTo) ? html`<dt>Trust</dt><dd class="num">${it.scoreFrom ?? "—"} → ${it.scoreTo} ${deltaText(it.delta)}${it.stateFrom !== it.stateTo && it.stateTo ? html`, ${it.stateFrom || "new"} → ${it.stateTo}` : ""}</dd>` : ""}
    ${causeList(it) ? html`<dt>Cause</dt><dd>${causeList(it)}</dd>` : ""}
    ${reason ? html`<dt>Reason</dt><dd>${reason.reason}</dd>` : ""}
    ${it.operator ? html`<dt>Operator</dt><dd>${it.operator}</dd>` : ""}
    ${it.caps && it.caps.length ? html`<dt>Ceilings</dt><dd>${it.caps.map(capLabel).join(", ")}</dd>` : ""}
    ${it.incident ? html`<dt>Incident</dt><dd><a href="#/incidents">${it.incident.id}</a> opened (${it.incident.modalities.join(" + ")})</dd>` : ""}
    ${ev ? html`<dt>Evidence</dt><dd><a href="#/evidence/${ev.seq}">Entry #${ev.seq}</a> sealed <span class="mono">${short(ev.event_hash, 12)}</span>${ev.signature ? html`, ML-DSA signed` : html`, unsigned`}</dd>` : ""}
    ${[...it.events, ...it.related].length ? html`<dt>Gateway records</dt><dd>${[...it.events, ...it.related].length > 6 ? html`<div class="caption">${[...it.events, ...it.related].length} records; the latest 6:</div>` : ""}${[...it.events, ...it.related].slice(-6).map((e) => html`<div><span class="mono">${e.event_type}</span> <span class="caption">#${e.id}, ${e.severity}</span>${e.details && e.details.claimed_device_id && e.details.claimed_device_id !== deviceId ? html` <span class="caption">claimed device ${e.details.claimed_device_id}</span>` : ""}</div>`)}</dd>` : ""}
    ${it.triggers && it.triggers.length ? html`<dt>Identifiers</dt><dd class="mono" style="font-size:11.5px">${it.group ? `${it.group.keys[0]} … ${it.group.keys[it.group.keys.length - 1]}` : it.key}; ${it.triggers.join(", ")}</dd>` : ""}
  </dl>`;
}

export function timeline(items, { expanded = new Set(), limit = 30, deviceId = null, moreAction = "tl-more", scope = "tl" } = {}) {
  if (!items.length) return "";
  const shown = items.slice(0, limit);
  let lastDay = null;
  const multiDay = shown.length && dayKey(shown[0].ts) !== dayKey(shown[shown.length - 1].ts);
  const rows = [];
  for (const it of shown) {
    if (multiDay && dayKey(it.ts) !== lastDay) {
      lastDay = dayKey(it.ts);
      rows.push(html`<li class="tl-day" data-key="${scope}-day-${lastDay}">${dayLabel(it.ts)}</li>`);
    }
    const id = `${scope}-${it.key}`;
    const open = expanded.has(id);
    const sub = [it.sub, it.operator && !it.sub?.includes(it.operator) ? `by ${it.operator}` : null].filter(Boolean).join(", ");
    const auth = (it.signals.find((s) => s.authenticity) || {}).authenticity;
    rows.push(html`<li class="tl-item ${it.isState ? "is-state" : ""}" data-tone="${it.tone}" data-key="${id}">
      <div class="tl-time">${clock(it.ts)}</div>
      <div class="tl-body">
        <span class="tl-dot" aria-hidden="true"></span>
        <button class="tl-head" type="button" aria-expanded="${open}" aria-controls="${id}-d" data-action="toggle" data-id="${id}">
          <span class="tl-title">${it.title}${it.isState && it.stateTo ? html` ${stateBadge(it.stateTo)}` : ""}${it.group && it.group.count > 1 ? html` <span class="caption">${it.type === "event" ? `×${it.group.count}` : `${it.group.count} updates`}</span>` : ""}</span>
          ${Number.isFinite(it.scoreTo) ? html`<span class="tl-score"><span class="strong">${it.scoreTo}</span>${deltaText(it.delta)}</span>` : html`<span></span>`}
          <span class="tl-sub">${sub}${it.rejected ? html` ${rejectedTag()}` : auth ? html` ${authTag(auth)}` : ""}</span>
        </button>
        <div class="tl-detail" id="${id}-d" ${open ? "" : "hidden"}>${open ? detail(it, deviceId) : ""}</div>
      </div>
    </li>`);
  }
  return html`<ol class="timeline" aria-label="Security timeline, newest first">${rows}</ol>
    ${items.length > limit ? html`<div class="tl-more"><button class="btn sm" type="button" data-action="${moreAction}">${icon("chevronDown")}Show ${Math.min(30, items.length - limit)} older ${items.length - limit === 1 ? "event" : "events"}</button></div>` : ""}`;
}

/** One-line headline of the latest event (presentation mode, overview). */
export function headline(it) {
  if (!it) return "";
  const m = it.stateTo ? stateMeta(it.stateTo) : null;
  return { title: it.title, sub: it.sub, tone: it.tone, time: clock(it.ts), icon: m ? m.icon : "dot", label: eventLabel };
}
