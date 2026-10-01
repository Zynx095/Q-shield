// Sign-in: an operator token is checked against the gateway before anything is shown.
import { html } from "../lib/html.js";
import { brandMark, icon } from "../components/icons.js";

export function signInView({ error = null, busy = false, info = null }) {
  const http = location.protocol === "http:";
  return html`<main class="signin" id="content">
    <div class="signin-card">
      <div class="row" style="gap:12px;margin-bottom:28px">${brandMark}<div><div class="brand-name">Q-SHIELD</div><div class="brand-sub">Security command center</div></div></div>
      <h1 class="h-page" style="font-size:1.75rem">Sign in to the gateway</h1>
      <p class="meta" style="margin-top:8px">Use your operator token. It was printed when your operator was created, or by the demo script for the shared bootstrap operator.</p>
      <form class="stack" style="margin-top:24px" data-signin novalidate>
        <div class="field ${error ? "has-error" : ""}">
          <label for="signin-token">Operator token</label>
          <input class="input mono" id="signin-token" name="token" type="password" autocomplete="off" spellcheck="false" required aria-describedby="signin-hint${error ? " signin-error" : ""}" ${busy ? "disabled" : ""}>
          <span class="hint" id="signin-hint">Kept only in this browser tab's session storage. Never shown on screen.</span>
          ${error ? html`<span class="field-error" id="signin-error" role="alert">${error}</span>` : ""}
        </div>
        ${info ? html`<div class="banner info">${icon("info")}<div class="banner-text">${info}</div></div>` : ""}
        <button class="btn primary" type="submit" ${busy ? "disabled" : ""}>${busy ? html`<span class="spinner" aria-hidden="true"></span>Checking token…` : html`${icon("lock")}Sign in`}</button>
      </form>
      <dl class="kv" style="margin-top:28px">
        <dt>Gateway</dt><dd class="mono">${location.origin}</dd>
        <dt>Transport</dt><dd>${http ? html`<span style="color:var(--warn)">HTTP: the token crosses the network unencrypted</span>` : "HTTPS"}</dd>
      </dl>
    </div>
  </main>`;
}
