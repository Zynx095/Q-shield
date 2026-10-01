// Q-SHIELD Command Center. Reads the live gateway operator API; renders nothing it did not receive.
// Every server string is escaped: security events contain attacker-chosen values (claimed device ids etc.).
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmtT = (ts) => (ts ? new Date(ts * 1000).toLocaleTimeString() : "—");
const short = (h) => (h ? `${h.slice(0, 10)}…` : "—");

const S = { token: "", device: "", me: null, timer: null, seenEvents: new Set(), seenEvidence: new Set() };

function loadToken() {
  const m = location.hash.match(/token=([^&]+)/);
  if (m) return decodeURIComponent(m[1]);
  try { return sessionStorage.getItem("qshield_token") || ""; } catch { return ""; }
}
function saveToken(t) { try { sessionStorage.setItem("qshield_token", t); } catch { /* private mode: keep in memory */ } }

async function api(path) {
  const r = await fetch(path, { headers: { Authorization: `Bearer ${S.token}` } });
  if (r.status === 401) throw new Error("unauthorised");
  if (!r.ok) return null;
  return r.json();
}

async function act(method, path, body) {
  const r = await fetch(path, { method, headers: { Authorization: `Bearer ${S.token}`, "Content-Type": "application/json" },
                                body: JSON.stringify(body) });
  let data = null;
  try { data = await r.json(); } catch { /* non-JSON error body */ }
  if (!r.ok) {
    const d = data && data.detail;
    throw new Error(r.status === 401 ? "unauthorised (operator token rejected, revoked or expired)"
      : r.status === 403 ? "forbidden (your role does not allow this action)"
      : `${r.status}: ${typeof d === "string" ? d : JSON.stringify(d ?? data)}`);
  }
  return data;
}

function setConn(ok, text) {
  const c = $("conn");
  c.className = `conn ${ok ? "on" : "off"}`;
  c.textContent = text;
}

// ------------------------------------------------------------------ renderers
function renderOverview(t, dev, access) {
  $("devid").textContent = S.device;
  const state = t && t.state ? t.state : (t && t.status) || "NO DATA";
  const pill = $("state");
  pill.textContent = state;
  pill.className = `pill ${state}`;
  const score = t && typeof t.score === "number" ? t.score : null;
  $("score").textContent = score ?? "--";
  $("marker").style.left = `${score ?? 0}%`;
  $("lastseen").textContent = dev && dev.last_seen ? new Date(dev.last_seen).toLocaleTimeString() : "—";
  const n = access && access.normal, r = access && access.recovery;
  $("access-normal").innerHTML = n ? (n.allowed ? '<span class="ok">allowed</span>' : `<span class="bad">BLOCKED (${esc(n.reason)})</span>`) : "—";
  $("access-recovery").innerHTML = r ? (r.allowed ? '<span class="ok">open</span>' : '<span class="muted">closed</span>') : "—";
  $("coverage").textContent = t && t.coverage !== undefined ? `${Math.round(t.coverage * 100)}% of factor weight has evidence` : "—";
  $("caps").textContent = t && t.caps && t.caps.length ? t.caps.map((c) => `${c.name} (${c.ceiling})`).join(", ") : "none";
}

const FACTOR_LABEL = { identity_crypto: "Identity", physical: "Physical", sensor_consistency: "Sensor",
                       config_integrity: "Config", visual: "Vision", network: "Network" };
function renderFactors(t) {
  const f = (t && t.factors) || {};
  $("factors").innerHTML = Object.keys(FACTOR_LABEL).map((k) => {
    const x = f[k] || {};
    if (!x.available) return `<div class="frow na"><span>${FACTOR_LABEL[k]}</span><div class="fbar"><i style="width:0"></i></div><span class="fval">no data</span></div>`;
    const p = Math.max(0, Math.min(100, x.penalty || 0));
    return `<div class="frow"><span>${FACTOR_LABEL[k]}</span><div class="fbar"><i style="width:${p}%"></i></div>`
         + `<span class="fval">${p.toFixed(0)} · ${(x.effective_weight * 100).toFixed(0)}%</span></div>`;
  }).join("") + (t && t.pressure ? `<div class="frow"><span>Pressure</span><div class="fbar"><i style="width:${t.pressure * 4}%"></i></div><span class="fval">${t.pressure.toFixed(1)}/25</span></div>` : "");
}

function renderTimeline(history) {
  const items = (history || []).slice().reverse().filter((c) => c.previous_state !== c.new_state);
  if (!items.length) { $("timeline").innerHTML = '<span class="muted">No state changes yet.</span>'; return; }
  $("timeline").innerHTML = items.map((c, i) => `${i ? '<div class="edge"></div>' : ""}<div class="node ${esc(c.new_state)}">`
    + `<div class="dot"></div><div class="lbl">${esc(c.new_state)}</div><div class="t">${fmtT(c.timestamp)} · ${esc(c.new_score)}</div></div>`).join("");
}

const REC_STEPS = [["remediation_pending", "Remediation issued"], ["health_checks", "Health checks"],
                   ["trust_ramp", "VERIFIED · trust ramp"], ["restoring", "RECOVERED · access restored"], ["completed", "TRUSTED"]];
function renderRecovery(rec) {
  const r = rec && rec.current;
  if (!r) {
    $("recovery-steps").innerHTML = "";
    $("recovery-detail").textContent = "No recovery started.";
    return;
  }
  const idx = r.status === "completed" ? REC_STEPS.length - 1 : REC_STEPS.findIndex(([k]) => k === r.stage);
  $("recovery-steps").innerHTML = REC_STEPS.map(([, label], i) => {
    let cls = i < idx ? "done" : i === idx ? "cur" : "";
    if (r.status === "completed" && i <= idx) cls = "done";
    if (r.status === "failed" && i === idx) cls = "fail";
    return `<div class="step ${cls}"><i></i>${label}</div>`;
  }).join("");
  const checks = (r.health || []).slice(-5).map((h) => (h.clean ? "✔" : "✖")).join(" ");
  $("recovery-detail").innerHTML = `<div>${esc(r.recovery_id)} · <b>${esc(r.status)}</b></div>`
    + (r.failure_reason ? `<div class="bad">${esc(r.failure_reason)}</div>` : "")
    + `<div>remediation: ${esc(r.command && r.command.action)} ${r.command_acked ? '<span class="ok">acknowledged</span>' : '<span class="muted">pending</span>'}</div>`
    + `<div>health: ${esc(r.consecutive_clean)} consecutive clean ${checks ? `(${checks})` : ""}</div>`;
}

function renderTwin(tw) {
  const rows = tw && tw.comparison ? Object.entries(tw.comparison.fields) : [];
  $("twin").querySelector("tbody").innerHTML = rows.length ? rows.map(([k, v]) =>
    `<tr><td>${esc(k)}</td><td class="mono">${esc(JSON.stringify(v.expected))}</td><td class="mono">${esc(v.observed === null ? "—" : JSON.stringify(v.observed))}</td>`
    + `<td class="st-${esc(v.status)}">${esc(v.status)}</td></tr>`).join("")
    : '<tr><td colspan="4" class="muted">No expected state set.</td></tr>';
}

function renderEvents(events, history) {
  const tc = (history || []).map((c) => ({ t: c.timestamp, key: `tc:${c.event_id}`, event: (c.reasons[0] || {}).signal || c.kind,
    sev: c.new_state === "QUARANTINED" ? "high" : c.delta < 0 ? "medium" : "low",
    score: `${c.previous_score} → ${c.new_score}`, state: c.previous_state === c.new_state ? "" : `${c.previous_state || "—"} → ${c.new_state}` }));
  const se = (events || []).filter((e) => !e.device_id || e.device_id === S.device).map((e) => ({ t: e.received_at, key: `se:${e.id}`,
    event: e.event_type, sev: e.severity, score: "", state: "" }));
  const all = tc.concat(se).sort((a, b) => b.t - a.t).slice(0, 80);
  $("events").querySelector("tbody").innerHTML = all.map((e) => {
    const fresh = !S.seenEvents.has(e.key); S.seenEvents.add(e.key);
    return `<tr class="${fresh && S.seenEvents.size > all.length ? "flash" : ""}"><td class="mono">${fmtT(e.t)}</td><td>${esc(e.event)}</td>`
         + `<td class="sev-${esc(e.sev)}">${esc(e.sev)}</td><td class="mono">${esc(e.score)}</td><td>${esc(e.state)}</td></tr>`;
  }).join("");
}

function renderEvidence(entries, verify) {
  const badge = $("chain-badge");
  if (!verify) { badge.textContent = "not configured"; badge.className = "badge"; return; }
  badge.textContent = verify.ok ? `VERIFIED · ${verify.count} entries${verify.signed ? " · ML-DSA-65" : " · UNSIGNED"}` : `BROKEN at #${verify.first_bad_seq}: ${verify.reason}`;
  badge.className = `badge ${verify.ok ? "ok" : "bad"}`;
  $("chain-head").textContent = `head #${verify.head.seq} ${verify.head.event_hash}`;
  const bad = new Map((verify.problems || []).map((p) => [p.seq, p.reason]));
  $("evidence").querySelector("tbody").innerHTML = (entries || []).slice(-40).reverse().map((e) =>
    `<tr><td class="mono">${esc(e.seq)}</td><td>${esc(e.event_type)}</td><td class="mono">${esc(short(e.event_hash))}</td>`
    + `<td class="mono">${esc(short(e.prev_hash))}</td><td class="mono">${esc(e.signature ? short(e.signature) : "unsigned")}</td>`
    + `<td class="${bad.has(e.seq) ? "bad" : "ok"}">${bad.has(e.seq) ? esc(bad.get(e.seq)) : "✔"}</td></tr>`).join("");
}

// ------------------------------------------------------------------ operator actions (server is authoritative)
const A = { busy: false, expected: {}, dirty: false };
function msg(kind, text) { const m = $("act-msg"); m.className = `act-msg ${kind}`; m.textContent = text; }

function renderActions(t, rec, tw) {
  const st = (t && t.state) || "NO DATA";
  const cur = rec && rec.current;
  const active = !!(cur && cur.status === "active");
  const canAct = !!(S.me && (S.me.role === "operator" || S.me.role === "admin"));
  $("act-state").textContent = st;
  $("act-rec").textContent = cur ? `${cur.status}${cur.status === "active" ? ` · ${cur.stage}` : ""}${cur.failure_reason ? ` (${cur.failure_reason})` : ""}` : "none";
  // Hints only: the gateway re-checks every precondition and refuses with 409 if they do not hold.
  $("btn-start").disabled = !canAct || A.busy || st !== "QUARANTINED" || active;
  $("btn-abort").disabled = !canAct || A.busy || !active;
  $("btn-twin").disabled = !canAct || A.busy || active;
  A.expected = (tw && tw.expected) || {};
  if (!A.dirty) { $("exp-fw").value = A.expected.fw_version || ""; $("exp-cfg").value = A.expected.cfg_hash || ""; }
}

async function runAction(label, fn) {
  if (A.busy) return;
  A.busy = true; msg("muted", `${label}…`);
  ["btn-start", "btn-abort", "btn-twin"].forEach((id) => { $(id).disabled = true; });
  try { msg("ok", `${label}: ${await fn()}`); A.dirty = false; }
  catch (e) { msg("bad", `${label} refused · ${e.message}`); }
  finally { A.busy = false; await refresh(); }
}

const reason = () => $("act-reason").value.trim();
$("btn-start").addEventListener("click", () => runAction("Start recovery", async () => {
  const r = await act("POST", `/api/v1/devices/${encodeURIComponent(S.device)}/recovery/start`, { reason: reason() });
  return `${r.recovery_id} · ${r.stage}`;
}));
$("btn-abort").addEventListener("click", () => runAction("Abort recovery", async () => {
  const r = await act("POST", `/api/v1/devices/${encodeURIComponent(S.device)}/recovery/abort`, { reason: reason() });
  return `${r.recovery_id} · ${r.failure_reason}`;
}));
$("btn-twin").addEventListener("click", () => runAction("Save expected state", async () => {
  // Keep the other expected fields (capabilities, sensor ranges); only firmware/config are edited here.
  const body = { ...A.expected, fw_version: $("exp-fw").value.trim() || null, cfg_hash: $("exp-cfg").value.trim() || null };
  const r = await act("PUT", `/api/v1/devices/${encodeURIComponent(S.device)}/twin/expected`, body);
  return `fw ${r.expected.fw_version ?? "—"} · cfg ${r.expected.cfg_hash ?? "—"}`;
}));
["exp-fw", "exp-cfg"].forEach((id) => $(id).addEventListener("input", () => { A.dirty = true; }));

// ------------------------------------------------------------------ loop
async function refresh() {
  try {
    const devices = await api("/api/v1/devices");
    const sel = $("device");
    if (devices && sel.options.length !== devices.length) {
      sel.innerHTML = devices.map((d) => `<option>${esc(d.device_id)}</option>`).join("");
      if (!S.device && devices.length) S.device = devices[0].device_id;
      sel.value = S.device;
    }
    if (!S.me) {
      S.me = await api("/api/v1/operators/me");
      $("operator").textContent = S.me ? `${S.me.operator_id} (${S.me.role})${S.me.bootstrap ? " · shared bootstrap token" : ""}` : "—";
    }
    if (!S.device) { setConn(true, "connected · no devices"); return; }
    const d = encodeURIComponent(S.device);
    const [t, hist, events, access, rec, twin, evid, verify] = await Promise.all([
      api(`/api/v1/trust/${d}`), api(`/api/v1/trust/${d}/history?limit=200`), api("/api/v1/events?limit=200"),
      api(`/api/v1/devices/${d}/access`), api(`/api/v1/devices/${d}/recovery`), api(`/api/v1/devices/${d}/twin`),
      api(`/api/v1/evidence/device/${d}?limit=1000`), api("/api/v1/evidence/verify")]);
    const dev = (devices || []).find((x) => x.device_id === S.device);
    renderOverview(t, dev, access); renderFactors(t); renderTimeline(hist); renderRecovery(rec);
    renderTwin(twin); renderActions(t, rec, twin); renderEvents(events, hist); renderEvidence(evid, verify);
    setConn(true, `live · ${new Date().toLocaleTimeString()}`);
  } catch (e) {
    setConn(false, e.message === "unauthorised" ? "bad token" : "offline");
  }
}

function start() {
  S.token = $("token").value.trim() || S.token;
  if (!S.token) { setConn(false, "enter operator token"); return; }
  saveToken(S.token);
  S.me = null;
  clearInterval(S.timer);
  refresh();
  S.timer = setInterval(refresh, 1500);
}

$("connect").addEventListener("click", start);
$("device").addEventListener("change", (e) => { S.device = e.target.value; A.dirty = false; S.seenEvents.clear(); refresh(); });
S.token = loadToken();
if (S.token) { $("token").value = S.token; start(); }
