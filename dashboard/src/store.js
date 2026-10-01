// Live state, fetched from the gateway operator API. The UI renders only what is in here, and everything in here
// came from the API: there is no seeded or demo data anywhere in the dashboard.

import { ApiError, ROUTES as R, createApi } from "./lib/api.js";
import { attentionOrder, evidenceIndex } from "./lib/derive.js";

const TOKEN_KEY = "qshield_operator_token";
const POLL_MS = 2000;
const DETAIL_ALL_MAX = 6;          // fetch per-device detail for every device up to this fleet size
const EVIDENCE_PAGE = 200;

export const S = {
  token: "",
  me: null,
  system: null,
  clockOffset: 0,                  // gateway clock - browser clock (seconds)
  connected: null,                 // null = not yet known
  lastOkAt: 0,                     // browser ms of the last successful sync
  devices: [],
  trust: new Map(),                // device_id -> trust snapshot
  events: [],
  observations: [],
  detail: new Map(),               // device_id -> { history, access, recovery, twin, errors }
  evidence: { entries: [], lastSeq: 0, verify: null, verifyAt: 0, verifyError: null, index: new Map(), loaded: false },
  pqcKey: undefined,               // undefined = unknown, null = PQC not configured
  focus: null,                     // device chosen by the operator; otherwise the one needing most attention
  loaded: false,
  stateChanges: [],                // recent { deviceId, from, to, at } for announcements
};

const api = createApi(() => S.token);
const listeners = new Set();
const changeListeners = new Set();
let timer = null;
let inflight = null;
let tick = 0;

export const subscribe = (fn) => (listeners.add(fn), () => listeners.delete(fn));
export const onStateChange = (fn) => (changeListeners.add(fn), () => changeListeners.delete(fn));
const notify = () => listeners.forEach((fn) => fn());

export const gatewayNow = () => Date.now() / 1000 + S.clockOffset;

export function focusId() {
  if (S.focus && S.devices.some((d) => d.device_id === S.focus)) return S.focus;
  const ordered = attentionOrder([...S.trust.values()]);
  return (ordered[0] && ordered[0].device_id) || (S.devices[0] && S.devices[0].device_id) || null;
}
export function setFocus(id) { S.focus = id; notify(); refreshNow(); }

// ---------------------------------------------------------------------------------------------- token
export function takeTokenFromUrl() {
  const m = location.hash.match(/(?:^#|[#&])token=([^&]+)/);
  if (!m) return null;
  // Never leave the token in the address bar (projector, screenshots, history).
  history.replaceState(null, "", `${location.pathname}${location.search}#/overview`);
  return decodeURIComponent(m[1]);
}
export function storedToken() {
  try { return sessionStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; }
}
function saveToken(t) {
  try { if (t) sessionStorage.setItem(TOKEN_KEY, t); else sessionStorage.removeItem(TOKEN_KEY); } catch { /* storage blocked: memory only */ }
}

/** Validate a token against the gateway before using it. Resolves to the operator identity. */
export async function signIn(token) {
  S.token = token.trim();
  try {
    const me = await api.get(R.me());
    S.me = me;
    saveToken(S.token);
    start();
    return me;
  } catch (e) {
    S.token = "";
    throw e;
  }
}

let onSignedOut = () => {};
export const setSignedOutHandler = (fn) => { onSignedOut = fn; };

export function signOut(reason = null) {
  stop();
  S.token = ""; S.me = null; saveToken("");
  S.loaded = false; S.devices = []; S.trust = new Map(); S.events = []; S.detail = new Map(); S.observations = [];
  S.evidence = { entries: [], lastSeq: 0, verify: null, verifyAt: 0, verifyError: null, index: new Map(), loaded: false };
  onSignedOut(reason);
}

// ---------------------------------------------------------------------------------------------- polling
export function start() {
  stop();
  poll();
  timer = setInterval(poll, POLL_MS);
}
export function stop() { clearInterval(timer); timer = null; }

export async function refreshNow() {
  if (inflight) await inflight.catch(() => {});
  return poll();
}

function poll() {
  if (inflight) return inflight;
  inflight = doPoll().finally(() => { inflight = null; });
  return inflight;
}

function isAuth(r) { return r.status === "rejected" && r.reason instanceof ApiError && r.reason.status === 401; }
function isNetwork(r) { return r.status === "rejected" && (!(r.reason instanceof ApiError) || r.reason.status === 0); }

async function doPoll() {
  if (!S.token) return;
  tick += 1;
  const t0 = Date.now();
  const wantSystem = !S.system || tick % 5 === 1;
  const core = await Promise.allSettled([
    api.get(R.devices()), api.get(R.trustAll()), api.get(R.events(300)),
    wantSystem ? api.get(R.system()) : Promise.resolve(S.system),
  ]);
  const t1 = Date.now();
  if (core.some(isAuth)) { signOut("Your operator token was rejected. It may have been revoked or may have expired."); return; }
  if (core.slice(0, 3).every(isNetwork)) {
    S.connected = false;
    notify();
    return;
  }
  S.connected = true;
  S.lastOkAt = t1;
  const [devices, trust, events, system] = core.map((r) => (r.status === "fulfilled" ? r.value : undefined));
  if (Array.isArray(devices)) S.devices = devices;
  if (Array.isArray(trust)) {
    const next = new Map(trust.map((t) => [t.device_id, t]));
    for (const [id, t] of next) {
      const prev = S.trust.get(id);
      if (S.loaded && prev && prev.state && t.state && prev.state !== t.state) {
        const change = { deviceId: id, from: prev.state, to: t.state, at: Date.now() };
        S.stateChanges = [...S.stateChanges.slice(-9), change];
        changeListeners.forEach((fn) => fn(change));
      }
    }
    S.trust = next;
  }
  if (Array.isArray(events)) S.events = events;
  if (system && wantSystem) {
    S.system = system;
    S.clockOffset = system.server_time - (t0 + t1) / 2000;
  }

  const ids = S.devices.length <= DETAIL_ALL_MAX ? S.devices.map((d) => d.device_id) : [focusId()].filter(Boolean);
  const jobs = ids.map((id) => fetchDetail(id));
  jobs.push(fetchEvidence());
  if (!S.observations.length || tick % 3 === 0) jobs.push(api.get(R.observations(200)).then((o) => { S.observations = o; }, () => {}));
  if (S.pqcKey === undefined || tick % 30 === 0) {
    jobs.push(api.get(R.pqcKey()).then((k) => { S.pqcKey = k; }, (e) => { if (e instanceof ApiError && e.status === 503) S.pqcKey = null; }));
  }
  await Promise.allSettled(jobs);
  S.loaded = true;
  notify();
}

async function fetchDetail(id) {
  const [history, access, recovery, twin] = await Promise.allSettled([
    api.get(R.trustHistory(id, 300)), api.get(R.access(id)), api.get(R.recovery(id)), api.get(R.twin(id)),
  ]);
  const prev = S.detail.get(id) || {};
  const val = (r, k) => (r.status === "fulfilled" ? r.value : prev[k]);
  S.detail.set(id, {
    history: val(history, "history") || [], access: val(access, "access") || null,
    recovery: val(recovery, "recovery") || null, twin: val(twin, "twin") || null,
    unavailable: [recovery, twin, access].some((r) => r.status === "rejected" && r.reason instanceof ApiError && r.reason.status === 503),
  });
}

async function fetchEvidence() {
  const ev = S.evidence;
  let added = 0;
  try {
    for (let page = 0; page < 5; page++) {
      const batch = await api.get(R.evidence(ev.lastSeq, EVIDENCE_PAGE));
      if (!Array.isArray(batch) || !batch.length) break;
      ev.entries = ev.entries.concat(batch);
      ev.lastSeq = batch[batch.length - 1].seq;
      added += batch.length;
      if (batch.length < EVIDENCE_PAGE) break;
    }
    ev.loaded = true;
  } catch (e) {
    if (e instanceof ApiError && e.status === 503) { ev.loaded = true; ev.unavailable = true; return; }
  }
  if (added) ev.index = evidenceIndex(ev.entries);
  if (added || !ev.verify || Date.now() - ev.verifyAt > 15000) await verifyEvidence();
}

export async function verifyEvidence() {
  const ev = S.evidence;
  try {
    ev.verify = await api.get(R.evidenceVerify());
    ev.verifyError = null;
  } catch (e) {
    ev.verifyError = e;
  }
  ev.verifyAt = Date.now();
}

// ---------------------------------------------------------------------------------------------- operator actions
// Each returns the gateway's own response (or throws its refusal). Nothing is assumed to have succeeded.
export async function startRecovery(id, reason) {
  const r = await api.post(R.recoveryStart(id), { reason });
  await refreshNow();
  return r;
}
export async function abortRecovery(id, reason) {
  const r = await api.post(R.recoveryAbort(id), { reason });
  await refreshNow();
  return r;
}
export async function setExpected(id, expected) {
  const r = await api.put(R.twinExpected(id), expected);
  await refreshNow();
  return r;
}
export async function listOperators() { return api.get(R.operators()); }
export async function reverify() { await verifyEvidence(); notify(); }
