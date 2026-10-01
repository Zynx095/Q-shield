// Application shell: sidebar navigation and the persistent security status strip. All values are live.
import { html } from "../lib/html.js";
import { clock, duration } from "../lib/format.js";
import { brandMark, icon } from "./icons.js";

const NAV = [
  { group: "Monitor", items: [
    { route: "overview", label: "Overview", icon: "overview" },
    { route: "devices", label: "Devices", icon: "devices" },
    { route: "incidents", label: "Incidents", icon: "incident", count: "incidents" },
    { route: "recovery", label: "Recovery", icon: "refresh", count: "recovery" },
  ] },
  { group: "Forensics", items: [
    { route: "evidence", label: "Evidence chain", icon: "ledger" },
    { route: "twin", label: "Digital twin", icon: "twin" },
    { route: "crypto", label: "Cryptography", icon: "key" },
  ] },
  { group: "Operate", items: [
    { route: "live", label: "Presentation mode", icon: "present" },
    { route: "settings", label: "Settings", icon: "settings" },
  ] },
];

export function sidebar({ route, counts, simulated, menuOpen }) {
  return html`<nav class="sidebar ${menuOpen ? "is-open" : ""}" aria-label="Main">
    <a class="brand" href="#/overview" aria-label="Q-SHIELD overview">${brandMark}<span class="brand-text"><span class="brand-name">Q-SHIELD</span><br><span class="brand-sub">Security command center</span></span></a>
    <div class="nav">${NAV.map((g) => html`<div class="nav-group"><div class="nav-label">${g.group}</div>${g.items.map((it) => {
      const n = it.count ? counts[it.count] : 0;
      const active = route === it.route || (it.route === "devices" && route === "device");
      return html`<a href="#/${it.route}" ${active ? html`aria-current="page"` : ""} title="${it.label}">${icon(it.icon)}<span>${it.label}</span>${n ? html`<span class="nav-count ${it.count === "incidents" ? "crit" : "proc"}" aria-label="${n} ${it.count === "incidents" ? "open" : "active"}">${n}</span>` : ""}</a>`;
    })}</div>`)}</div>
    ${simulated.length ? html`<div class="sidebar-foot"><p class="caption"><span class="tag sim">Simulated</span> ${simulated.join(", ")} ${simulated.length > 1 ? "are software agents" : "is a software agent"}, not physical hardware. The device path is HMAC-SHA256, not post-quantum.</p></div>` : ""}
  </nav>`;
}

export function topbar({ posture, connected, lastOkAt, pqc, chain, deviceCount, openIncidents, me, offset, gatewayNow }) {
  const since = lastOkAt ? Math.round((Date.now() - lastOkAt) / 1000) : null;
  const gw = connected === false
    ? html`<span class="chip crit chip-key" title="Last synchronized ${since === null ? "never" : `${since} s ago`}"><span class="dot"></span>Last sync ${since !== null ? `${duration(since)} ago` : "never"}</span>`
    : connected ? html`<span class="chip ok"><span class="dot"></span>Gateway online</span>` : html`<span class="chip"><span class="dot"></span>Connecting</span>`;
  const pqcChip = pqc === undefined ? "" : pqc ? html`<span class="chip ok" title="Gateway ML-KEM key ${pqc.key_id}"><span class="dot"></span>PQC online</span>` : html`<span class="chip warn"><span class="dot"></span>PQC disabled</span>`;
  const v = chain && chain.verify;
  const chainChip = !v ? "" : v.ok
    ? html`<span class="chip ok" title="${v.count} entries, SHA-256 linked${v.signed ? ", ML-DSA signed" : ", unsigned"}"><span class="dot"></span>Chain verified</span>`
    : html`<span class="chip crit"><span class="dot"></span>Evidence chain broken at #${v.first_bad_seq}</span>`;
  const lapse = Math.abs(offset) > 120;
  return html`<header class="topbar">
    <button class="btn icon ghost menu-btn" type="button" data-action="menu" aria-label="Open navigation">${icon("menu")}</button>
    <div class="status-strip" role="status" aria-live="polite" aria-label="System status">
      <a class="chip ${posture.tone === "ok-soft" ? "ok" : posture.tone} chip-key" href="#/overview" style="text-decoration:none"><span class="dot"></span><b>${posture.title}</b></a>
      <a class="chip ${openIncidents ? "crit" : ""}" href="#/incidents" style="text-decoration:none">${icon("incident")}${openIncidents ? `${openIncidents} active incident${openIncidents === 1 ? "" : "s"}` : "No incidents"}</a>
      ${gw}${chainChip}${pqcChip}
    </div>
    <div class="topbar-right">
      ${lapse ? html`<span class="chip warn" title="The gateway clock runs ${duration(Math.abs(offset))} ${offset > 0 ? "ahead of" : "behind"} this browser. The demo announces this as TIME-LAPSE.">Time-lapse ${offset > 0 ? "+" : "−"}${duration(Math.abs(offset))}</span>` : ""}
      <span class="chip chip-time" title="Gateway time">${icon("clock")}<span data-gateway-clock>${clock(gatewayNow)}</span></span>
      ${me ? html`<a class="chip" href="#/settings" style="text-decoration:none" title="Signed in as ${me.display_name}">${icon("user")}${me.operator_id}<span class="caption">${me.role}</span></a>` : ""}
    </div>
  </header>`;
}
