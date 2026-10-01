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

// ---------------------------------------------------------------------------------------------- controller (no DOM)
export function createCameraController({ media = globalThis.navigator && globalThis.navigator.mediaDevices, onChange = () => {} } = {}) {
  const st = { status: "idle", stream: null, error: null, info: null };
  let seq = 0;                                      // a newer start()/stop() supersedes a pending request

  const snapshot = () => ({ status: st.status, error: st.error, info: st.info, stream: st.stream });
  const emit = () => onChange(snapshot());

  function stopTracks() {
    if (st.stream) for (const t of st.stream.getTracks()) t.stop();
    st.stream = null;
    st.info = null;
  }

  async function start() {
    const mine = ++seq;
    stopTracks();
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
      const stream = await media.getUserMedia({ video: { ...IDEAL }, audio: false });
      if (mine !== seq) { for (const t of stream.getTracks()) t.stop(); return; }
      st.stream = stream;
      st.info = describeTrack(stream.getVideoTracks()[0]);
      st.status = "live";
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

  return { start, stop, get state() { return snapshot(); } };
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
  const startBtn = el("button", "btn accent", "Start preview");
  startBtn.type = "button";
  const stopBtn = el("button", "btn", "Stop preview");
  stopBtn.type = "button";
  controls.append(startBtn, stopBtn);
  root.append(stage, status, controls);
  host.append(root);

  startBtn.addEventListener("click", () => ctl.start());
  stopBtn.addEventListener("click", () => ctl.stop());

  function update(s) {
    root.dataset.status = s.status;
    if (video.srcObject !== s.stream) video.srcObject = s.stream;
    placeholder.hidden = s.status === "live";
    const res = s.info && s.info.width ? ` ${s.info.width}×${s.info.height} as reported by the camera.` : "";
    status.textContent = s.status === "live" ? `${STATUS_TEXT.live}${s.info && s.info.label ? ` ${s.info.label}.` : ""}${res}` : STATUS_TEXT[s.status] || "";
    startBtn.disabled = s.status === "requesting" || s.status === "live";
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
  }

  release() {
    this.ctl.stop();
    this.host = null;
    this.view = null;
  }
}
