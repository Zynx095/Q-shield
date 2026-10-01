// Empty, error and loading states. Each one says what is going on and what to do next.
import { html } from "../lib/html.js";
import { icon } from "./icons.js";

export function empty({ title, text = "", iconName = "info", ok = false, action = "" }) {
  return html`<div class="empty ${ok ? "is-ok" : ""}">${icon(iconName)}<div class="h-panel">${title}</div>${text ? html`<p>${text}</p>` : ""}${action}</div>`;
}

export function banner(tone, iconName, title, text = "") {
  return html`<div class="banner ${tone}" role="${tone === "crit" ? "alert" : "status"}">${icon(iconName)}<div><b>${title}</b>${text ? html` <span class="banner-text">${text}</span>` : ""}</div></div>`;
}

export function skeleton(h = 16, w = "100%") {
  return html`<div class="skeleton" style="height:${Number(h)}px;width:${w}" aria-hidden="true"></div>`;
}

export function loadingPanel(lines = 4) {
  const rows = [];
  for (let i = 0; i < lines; i++) rows.push(skeleton(14, `${90 - i * 12}%`));
  return html`<div class="stack-sm" aria-busy="true" aria-label="Loading">${rows}</div>`;
}
