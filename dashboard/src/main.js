// Q-SHIELD command center: routing, rendering and interaction. No build step: native ES modules served by the
// gateway at /dashboard. All data comes from the operator API through store.js.
import { html } from "./lib/html.js";
import { render } from "./lib/morph.js";
import { explain } from "./lib/api.js";
import { stateMeta } from "./lib/copy.js";
import { clock } from "./lib/format.js";
import {
  S, gatewayNow, onStateChange, reverify, setFocus, setSignedOutHandler, signIn, signOut,
  storedToken, subscribe, takeTokenFromUrl,
} from "./store.js";
import { UI, fleet } from "./model.js";
import { openAbort, openExpected, openStart } from "./actions.js";
import { installModal, isModalOpen } from "./components/modal.js";
import { installChartHover } from "./components/chart.js";
import { sidebar, topbar } from "./components/shell.js";
import { icon } from "./components/icons.js";
import { signInView } from "./pages/signin.js";
import * as overview from "./pages/overview.js";
import * as devices from "./pages/devices.js";
import * as device from "./pages/device.js";
import * as incidents from "./pages/incidents.js";
import * as recovery from "./pages/recovery.js";
import * as evidence from "./pages/evidence.js";
import * as twin from "./pages/twin.js";
import * as crypto from "./pages/crypto.js";
import * as settings from "./pages/settings.js";
import * as live from "./pages/live.js";

const PAGES = {
  overview: [overview, "Overview"], devices: [devices, "Devices"], device: [device, "Device"], incidents: [incidents, "Incidents"],
  recovery: [recovery, "Recovery"], evidence: [evidence, "Evidence chain"], twin: [twin, "Digital twin"],
  crypto: [crypto, "Cryptography"], settings: [settings, "Settings"], live: [live, "Presentation mode"],
};

const app = document.getElementById("app");
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

// ---------------------------------------------------------------------------------------------- routing
function parseRoute() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  const [a, b] = parts;
  if (a === "devices" && b) return { name: "device", params: { id: b } };
  if (a === "evidence" && b) return { name: "evidence", params: { seq: b } };
  return { name: PAGES[a] ? a : "overview", params: {} };
}

// ---------------------------------------------------------------------------------------------- rendering
let auth = { phase: "checking", error: null, info: null };
let lastRouteKey = null;
let frame = 0;

export function scheduleRender() {
  if (frame) return;
  frame = requestAnimationFrame(() => { frame = 0; paint(); });
}

function paint() {
  if (!S.token || !S.me) {
    document.title = "Sign in – Q-SHIELD";
    if (auth.phase === "checking") {
      render(app, html`<main class="signin" id="content"><div class="signin-card"><div class="row" style="gap:10px"><span class="spinner" aria-hidden="true"></span><span>Connecting to the gateway…</span></div></div></main>`);
    } else {
      render(app, signInView({ error: auth.error, busy: auth.phase === "busy", info: auth.info }));
    }
    return;
  }
  const route = parseRoute();
  const [page, title] = PAGES[route.name];
  const f = fleet();
  const bare = route.name === "live";
  const counts = { incidents: f.open.length, recovery: f.activeRecoveries.length };
  const body = page.render({ params: route.params, rerender: scheduleRender });
  const shell = bare
    ? html`<div class="shell is-bare"><main id="content" tabindex="-1">${body}</main></div>`
    : html`<div class="shell">
        ${sidebar({ route: route.name, counts, simulated: f.simulated, menuOpen: UI.menuOpen })}
        <div class="main">
          ${topbar({ posture: f.posture, connected: S.connected, lastOkAt: S.lastOkAt, pqc: S.pqcKey, chain: S.evidence,
            deviceCount: S.devices.length, openIncidents: f.open.length, me: S.me, offset: S.clockOffset, gatewayNow: gatewayNow() })}
          ${S.connected === false ? html`<div class="offline-bar" role="alert">${icon("plugOff")}<span><b>Gateway connection lost.</b> Last synchronized ${S.lastOkAt ? `${Math.round((Date.now() - S.lastOkAt) / 1000)} s ago` : "never"}. Retrying every 2 s; the data below may be out of date.</span></div>` : ""}
          <main id="content" class="content" tabindex="-1">${body}</main>
        </div>
      </div>`;
  render(app, html`<a class="skip-link" href="#content" data-action="skip">Skip to content</a>${shell}`);

  const key = `${route.name}/${JSON.stringify(route.params)}`;
  if (key !== lastRouteKey) {
    lastRouteKey = key;
    document.title = `${route.name === "device" ? route.params.id : title} – Q-SHIELD`;
    UI.menuOpen = false;
    window.scrollTo(0, 0);
    const content = document.getElementById("content");
    if (content && document.activeElement && document.activeElement !== document.body && !app.contains(document.activeElement)) content.focus({ preventScroll: true });
    if (route.name === "evidence" && route.params.seq) {
      requestAnimationFrame(() => document.getElementById(`evidence-${route.params.seq}`)?.scrollIntoView({ block: "center" }));
    }
  }
  afterRender();
}

// ---------------------------------------------------------------------------------------------- post-render effects
const shown = new Map();     // tween element key -> last displayed number
function afterRender() {
  // score tween: animate the number when it really changes
  app.querySelectorAll("[data-tween]").forEach((el) => {
    const k = `${location.hash}|${el.dataset.tween}`;
    const to = Number(el.textContent);
    const from = shown.get(k);
    shown.set(k, to);
    if (!Number.isFinite(to) || !Number.isFinite(from) || from === to || reduceMotion.matches) return;
    const t0 = performance.now(), dur = 700;
    const step = (t) => {
      const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      el.textContent = String(Math.round(from + (to - from) * e));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
  // charts: render at their real pixel width so text stays legible
  app.querySelectorAll("[data-chart]").forEach((el) => {
    const w = el.parentElement ? el.parentElement.clientWidth : 0;
    const id = el.dataset.chart;
    if (w > 0 && Math.abs((UI.chartWidth[id] || 0) - w) > 4) { UI.chartWidth[id] = w; scheduleRender(); }
  });
}

// ---------------------------------------------------------------------------------------------- toasts
const toasts = document.getElementById("toasts");
function toast(tone, iconName, title, sub) {
  const el = document.createElement("div");
  el.className = `toast ${tone}`;
  el.innerHTML = String(html`${icon(iconName)}<div><div><b>${title}</b></div>${sub ? html`<div class="t-sub">${sub}</div>` : ""}</div>`);
  toasts.appendChild(el);
  setTimeout(() => el.remove(), 7000);
}

onStateChange((c) => {
  const m = stateMeta(c.to);
  UI.flash = { deviceId: c.deviceId, from: c.from, to: c.to, until: Date.now() + 6000 };
  toast(m.tone === "ok-soft" ? "ok" : m.tone, m.icon, `${c.deviceId}: ${c.from} → ${c.to}`, m.line);
  setTimeout(scheduleRender, 6100);
});

// ---------------------------------------------------------------------------------------------- interaction
document.addEventListener("click", (e) => {
  const a = e.target.closest("[data-action]");
  const row = !a && e.target.closest("tr[data-href]");
  if (row && !e.target.closest("a, button")) { location.hash = row.dataset.href; return; }
  if (!a) return;
  const act = a.dataset.action;
  if (act === "toggle") { const id = a.dataset.id; UI.expanded.has(id) ? UI.expanded.delete(id) : UI.expanded.add(id); scheduleRender(); }
  else if (act.startsWith("more:")) { const k = act.slice(5); UI.limits[k] = (UI.limits[k] || (k === "ov-tl" ? 14 : 20)) + 30; scheduleRender(); }
  else if (act === "chart-mode") { UI.chartMode = a.dataset.mode; scheduleRender(); }
  else if (act === "toggle-math") { UI.showMath = !UI.showMath; scheduleRender(); }
  else if (act === "op-start") openStart(a.dataset.id);
  else if (act === "op-abort") openAbort(a.dataset.id);
  else if (act === "op-expected") openExpected(a.dataset.id);
  else if (act === "reverify") { a.disabled = true; reverify().finally(scheduleRender); }
  else if (act === "ev-filter") { UI.evidenceFilter = a.dataset.filter; UI.evidenceLimit = 40; scheduleRender(); }
  else if (act === "ev-more") { UI.evidenceLimit += 40; scheduleRender(); }
  else if (act === "menu") { UI.menuOpen = !UI.menuOpen; scheduleRender(); }
  else if (act === "signout") signOut();
});

document.addEventListener("change", (e) => {
  const a = e.target.closest("[data-action]");
  if (!a) return;
  if (a.dataset.action === "focus") setFocus(a.value);
  else if (a.dataset.action === "ev-device") { UI.evidenceDevice = a.value; scheduleRender(); }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !isModalOpen()) {
    if (parseRoute().name === "live") location.hash = "#/overview";
    else if (UI.menuOpen) { UI.menuOpen = false; scheduleRender(); }
  }
});

document.addEventListener("submit", async (e) => {
  if (!e.target.matches("[data-signin]")) return;
  e.preventDefault();
  const token = e.target.elements.token.value.trim();
  if (!token) { auth = { phase: "form", error: "Enter your operator token.", info: null }; paint(); document.getElementById("signin-token")?.focus(); return; }
  auth = { phase: "busy", error: null, info: null };
  paint();
  try {
    await signIn(token);
    auth = { phase: "ok", error: null, info: null };
  } catch (err) {
    auth = { phase: "form", error: explain(err), info: null };
  }
  paint();
  if (auth.phase === "form") document.getElementById("signin-token")?.focus();
});

window.addEventListener("hashchange", () => {
  if (location.hash.includes("token=")) { boot(); return; }
  scheduleRender();
});
window.addEventListener("resize", () => scheduleRender());

setInterval(() => {
  const t = clock(gatewayNow());
  document.querySelectorAll("[data-gateway-clock]").forEach((el) => { if (el.textContent !== t) el.textContent = t; });
  if (S.connected === false) scheduleRender();   // keeps "last synchronized N s ago" honest
}, 1000);

// ---------------------------------------------------------------------------------------------- boot
setSignedOutHandler((reason) => {
  auth = { phase: "form", error: reason, info: null };
  lastRouteKey = null;
  paint();
});
subscribe(scheduleRender);
installModal();
installChartHover(document.body);

async function boot() {
  const fromUrl = takeTokenFromUrl();
  const token = fromUrl || storedToken();
  if (!token) { auth = { phase: "form", error: null, info: null }; paint(); return; }
  auth = { phase: "checking", error: null, info: null };
  paint();
  try {
    await signIn(token);
    auth = { phase: "ok", error: null, info: null };
  } catch (err) {
    auth = { phase: "form", error: explain(err), info: fromUrl ? "The token in the link was not accepted." : null };
  }
  paint();
}

boot();
