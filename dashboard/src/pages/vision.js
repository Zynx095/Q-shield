// Camera & vision: what this browser's camera sees (a local preview; nothing leaves the page) beside what the Python
// vision service actually reported to the gateway (signed observations). They are kept apart on purpose: the preview
// is never analysed, and no signed observation ever came from this browser.
import { html } from "../lib/html.js";
import { icon } from "../components/icons.js";
import { banner } from "../components/states.js";
import { CameraMonitor } from "../components/camera.js";

let monitor = null;

/** After each render (main.js): give the preview its mount. The mount is data-morph-skip, so refreshes leave it be. */
export function mount() {
  const host = document.getElementById("cam-mount");
  if (!host) return;
  if (!monitor) monitor = new CameraMonitor();
  monitor.attach(host);
}

/** Leaving the page or signing out: turn the camera off. */
export function release() {
  if (!monitor) return;
  monitor.release();
  monitor = null;
}

function previewPanel() {
  return html`<section class="panel" aria-labelledby="cam-title" data-reveal>
    <div class="panel-head"><h2 class="panel-title" id="cam-title">${icon("camera")}Live camera preview (this browser)</h2></div>
    <div class="panel-body stack-sm">
      ${banner("info", "info", "Local preview only.", "Not analysed, not signed, not sent to the gateway. The video stays on this page.")}
      <div id="cam-mount" data-morph-skip></div>
      <p class="caption">The vision service opens its own camera: the one set by <span class="mono">camera.source</span> in
        <span class="mono">config/vision.json</span>. Most webcams serve one program at a time, so preview the other camera, for example
        the integrated one while the USB camera feeds the vision service.</p>
    </div>
  </section>`;
}

export function render() {
  return html`<div class="page-head"><div><h1 class="h-page">Camera &amp; vision</h1>
    <p class="lead">A live preview from this browser's camera, beside the signed observations the vision service sent the gateway. The two are separate: the preview is never analysed or sent anywhere.</p></div></div>
  <div class="grid split-7-5">${previewPanel()}</div>`;
}
