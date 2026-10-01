// Ambient background: a few very faint rows of the algorithm names Q-SHIELD actually uses, drifting slowly sideways
// behind the panels (styles/ambient.css). Decorative only: aria-hidden, not interactive, not selectable, built once
// from constants in this file. It deliberately imports nothing from the store or the API, so no live value, token,
// key or signature can ever reach it.

export const ALGORITHMS = ["ML-DSA-65", "ML-KEM-768", "SHA-256", "AES-256-GCM", "HKDF-SHA256", "HMAC-SHA256"];

const DEPTHS = [7, 6, 5];          // rows per depth (far, middle, near); size, speed and opacity live in ambient.css
const TOKENS = 18;                 // tokens per copy of a row: wider than a 1920 px screen at every depth

/** One row's tokens, rotated so neighbouring rows never line up. Pure and deterministic. */
export function rowTokens(depth, row, n = TOKENS) {
  const out = [];
  for (let i = 0; i < n; i++) out.push(ALGORITHMS[(i + row * 2 + depth * 3) % ALGORITHMS.length]);
  return out;
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
}
