// Camera preview controller (src/components/camera.js), run against fake media devices, permissions and pages.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { cameraLabel, classifyCameraError, createCameraController, describeTrack } from "../src/components/camera.js";

const tick = () => new Promise((r) => setTimeout(r, 0));

function fakeEnv({ devices = [["int", "Integrated Camera"], ["usb", "USB Camera"]], fail = null } = {}) {
  const log = [];
  const ended = {};
  const listeners = { media: {}, doc: {}, win: {}, perm: {} };
  const track = (id) => ({
    label: devices.find(([d]) => d === id)?.[1] || "Default camera",
    stop() { log.push(`stop ${id}`); },
    getSettings: () => ({ deviceId: id, width: 1280, height: 720, frameRate: 30 }),
    addEventListener: (n, f) => { if (n === "ended") ended[id] = f; },
  });
  const media = {
    calls: [],
    async getUserMedia(c) {
      media.calls.push(c);
      if (fail) { const e = new Error("fail"); e.name = fail; throw e; }
      const id = c.video.deviceId ? c.video.deviceId.exact : devices[0][0];
      log.push(`open ${id}`);
      const t = track(id);
      return { getTracks: () => [t], getVideoTracks: () => [t] };
    },
    async enumerateDevices() {
      return [...devices.map(([deviceId, label]) => ({ kind: "videoinput", deviceId, label })), { kind: "audioinput", deviceId: "mic", label: "Mic" }];
    },
    addEventListener: (n, f) => { listeners.media[n] = f; },
    removeEventListener: (n) => { delete listeners.media[n]; },
  };
  const mem = new Map();
  const storage = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v), removeItem: (k) => mem.delete(k) };
  const doc = { hidden: false, addEventListener: (n, f) => { listeners.doc[n] = f; }, removeEventListener: (n) => { delete listeners.doc[n]; } };
  const win = { addEventListener: (n, f) => { listeners.win[n] = f; }, removeEventListener: (n) => { delete listeners.win[n]; } };
  const permissions = { query: async () => ({ state: "prompt", addEventListener: (n, f) => { listeners.perm[n] = f; }, removeEventListener: (n) => { delete listeners.perm[n]; } }) };
  return { log, ended, listeners, media, mem, storage, doc, win, permissions };
}

const make = (env, extra = {}) => createCameraController({ media: env.media, storage: env.storage, doc: env.doc, win: env.win,
  permissions: env.permissions, secure: true, ...extra });

test("camera: nothing opens the camera until Start is pressed", async () => {
  const env = fakeEnv();
  const c = make(env);
  await c.refreshDevices();
  await tick();
  assert.equal(env.media.calls.length, 0, "listing cameras and reading the permission never call getUserMedia");
  assert.equal(c.state.status, "idle");
  assert.equal(c.state.permission, "prompt");
  assert.deepEqual(c.state.devices.map((d) => d.label), ["Integrated Camera", "USB Camera"], "video inputs only");
});

test("camera: video only at an ideal 1280x720; stop releases every track", async () => {
  const env = fakeEnv();
  const seen = [];
  const c = make(env, { onChange: (s) => seen.push(s.status) });
  await c.start();
  assert.deepEqual(env.media.calls[0], { video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
  assert.equal(c.state.status, "live");
  assert.deepEqual(c.state.info, { label: "Integrated Camera", deviceId: "int", width: 1280, height: 720 }, "no frame rate is surfaced");
  c.stop();
  assert.equal(c.state.status, "idle");
  assert.equal(c.state.stream, null);
  assert.deepEqual(env.log, ["open int", "stop int"]);
  assert.deepEqual(seen.filter((x, i) => x !== seen[i - 1]), ["requesting", "live", "idle"]);
});

test("camera: switching stops the old camera before opening the new one, and is remembered for the tab", async () => {
  const env = fakeEnv();
  const c = make(env);
  await c.start();
  c.choose("usb");
  await tick();
  assert.deepEqual(env.log, ["open int", "stop int", "open usb"], "exclusive webcams need the old stream closed first");
  assert.deepEqual(env.media.calls[1].video.deviceId, { exact: "usb" });
  assert.equal(c.state.deviceId, "usb");
  assert.equal(env.mem.get("qshield_camera"), "usb");
  assert.equal(make(env).state.deviceId, "usb", "a new controller in the same tab starts from the remembered camera");
  env.mem.set("qshield_camera", "unplugged-id");
  const c3 = make(env);
  await c3.refreshDevices();
  assert.equal(c3.state.deviceId, null, "a remembered camera that is gone falls back to the default");
  assert.equal(env.mem.has("qshield_camera"), false);
});

test("camera: a request superseded by Stop never leaves the camera on", async () => {
  const env = fakeEnv();
  let release;
  env.media.getUserMedia = (c) => new Promise((r) => { release = () => { const t = { label: "", stop() { env.log.push("stop late"); }, getSettings: () => ({}) }; r({ getTracks: () => [t], getVideoTracks: () => [t] }); }; });
  const c = make(env);
  const p = c.start();
  assert.equal(c.state.status, "requesting");
  c.stop();
  release();
  await p;
  assert.equal(c.state.status, "idle");
  assert.deepEqual(env.log, ["stop late"]);
});

test("camera: hidden tab releases the camera and resumes; unplug and page exit are handled; release removes listeners", async () => {
  const env = fakeEnv();
  const c = make(env);
  await c.start();
  env.doc.hidden = true;
  env.listeners.doc.visibilitychange();
  assert.equal(c.state.status, "paused");
  assert.equal(env.log.at(-1), "stop int");
  env.doc.hidden = false;
  env.listeners.doc.visibilitychange();
  await tick();
  assert.equal(c.state.status, "live");
  env.ended.int();
  assert.equal(c.state.status, "ended");
  await c.start();
  env.listeners.win.pagehide();
  assert.equal(c.state.status, "idle");
  assert.equal(env.log.at(-1), "stop int");
  c.release();
  for (const k of ["media", "doc", "win", "perm"]) assert.deepEqual(Object.keys(env.listeners[k]), [], k);
});

test("camera: an insecure page never asks for the camera", async () => {
  const env = fakeEnv();
  const c = make(env, { secure: false });
  await c.start();
  assert.equal(env.media.calls.length, 0);
  assert.equal(c.state.status, "error");
  assert.equal(c.state.error.kind, "insecure");
});

test("camera: every failure is explained with a next step", async () => {
  const kinds = { NotAllowedError: "denied", PermissionDeniedError: "denied", NotFoundError: "none", OverconstrainedError: "missing",
    NotReadableError: "in-use", TrackStartError: "in-use", AbortError: "in-use", NotSupportedError: "unsupported", SecurityError: "insecure", Odd: "error" };
  for (const [name, kind] of Object.entries(kinds)) {
    const e = classifyCameraError({ name });
    assert.equal(e.kind, kind, name);
    assert.ok(e.title && e.text.length > 20, name);
  }
  const busy = classifyCameraError({ name: "NotReadableError" });
  assert.match(busy.text, /vision service/);
  assert.match(busy.text, /config\/vision\.json/);
  const lan = classifyCameraError(null, { secure: false, host: "192.168.1.20:8765" });
  assert.match(lan.text, /192\.168\.1\.20:8765/);
  assert.match(lan.text, /localhost/);
  assert.match(lan.text, /QSHIELD_TLS_CERT/);
  const env = fakeEnv({ fail: "NotReadableError" });
  const c = make(env);
  await c.start();
  assert.equal(c.state.status, "error");
  assert.equal(c.state.error.kind, "in-use");
});

test("camera: names before permission, and what is shown about a track", () => {
  assert.equal(cameraLabel({ label: "" }, 1), "Camera 2");
  assert.equal(cameraLabel({ label: "USB Camera" }, 0), "USB Camera");
  assert.equal(describeTrack(null), null);
});

test("camera: the preview cannot send, record or capture frames", () => {
  const src = readFileSync(new URL("../src/components/camera.js", import.meta.url), "utf-8");
  for (const banned of ["fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "MediaRecorder", "captureStream", "toDataURL", "toBlob",
    "drawImage", "getImageData", "ImageCapture", "localStorage", "store.js", "api.js"]) {
    assert.ok(!src.includes(banned), banned);
  }
});
