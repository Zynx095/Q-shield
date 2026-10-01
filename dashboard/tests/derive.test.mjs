// Frontend unit tests (node --test dashboard/tests). Fixtures are real gateway responses from a demo run.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { html, raw, esc } from "../src/lib/html.js";
import {
  buildIncidents, buildTimeline, chainView, evidenceIndex, factorView, posture, recoverySteps, scoreBreakdown,
  scoreSeries, statePath, observationView, visionStatus,
} from "../src/lib/derive.js";
import { storyProgress } from "../src/components/rail.js";
import { countdown, duration, signed } from "../src/lib/format.js";
import { ROUTES } from "../src/lib/api.js";

const FX = JSON.parse(readFileSync(new URL("./fixtures/demo-run.json", import.meta.url), "utf-8"));
const DEV = "DEVICE-001";

test("html escapes every interpolated value and keeps trusted fragments", () => {
  const evil = `<img src=x onerror=alert(1)>"'`;
  const out = String(html`<p title="${evil}">${evil}${raw("<b>ok</b>")}${[html`<i>${"<x>"}</i>`]}</p>`);
  assert.ok(!out.includes("<img"));
  assert.ok(out.includes("&lt;img src=x onerror=alert(1)&gt;&quot;&#39;"));
  assert.ok(out.includes("<b>ok</b>") && out.includes("<i>&lt;x&gt;</i>"));
  assert.equal(esc(null), "");
});

test("posture answers 'is my system secure' from real states", () => {
  assert.equal(posture({ connected: true, trustList: [{ device_id: DEV, state: "QUARANTINED" }] }).title, "Threat contained");
  assert.equal(posture({ connected: true, trustList: [{ device_id: DEV, state: "RECOVERING" }] }).tone, "proc");
  assert.equal(posture({ connected: true, trustList: [{ device_id: DEV, state: "SUSPICIOUS" }] }).tone, "warn");
  assert.equal(posture({ connected: true, trustList: [{ device_id: DEV, state: "TRUSTED" }] }).title, "All devices trusted");
  assert.equal(posture({ connected: false, trustList: [{ device_id: DEV, state: "TRUSTED" }] }).title, "Gateway connection lost");
  assert.equal(posture({ connected: true, trustList: [] }).tone, "neutral");
});

test("timeline joins gateway events to the trust changes they caused", () => {
  const items = buildTimeline({ history: FX.history, events: FX.events, deviceId: DEV, evidenceByTrustEvent: evidenceIndex(FX.evidence) });
  const titles = items.map((i) => i.title);
  // forged + replayed observations are rejected AND explained by the security event that caused the score change
  const forged = items.find((i) => i.title === "Forged observation rejected");
  assert.ok(forged && forged.delta === -10 && forged.events[0].event_type === "pqc_invalid_signature");
  assert.ok(titles.includes("Replayed observation rejected"));
  // the attack story, in order (newest first)
  const states = items.filter((i) => i.isState).map((i) => i.stateTo).reverse();
  assert.deepEqual(states, ["TRUSTED", "SUSPICIOUS", "QUARANTINED", "RECOVERING", "VERIFIED", "RECOVERED", "TRUSTED"]);
  const q = items.find((i) => i.stateTo === "QUARANTINED");
  assert.equal(q.title, "Device entered quarantine");
  assert.equal(q.sub, "Restricted visual condition detected");
  assert.ok(q.incident && q.incident.id === "INC-DEVICE-001-1");
  assert.ok(q.evidence && q.evidence.event_type === "trust_state_transition");
  // recovery bookkeeping events attach to their transition instead of repeating it
  const rec = items.find((i) => i.stateTo === "RECOVERING");
  assert.equal(rec.operator, "bootstrap-admin");
  assert.ok(rec.related.some((e) => e.event_type === "recovery_started"));
  assert.ok(!items.some((i) => i.type === "event" && i.events[0].event_type === "recovery_started"));
  // operator's SET_EXPECTED_STATE is not shown twice next to "Known-good state updated"
  assert.equal(items.filter((i) => /known-good/i.test(i.title)).length, 1);
  // enforcement is visible as its own entry
  assert.ok(titles.includes("Normal channel blocked by quarantine"));
  // small clean-evidence steps are folded
  assert.ok(items.some((i) => i.group && i.group.count >= 2));
  // newest first
  for (let k = 1; k < items.length; k++) assert.ok(items[k - 1].ts >= items[k].ts);
});

test("incident is reconstructed with evidence, enforcement and resolution", () => {
  const recs = FX.recovery.history;
  const [inc, ...rest] = buildIncidents({ deviceId: DEV, history: FX.history, snapshot: FX.snapshot, recoveries: recs,
    events: FX.events, observations: FX.observations });
  assert.equal(rest.length, 0);
  assert.equal(inc.id, "INC-DEVICE-001-1");
  assert.equal(inc.title, "Physical + visual correlation");
  assert.deepEqual([inc.scoreBefore, inc.scoreAfter, inc.stateAfter], [55, 30, "QUARANTINED"]);
  assert.ok(inc.enforced && inc.blocked >= 1);
  assert.equal(inc.status, "resolved");
  const vis = inc.members.find((m) => m.modality === "VISUAL");
  assert.ok(vis.observation && vis.observation.auth.startsWith("ML-DSA-65"));
  assert.match(vis.provenance, /synthetic/);      // simulated detections are labelled, never passed off as camera output
  const phys = inc.members.find((m) => m.modality === "PHYSICAL");
  assert.match(phys.provenance, /simulated/);
});

test("recovery steps never run ahead of the orchestrator record", () => {
  const cfg = { health_checks_required: 3, quarantine_below: 50, trusted_reentry_min: 85 };
  const status = (opts) => recoverySteps({ cfg, ...opts }).map((s) => s.status);
  assert.deepEqual(status({ rec: FX.recovery.current, state: "TRUSTED", score: 85 }), Array(8).fill("done"));
  assert.deepEqual(status({ rec: null, state: "QUARANTINED", score: 30 }), ["done", "active", ...Array(6).fill("pending")]);
  assert.deepEqual(status({ rec: null, state: "TRUSTED", score: 100 }), Array(8).fill("pending"));
  const base = { ...FX.recovery.current, status: "active", command_acked: false, consecutive_clean: 0 };
  assert.deepEqual(status({ rec: { ...base, stage: "remediation_pending" }, state: "RECOVERING", score: 30 }).slice(0, 4), ["done", "done", "active", "pending"]);
  const hc = recoverySteps({ cfg, rec: { ...base, stage: "health_checks", command_acked: true, consecutive_clean: 2 }, state: "RECOVERING", score: 30 });
  assert.equal(hc[3].status, "active");
  assert.deepEqual(hc[3].pips, { on: 2, of: 3 });
  const ramp = recoverySteps({ cfg, rec: { ...base, stage: "trust_ramp" }, state: "VERIFIED", score: 42 });
  assert.equal(ramp[4].status, "done");
  assert.deepEqual([ramp[5].status, ramp[5].progress.value, ramp[5].progress.target], ["active", 42, 50]);
  const failed = status({ rec: { ...base, status: "failed", stage: "health_checks" }, state: "QUARANTINED", score: 30 });
  assert.equal(failed[3], "failed");
  // a finished recovery followed by a new quarantine starts a new cycle
  assert.equal(status({ rec: FX.recovery.current, state: "QUARANTINED", score: 30 })[1], "active");
});

test("factor view shows the points each factor removes, from the real snapshot", () => {
  const f = factorView(FX.snapshot, FX.history);
  assert.equal(f.length, 6);
  const phys = f.find((x) => x.key === "physical");
  assert.ok(Math.abs(phys.loss - 0.2 * FX.snapshot.factors.physical.penalty) < 1e-9);
  assert.equal(phys.level, "hit");
  assert.equal(f.find((x) => x.key === "identity_crypto").level, "clear");
  const sum = f.reduce((a, x) => a + (x.contribution || 0), 0);
  assert.ok(Math.abs(sum - FX.snapshot.raw) < 1e-6);          // the lattice adds up to the engine's own number
  const b = scoreBreakdown(FX.snapshot);
  assert.equal(b.final, 85);
  assert.equal(factorView(null, []).every((x) => x.level === "na"), true);
});

test("evidence chain links are re-checked and a tampered link is caught", () => {
  const ok = chainView(FX.evidence, FX.verify);
  assert.ok(ok.slice(1).every((b) => b.linked === true));
  const bad = FX.evidence.map((e) => ({ ...e }));
  bad[5].prev_hash = "f".repeat(64);
  const v = chainView(bad, null);
  assert.equal(v.find((b) => b.seq === bad[5].seq).linked, false);
});

test("story rail marks only states that really happened", () => {
  const full = storyProgress(statePath(FX.history), "TRUSTED");
  assert.equal(full.pos, 6);
  assert.ok(full.marks.every((m) => m !== null));
  const back = storyProgress([{ state: "TRUSTED", ts: 1 }, { state: "QUARANTINED", ts: 2 }, { state: "RECOVERING", ts: 3 }, { state: "QUARANTINED", ts: 4 }], "QUARANTINED");
  assert.equal(back.pos, 2);
  assert.equal(back.marks[1], null);       // SUSPICIOUS never happened
  assert.equal(back.marks[3], null);       // the failed recovery is no longer "past"
});

test("score series ends at the live score", () => {
  const s = scoreSeries(FX.history, FX.snapshot, FX.snapshot && 2e9);
  assert.equal(s[0].score, 100);
  assert.equal(s[s.length - 1].score, FX.snapshot.score);
  assert.ok(s.filter((p) => p.transition).length >= 7);
});

test("formatting", () => {
  assert.equal(duration(42), "42 s");
  assert.equal(duration(2520), "42 min");
  assert.equal(countdown(125), "2:05");
  assert.equal(signed(-3), "−3");
});

test("every API route the dashboard uses is a gateway /api/v1 path", () => {
  for (const [name, fn] of Object.entries(ROUTES)) assert.match(fn("DEVICE-001"), /^\/api\/v1\//, name);
  assert.equal(ROUTES.recoveryStart("A B/../x"), "/api/v1/devices/A%20B%2F..%2Fx/recovery/start");
});

// ---- a second real run: the operator aborts the first recovery, then a second recovery succeeds ----
const AB = JSON.parse(readFileSync(new URL("./fixtures/abort-cycle.json", import.meta.url), "utf-8"));

test("abort cycle: the timeline shows who aborted, why, and the return to quarantine once", () => {
  const items = buildTimeline({ history: AB.history, events: AB.events, deviceId: DEV, evidenceByTrustEvent: evidenceIndex(AB.evidence) });
  const back = items.filter((i) => i.title === "Returned to quarantine");
  assert.equal(back.length, 1);
  assert.match(back[0].sub, /^Aborted by operator: Alice: second indicator of compromise/);
  assert.ok(back[0].related.some((e) => e.event_type === "recovery_failed"));        // not repeated as its own row
  assert.ok(!items.some((i) => i.type === "event" && i.events[0].event_type === "recovery_failed"));
  const starts = items.filter((i) => i.isState && i.stateTo === "RECOVERING");
  assert.equal(starts.length, 2);
  assert.ok(starts.every((i) => i.operator === "alice"));
  // refused normal-channel messages: one entry per containment episode, with the count
  const blocked = items.filter((i) => i.type === "event" && i.events[0].event_type === "quarantine_access_blocked");
  const total = AB.events.filter((e) => e.event_type === "quarantine_access_blocked").length;
  assert.ok(blocked.length >= 1 && blocked.length <= 2, String(blocked.length));
  assert.equal(blocked.reduce((n, i) => n + i.events.length, 0), total);
  // operator-management actions (no device) stay out of the device story
  assert.ok(!items.some((i) => /created an operator/.test(i.title)));
});

test("abort cycle: incident resolved by the second recovery, failed attempt counted", () => {
  const incs = buildIncidents({ deviceId: DEV, history: AB.history, snapshot: AB.snapshot, recoveries: AB.recovery.history,
    events: AB.events, observations: AB.observations });
  assert.equal(incs.length, 1);
  assert.equal(incs[0].status, "resolved");
  assert.equal(incs[0].failedAttempts, 1);
  const path = statePath(AB.history).map((p) => p.state);
  assert.deepEqual(path.slice(0, 4), ["TRUSTED", "SUSPICIOUS", "QUARANTINED", "RECOVERING"]);
  assert.ok(path.includes("QUARANTINED", 3));              // back to quarantine after the abort
  assert.equal(storyProgress(statePath(AB.history), "TRUSTED").pos, 6);
});

// ---- presentation polish: rejected attacks, connection wording, presentation feed ----
import { connectionView, rejectionNote } from "../src/lib/derive.js";
import { meaningful } from "../src/pages/live.js";

test("forged and replayed observations read as rejected attacks, with what the gateway checked", () => {
  const items = buildTimeline({ history: FX.history, events: FX.events, deviceId: DEV, sigAlg: "ML-DSA-65" });
  const forged = items.find((i) => i.title === "Forged observation rejected");
  const replay = items.find((i) => i.title === "Replayed observation rejected");
  assert.ok(forged.rejected && replay.rejected);
  assert.equal(forged.sub, "ML-DSA-65 signature did not verify; bounded pressure only.");
  assert.equal(replay.sub, "Previously accepted signed observation was replayed; replay rejected.");
  const tag = items.find((i) => i.title === "Device message failed authentication");     // forged "all clear" while quarantined
  assert.ok(tag.rejected && /HMAC-SHA256 tag did not verify/.test(tag.sub));
  // genuine evidence is never labelled as a rejected attack
  assert.ok(!items.find((i) => i.stateTo === "QUARANTINED" && i.isState).rejected);
  assert.ok(!items.find((i) => i.stateTo === "SUSPICIOUS" && i.isState).rejected);
  assert.equal(rejectionNote("visual_observation"), null);
});

test("presentation feed keeps security decisions and drops entries that changed nothing", () => {
  const items = buildTimeline({ history: AB.history, events: AB.events, deviceId: DEV });
  const feed = items.filter(meaningful);
  assert.ok(items.some((i) => i.type === "score" && i.delta === 0));                // e.g. "Liveness fading ±0" exists ...
  assert.ok(!feed.some((i) => i.type === "score" && i.delta === 0));                // ... but never takes a slot
  assert.equal(feed.filter((i) => i.isState).length, items.filter((i) => i.isState).length);
  assert.ok(feed.some((i) => i.type === "event" && i.events[0].event_type === "quarantine_access_blocked"));
  assert.ok(feed.some((i) => i.rejected));
});

test("a quarantined device that is still talking is 'Blocked by quarantine', a silent one is offline", () => {
  const dev = { device_id: DEV, status: "OFFLINE" };
  const refused = [{ device_id: DEV, event_type: "quarantine_access_blocked", received_at: 1000 }];
  assert.equal(connectionView({ device: dev, state: "QUARANTINED", events: refused, now: 1012 }).label, "Blocked by quarantine");
  assert.equal(connectionView({ device: dev, state: "QUARANTINED", events: refused, now: 1200 }).label, "Offline");
  assert.equal(connectionView({ device: dev, state: "QUARANTINED", events: [], now: 1012 }).label, "Offline");
  const rec = connectionView({ device: { ...dev, status: "ONLINE" }, state: "RECOVERING", events: [], now: 1012 });
  assert.deepEqual([rec.label, rec.caption], ["Blocked by quarantine", "Reporting on the recovery channel only"]);
  assert.equal(connectionView({ device: { ...dev, status: "ONLINE" }, state: "TRUSTED" }).label, "Online");
  assert.equal(connectionView({ device: dev, state: "TRUSTED" }).label, "Offline");               // genuine offline kept
  assert.equal(connectionView({ device: { ...dev, status: "ENROLLED" }, state: null }).label, "Never connected");
});

test("vision observations show the gateway's verdict, and synthetic detections are labelled", () => {
  const [person, chair] = FX.observations.map(observationView);
  assert.deepEqual([person.title, person.confidence, person.signed, person.alg, person.signer, person.synthetic],
    ["Person detected", 0.9, true, "ML-DSA-65", "vision-1", true]);
  assert.equal(person.rule, "restricted class in restricted zone");
  assert.equal(person.zone, "restricted zone", "zone kind is not repeated when the name already says it");
  assert.equal(chair.rule, null);
  const health = observationView({ observation_id: "h", received_at: 5, event_type: "camera_health", details: { state: "source_lost" },
    auth: "ML-DSA-65:vision-1", model: { name: "yolo11n", version: "8.3" } });
  assert.deepEqual([health.title, health.confidence, health.synthetic, health.model], ["Camera health: source lost", null, false, "yolo11n 8.3"]);
  const unsigned = observationView({ observation_id: "u", received_at: 6, event_type: "visual_observation", object: "car", confidence: 0.5, auth: null });
  assert.deepEqual([unsigned.signed, unsigned.alg, unsigned.signer], [false, null, null], "an ingest-token post is never shown as signed");
});

test("vision status reports the latest path, camera health and rule matches from stored observations only", () => {
  const obs = [
    { observation_id: "c", received_at: 300, event_type: "visual_observation", object: "person", confidence: 0.8, anomaly: true,
      anomaly_reason: "restricted_class_in_restricted_zone", auth: "ML-DSA-65:vision-1", transport: "secure" },
    { observation_id: "b", received_at: 200, event_type: "camera_health", details: { state: "obstructed" }, anomaly: true,
      auth: "ML-DSA-65:vision-1", transport: "secure" },
    { observation_id: "a", received_at: 100, event_type: "visual_observation", object: "car", confidence: 0.5, anomaly: false,
      auth: "ingest-token", transport: "token" },
  ];
  const vs = visionStatus(obs, 312);
  assert.equal(vs.last.key, "c");
  assert.equal(vs.last.transport, "secure");
  assert.equal(vs.lastAgeS, 12);
  assert.deepEqual(vs.camera, { state: "obstructed", since: 200 });
  assert.deepEqual([vs.total, vs.signed, vs.rules], [3, 2, 2]);
  assert.equal(observationView(obs[2]).signed, false);
  assert.equal(visionStatus([], 10).camera, null, "no camera-health report means no fault reported, not 'ok'");
  assert.equal(visionStatus([], 10).last, null);
});
