// Ambient background: a few very faint rows of the algorithm names Q-SHIELD actually uses, interleaved with short
// decorative hex groups, drifting slowly sideways behind the panels (styles/ambient.css). Decorative only:
// aria-hidden, not interactive, not selectable, built once from constants and a fixed-seed generator in this file.
// It deliberately imports nothing from the store or the API, so no live value, token, key or signature can ever
// reach it; the hex groups are 8 digits, far shorter than any real key, hash or signature.

export const ALGORITHMS = ["ML-DSA-65", "ML-KEM-768", "SHA-256", "AES-256-GCM", "HKDF-SHA256", "HMAC-SHA256"];

const DEPTHS = [7, 6, 5];          // rows per depth (far, middle, near); size, speed and opacity live in ambient.css
const TOKENS = 21;                 // tokens per copy of a row: wider than a 1920 px screen at every depth

const SEED = 0x51534844;          // "QSHD": the same decoration on every load and every machine

/** mulberry32: a tiny fixed-seed generator. Deliberately not the browser's random source, so the background is
 *  reproducible and the dashboard contract test can keep banning invented values. */
export function seeded(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** `count` decorative 8-digit hex groups from `seed`. Never derived from any data. */
export function decorativeHex(count, seed = SEED) {
  const next = seeded(seed);
  return Array.from({ length: count }, () => Math.floor(next() * 0x100000000).toString(16).padStart(8, "0"));
}

/** One row's tokens: algorithm names with a hex group every third slot, rotated so neighbouring rows never line up. */
export function rowTokens(depth, row, n = TOKENS) {
  const hex = decorativeHex(n, SEED + depth * 101 + row);
  const out = [];
  let k = row * 2 + depth * 3;
  for (let i = 0; i < n; i++) out.push(i % 3 === 2 ? hex[i] : ALGORITHMS[k++ % ALGORITHMS.length]);
  return out;
}

// Drift speed per overall posture: calm when trusted, a little quicker under suspicion, almost still while a threat
// is contained (the system feels sealed), steady during recovery. The tint is in ambient.css (body[data-posture]).
const RATE = { ok: 1, "ok-soft": 1, warn: 1.6, crit: 0.15, proc: 0.8, neutral: 1 };
let posture = null;

/** Follow the fleet posture tone. Speed changes go through the Web Animations API, so the rows never jump. */
export function setPosture(tone, { force = false } = {}) {
  if (tone === posture && !force) return;
  posture = tone;
  document.body.setAttribute("data-posture", tone);
  const host = document.getElementById("ambient");
  if (!host || !host.getAnimations) return;
  const rate = RATE[tone] ?? 1;
  for (const a of host.getAnimations({ subtree: true })) {
    if (a.animationName !== "amb-drift") continue;         // leave the tint's colour transition at normal speed
    if (a.updatePlaybackRate) a.updatePlaybackRate(rate); else a.playbackRate = rate;
  }
}

/** Build the layers once into `host` (the aria-hidden #ambient element). */
export function mountAmbient(host) {
  if (!host || host.childElementCount) return;
  DEPTHS.forEach((rows, d) => {
    const layer = document.createElement("div");
    layer.className = `amb-layer amb-d${d + 1}`;
    for (let r = 0; r < rows; r++) {
      const el = document.createElement("div");
      el.className = "amb-row";
      const text = rowTokens(d, r).join(" ");
      el.textContent = `${text} ${text}`;            // two copies: the drift loops seamlessly at -50%
      layer.appendChild(el);
    }
    host.appendChild(layer);
  });
  apply(ambientEnabled());
}

// ---------------------------------------------------------------------------------------------- on / off (Settings)
const PREF = "qshield_ambient";             // per tab, like the operator session; "off" when switched off

export function ambientEnabled() {
  try { return sessionStorage.getItem(PREF) !== "off"; } catch { return true; }
}

export function setAmbientEnabled(on) {
  try { if (on) sessionStorage.removeItem(PREF); else sessionStorage.setItem(PREF, "off"); } catch { /* memory only */ }
  apply(on);
}

function apply(on) {
  const host = document.getElementById("ambient");
  if (!host) return;
  host.hidden = !on;                                       // display:none: nothing painted, animations stop
  document.documentElement.classList.toggle("ambient-on", on);
  if (on && posture) setPosture(posture, { force: true }); // restarted animations need their posture rate again
}
