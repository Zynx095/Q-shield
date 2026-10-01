// Live camera preview for the "Camera & vision" page.
//
// LOCAL ONLY. The stream goes from this browser's camera to a <video> element on the page and nowhere else: it is
// not analysed, not recorded, not signed and never sent to the gateway. Signed observations come from the separate
// Python vision service (python -m ai.vision), which opens its own camera. Nothing here may suggest otherwise, so
// the preview draws no detections, boxes, confidence or frame rate over the video.
//
// The monitor owns its DOM: the page gives it a mount marked data-morph-skip, so the 2-second refresh never
// replaces the <video> element. Every node is built with createElement and textContent, never parsed from markup.

const IDEAL = { width: { ideal: 1280 }, height: { ideal: 720 } };

/** What the browser reports about the running video track: its label and the resolution the camera delivers. */
export function describeTrack(track) {
  if (!track) return null;
  const s = track.getSettings ? track.getSettings() : {};
  return { label: track.label || "", deviceId: s.deviceId || null, width: s.width || null, height: s.height || null };
}

/** A camera's name. Browsers hide names until camera permission is granted, so fall back to its position. */
export function cameraLabel(device, index) {
  return (device && device.label) || `Camera ${index + 1}`;
}

// ---------------------------------------------------------------------------------------------- controller (no DOM)
const NAV = globalThis.navigator;
const PREF = "qshield_camera";                      // the chosen camera, per tab (sessionStorage, like the session)

function storageOf(storage) {
  return {
    get: () => { try { return storage ? storage.getItem(PREF) : null; } catch { return null; } },
    set: (v) => { try { if (!storage) return; if (v) storage.setItem(PREF, v); else storage.removeItem(PREF); } catch { /* memory only */ } },
  };
}

export function createCameraController({
  media = NAV && NAV.mediaDevices, permissions = NAV && NAV.permissions, secure = globalThis.isSecureContext !== false,
  storage = globalThis.sessionStorage, onChange = () => {},
} = {}) {
  const pref = storageOf(storage);
  // permission: "granted" | "prompt" | "denied" | null (unknown). The camera is only ever opened by start().
  const st = { status: "idle", stream: null, error: null, info: null, devices: [], chosen: pref.get(), permission: null };
  let seq = 0;                                      // a newer start()/stop() supersedes a pending request

  const snapshot = () => ({ status: st.status, error: st.error, info: st.info, stream: st.stream, devices: st.devices,
    deviceId: (st.info && st.info.deviceId) || st.chosen, permission: st.permission, secure });
  const emit = () => onChange(snapshot());

  function stopTracks() {
    if (st.stream) for (const t of st.stream.getTracks()) t.stop();
    st.stream = null;
    st.info = null;
  }

  /** List the video inputs (integrated, USB, virtual). Called on load, after permission and on plug / unplug. */
  async function refreshDevices() {
    if (!media || typeof media.enumerateDevices !== "function") return;
    try {
      const all = await media.enumerateDevices();
      st.devices = all.filter((d) => d.kind === "videoinput").map((d, i) => ({ deviceId: d.deviceId, label: cameraLabel(d, i) }));
      // a remembered camera that is no longer attached: fall back to the browser's default
      if (st.chosen && st.devices.length && st.devices.every((d) => d.deviceId && d.deviceId !== st.chosen)) { st.chosen = null; pref.set(null); }
    } catch { st.devices = []; }
    emit();
  }
  const onDeviceChange = () => { refreshDevices(); };
  if (media && typeof media.addEventListener === "function") media.addEventListener("devicechange", onDeviceChange);

  // Read (never request) the camera permission, so the page can explain a block before the person presses Start.
  let permStatus = null;
  const onPermission = () => { st.permission = permStatus.state; refreshDevices(); };
  if (permissions && typeof permissions.query === "function") {
    permissions.query({ name: "camera" }).then((ps) => {
      permStatus = ps;
      st.permission = ps.state;
      if (typeof ps.addEventListener === "function") ps.addEventListener("change", onPermission);
      emit();
    }, () => {});                                   // "camera" not queryable in this browser: stay unknown
  }

  /** Choose a camera. While the preview runs this switches: the old stream is stopped before the new one opens,
   *  because most webcams (on Windows especially) serve one program at a time. */
  function choose(deviceId) {
    st.chosen = deviceId || null;
    pref.set(st.chosen);
    if (st.status === "live" || st.status === "requesting") start();
    else emit();
  }

  async function start() {
    const mine = ++seq;
    stopTracks();
    if (!secure) {                                  // browsers expose cameras only to HTTPS and localhost pages
      st.status = "error";
      st.error = { kind: "insecure", name: "SecurityError" };
      emit();
      return;
    }
    if (!media || typeof media.getUserMedia !== "function") {
      st.status = "error";
      st.error = { kind: "unsupported", name: "NotSupportedError" };
      emit();
      return;
    }
    st.status = "requesting";
    st.error = null;
    emit();
    try {
      const video = st.chosen ? { deviceId: { exact: st.chosen }, ...IDEAL } : { ...IDEAL };
      const stream = await media.getUserMedia({ video, audio: false });
      if (mine !== seq) { for (const t of stream.getTracks()) t.stop(); return; }
      st.stream = stream;
      st.info = describeTrack(stream.getVideoTracks()[0]);
      st.status = "live";
      st.permission = "granted";
      refreshDevices();                             // names become readable once permission is granted
    } catch (err) {
      if (mine !== seq) return;
      st.status = "error";
      st.error = { kind: "error", name: (err && err.name) || "Error" };
    }
    emit();
  }

  /** Stop the preview and release the camera (the light goes off; another program can open it). */
  function stop() {
    seq++;
    stopTracks();
    st.status = "idle";
    st.error = null;
    emit();
  }

  /** Stop and stop listening: the page is going away. */
  function release() {
    stop();
    if (media && typeof media.removeEventListener === "function") media.removeEventListener("devicechange", onDeviceChange);
    if (permStatus && typeof permStatus.removeEventListener === "function") permStatus.removeEventListener("change", onPermission);
  }

  return { start, stop, choose, refreshDevices, release, get state() { return snapshot(); } };
}

// ---------------------------------------------------------------------------------------------- view
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

const STATUS_TEXT = {
  idle: "Preview off. The camera is not in use by this page.",
  requesting: "Asking the browser for the camera…",
  live: "Preview running in this browser only.",
  error: "The camera could not be opened.",
};

function mountCameraView(host, ctl) {
  host.replaceChildren();
  const root = el("div", "cam");
  const stage = el("div", "cam-stage");
  const video = el("video", "cam-video");
  video.muted = true;
  video.autoplay = true;
  video.playsInline = true;
  video.setAttribute("aria-label", "Live camera preview");
  const placeholder = el("div", "cam-placeholder", "Preview off");
  stage.append(video, placeholder);
  const status = el("p", "cam-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const controls = el("div", "cam-controls");
  const pick = el("label", "cam-pick");
  const select = el("select", "select");
  select.id = "cam-device";
  pick.append(el("span", "caption", "Camera"), select);
  const count = el("span", "caption cam-count");
  const startBtn = el("button", "btn accent", "Start preview");
  startBtn.type = "button";
  const stopBtn = el("button", "btn", "Stop preview");
  stopBtn.type = "button";
  controls.append(pick, startBtn, stopBtn, count);
  const note = el("p", "caption cam-note");
  root.append(stage, status, controls, note);
  host.append(root);

  startBtn.addEventListener("click", () => ctl.start());
  stopBtn.addEventListener("click", () => ctl.stop());
  select.addEventListener("change", () => ctl.choose(select.value));

  function update(s) {
    root.dataset.status = s.status;
    if (video.srcObject !== s.stream) video.srcObject = s.stream;
    placeholder.hidden = s.status === "live";
    const res = s.info && s.info.width ? ` ${s.info.width}×${s.info.height} as reported by the camera.` : "";
    status.textContent = s.status === "live" ? `${STATUS_TEXT.live}${s.info && s.info.label ? ` ${s.info.label}.` : ""}${res}` : STATUS_TEXT[s.status] || "";
    const opts = s.devices.map((d) => `${d.deviceId}=${d.label}`).join("|");
    if (select.dataset.opts !== opts) {                // rebuild only when the list really changed
      select.dataset.opts = opts;
      select.replaceChildren(...s.devices.map((d) => { const o = el("option", "", d.label); o.value = d.deviceId; return o; }));
    }
    if (s.deviceId && select.value !== s.deviceId) select.value = s.deviceId;
    pick.hidden = s.devices.length === 0;
    count.textContent = s.devices.length ? `${s.devices.length} camera${s.devices.length === 1 ? "" : "s"} found` : "No camera listed yet";
    note.textContent = !s.secure
      ? `Camera preview needs HTTPS or localhost. This page is served over plain HTTP from ${location.host}, so the browser offers no camera here. Open it as http://localhost or http://127.0.0.1 on this machine, or start the gateway with QSHIELD_TLS_CERT and QSHIELD_TLS_KEY.`
      : s.permission === "denied" && s.status !== "live"
        ? "Camera access is blocked for this site. Allow it in the browser's site settings (the camera icon in the address bar), then press Start preview."
        : s.status === "live" ? "" : "Nothing starts until you press Start preview. The browser then asks for camera access; video only, no microphone.";
    startBtn.disabled = !s.secure || s.status === "requesting" || s.status === "live";
    stopBtn.disabled = s.status !== "live" && s.status !== "requesting";
  }
  return { update };
}

// ---------------------------------------------------------------------------------------------- monitor
/** A camera controller plus its view. attach() is idempotent per host; release() turns the camera off. */
export class CameraMonitor {
  constructor(opts = {}) {
    this.view = null;
    this.host = null;
    this.ctl = createCameraController({ ...opts, onChange: (s) => this.view && this.view.update(s) });
  }

  attach(host) {
    if (!host || host === this.host) return;
    this.host = host;
    this.view = mountCameraView(host, this.ctl);
    this.view.update(this.ctl.state);
    this.ctl.refreshDevices();
  }

  release() {
    this.ctl.release();
    this.host = null;
    this.view = null;
  }
}
