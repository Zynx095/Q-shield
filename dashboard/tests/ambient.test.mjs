// Ambient background (src/components/ambient.js): deterministic, decorative, and never shaped like a secret.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { ALGORITHMS, decorativeHex, rowTokens, seeded } from "../src/components/ambient.js";

const ROWS = [];
for (let d = 0; d < 3; d++) for (let r = 0; r < 7; r++) ROWS.push(rowTokens(d, r));

test("ambient: the same strings on every load", () => {
  assert.deepEqual(decorativeHex(3), ["3fb1fb8f", "010894e2", "399bae06"], "fixed seed, fixed output");
  assert.deepEqual(rowTokens(1, 4), rowTokens(1, 4));
  const a = seeded(7), b = seeded(7);
  for (let i = 0; i < 50; i++) assert.equal(a(), b());
  assert.notDeepEqual(rowTokens(0, 0), rowTokens(0, 1), "neighbouring rows differ");
});

test("ambient: every token is an algorithm name or a short decorative hex group", () => {
  for (const row of ROWS) {
    for (const t of row) assert.ok(ALGORITHMS.includes(t) || /^[0-9a-f]{8}$/.test(t), t);
    assert.ok(ALGORITHMS.every((n) => row.includes(n)), "each row names every algorithm");
  }
});

test("ambient: nothing in the background is shaped like a key, hash, signature or token", () => {
  const text = ROWS.map((r) => r.join(" ")).join("\n");
  assert.ok(!/[0-9a-f]{9,}/i.test(text), "no hex run longer than 8 digits (a SHA-256 hash is 64)");
  assert.ok(!/[A-Za-z0-9+/=_]{16,}/.test(text), "no base64-like run of 16 or more characters");
  assert.ok(!/qso_|bearer|token|secret|password|private/i.test(text), "no credential vocabulary");
});

test("ambient: the module cannot reach live data", () => {
  const src = readFileSync(new URL("../src/components/ambient.js", import.meta.url), "utf-8");
  assert.ok(!/^\s*import\b/m.test(src), "imports nothing: no store, no API");
  assert.ok(!/fetch\(|XMLHttpRequest|WebSocket|sessionStorage\.getItem\("qshield_operator_token/.test(src));
});
