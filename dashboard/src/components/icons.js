// Inline stroke icons (24-unit grid, 1.75 stroke). Static markup only, so raw() is safe here.
import { raw } from "../lib/html.js";

const P = {
  overview: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  devices: '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6" rx="1"/><path d="M9 1.5V4M15 1.5V4M9 20v2.5M15 20v2.5M1.5 9H4M1.5 15H4M20 9h2.5M20 15h2.5"/>',
  incident: '<path d="M12 3 2.5 20h19L12 3Z"/><path d="M12 10v4.5M12 17.5v.01"/>',
  alert: '<path d="M12 3 2.5 20h19L12 3Z"/><path d="M12 10v4.5M12 17.5v.01"/>',
  ledger: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><path d="M10 6.5h4a3 3 0 0 1 3 3V14"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8"/><path d="M4 3.5V8h4.5"/><path d="M4 13a8 8 0 0 0 14.3 4.9L20 16"/><path d="M20 20.5V16h-4.5"/>',
  twin: '<rect x="2.5" y="5" width="8" height="14" rx="1.5"/><rect x="13.5" y="5" width="8" height="14" rx="1.5"/><path d="M5 9h3M5 12h3M16 9h3M16 12h3"/>',
  key: '<circle cx="8" cy="15" r="4.5"/><path d="m11.2 11.8 8.3-8.3M16.5 6.5l2.5 2.5M14 9l2 2"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
  present: '<rect x="2.5" y="4" width="19" height="13" rx="1.5"/><path d="M12 17v3.5M8 20.5h8"/><path d="m10 8.5 4.5 2.5-4.5 2.5v-5Z"/>',
  shield: '<path d="M12 2.8 4.5 5.6v5.9c0 4.7 3.2 8.4 7.5 9.7 4.3-1.3 7.5-5 7.5-9.7V5.6L12 2.8Z"/>',
  shieldCheck: '<path d="M12 2.8 4.5 5.6v5.9c0 4.7 3.2 8.4 7.5 9.7 4.3-1.3 7.5-5 7.5-9.7V5.6L12 2.8Z"/><path d="m8.8 12 2.2 2.2 4.4-4.6"/>',
  shieldAlert: '<path d="M12 2.8 4.5 5.6v5.9c0 4.7 3.2 8.4 7.5 9.7 4.3-1.3 7.5-5 7.5-9.7V5.6L12 2.8Z"/><path d="M12 8v4.5M12 15.8v.01"/>',
  lock: '<rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/><path d="M12 14.5v2.5"/>',
  unlock: '<rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 7.7-1.5"/><path d="M12 14.5v2.5"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  checkCircle: '<circle cx="12" cy="12" r="9"/><path d="m8.2 12.2 2.6 2.6 5-5.2"/>',
  badgeCheck: '<path d="M12 2.5 14.5 4.6l3.2-.3.9 3.1 2.9 1.5-1.2 3 1.2 3-2.9 1.5-.9 3.1-3.2-.3L12 21.5l-2.5-2.1-3.2.3-.9-3.1-2.9-1.5 1.2-3-1.2-3 2.9-1.5.9-3.1 3.2.3L12 2.5Z"/><path d="m8.6 12.2 2.3 2.3 4.6-4.8"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  xCircle: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.6v.01"/>',
  dot: '<circle cx="12" cy="12" r="3.5"/>',
  minus: '<path d="M6 12h12"/>',
  arrowRight: '<path d="M4.5 12h15M13.5 6l6 6-6 6"/>',
  arrowDown: '<path d="M12 4.5v15M6 13.5l6 6 6-6"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  chevronRight: '<path d="m9 6 6 6-6 6"/>',
  chevronLeft: '<path d="m15 6-6 6 6 6"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  fingerprint: '<path d="M7 6.5a7 7 0 0 1 11.5 4.3"/><path d="M5 11.5a7 7 0 0 1 .7-3"/><path d="M5.3 15.5c.9-1.1 1.2-2.4 1.2-4a5.5 5.5 0 0 1 11 0c0 1.3-.1 2.6-.4 3.8"/><path d="M9 20a10 10 0 0 0 1.5-5.5V11.5a1.5 1.5 0 0 1 3 0v2.5"/><path d="M15 20.5c.6-1 1-2.1 1.3-3.3"/><path d="M12.5 21.5c.5-1.3.9-2.7 1-4.2"/>',
  box: '<path d="M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5v-9Z"/><path d="M3.5 7.5 12 12l8.5-4.5M12 12v9"/>',
  fileCheck: '<path d="M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8l-5-5Z"/><path d="M14 3v5h5"/><path d="m9 14.5 2 2 4-4.2"/>',
  thermo: '<path d="M14 14.8V4.5a2 2 0 0 0-4 0v10.3a4 4 0 1 0 4 0Z"/><path d="M12 17.5v.01"/>',
  eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
  signal: '<path d="M4.5 19.5v-3M9.5 19.5v-7M14.5 19.5V9M19.5 19.5V4.5"/>',
  link: '<path d="M10 13.5a4.5 4.5 0 0 0 6.4.3l2.8-2.8a4.5 4.5 0 0 0-6.4-6.4l-1.2 1.2"/><path d="M14 10.5a4.5 4.5 0 0 0-6.4-.3l-2.8 2.8a4.5 4.5 0 0 0 6.4 6.4l1.2-1.2"/>',
  unlink: '<path d="M10 13.5a4.5 4.5 0 0 0 6.4.3l2.8-2.8a4.5 4.5 0 0 0-6.4-6.4"/><path d="M14 10.5a4.5 4.5 0 0 0-6.4-.3l-2.8 2.8a4.5 4.5 0 0 0 6.4 6.4"/><path d="M3 3l18 18"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
  server: '<rect x="3.5" y="3.5" width="17" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="17" height="7" rx="1.5"/><path d="M7 7h.01M7 17h.01"/>',
  plugOff: '<path d="M9 7V3M15 7V3M6.5 7h11v4a5.5 5.5 0 0 1-11 0V7Z"/><path d="M12 16.5V21"/><path d="M3 3l18 18"/>',
  camera: '<path d="M3 8.5A1.5 1.5 0 0 1 4.5 7H7l1.5-2.5h7L17 7h2.5A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5v-9Z"/><circle cx="12" cy="12.5" r="3.5"/>',
  cpu: '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6" rx=".5"/><path d="M9 2.5V5M15 2.5V5M9 19v2.5M15 19v2.5M2.5 9H5M2.5 15H5M19 9h2.5M19 15h2.5"/>',
  hash: '<path d="M5 9h15M4 15h15M10 3 8 21M16 3l-2 18"/>',
  signature: '<path d="M3 17c3-1 4.5-9 6.5-9S10 17 12 17s2.5-4 4-4 1 3 2.5 3H21"/><path d="M3 21h18"/>',
  logout: '<path d="M9.5 21H5.5A1.5 1.5 0 0 1 4 19.5v-15A1.5 1.5 0 0 1 5.5 3h4"/><path d="M16 17l5-5-5-5M21 12H9.5"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5.5a1.5 1.5 0 0 1-1.5 1.5h-12A1.5 1.5 0 0 1 3 19.5v-12A1.5 1.5 0 0 1 4.5 6H10"/>',
  play: '<path d="m7 4.5 13 7.5-13 7.5v-15Z"/>',
  stop: '<rect x="5.5" y="5.5" width="13" height="13" rx="1.5"/>',
  copy: '<rect x="8.5" y="8.5" width="12" height="12" rx="1.5"/><path d="M15.5 8.5V5A1.5 1.5 0 0 0 14 3.5H5A1.5 1.5 0 0 0 3.5 5v9A1.5 1.5 0 0 0 5 15.5h3.5"/>',
  edit: '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4Z"/><path d="m13.5 6.5 4 4"/>',
  wifi: '<path d="M2.5 9a14 14 0 0 1 19 0M5.5 12.5a9.5 9.5 0 0 1 13 0M9 16a4.5 4.5 0 0 1 6 0M12 19.5v.01"/>',
  atom: '<circle cx="12" cy="12" r="1.6"/><ellipse cx="12" cy="12" rx="9.5" ry="4"/><ellipse cx="12" cy="12" rx="9.5" ry="4" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="9.5" ry="4" transform="rotate(120 12 12)"/>',
};

export function icon(name, extra = "") {
  const body = P[name] || P.dot;
  return raw(`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"${extra ? ` ${extra}` : ""}>${body}</svg>`);
}

/** Raw inner paths, for embedding an icon inside a larger SVG at a given position and size. */
export function iconPaths(name) {
  return P[name] || P.dot;
}

/** Brand mark: a hexagonal shield with a lattice core. */
export const brandMark = raw(`<svg class="brand-mark" viewBox="0 0 40 40" aria-hidden="true">
  <path d="M20 2.5 35.2 11.2v17.6L20 37.5 4.8 28.8V11.2Z" fill="#0f1b2d"/>
  <path d="M20 9.5 29.1 14.8v10.4L20 30.5l-9.1-5.3V14.8Z" fill="none" stroke="#8ea0ff" stroke-width="1.6"/>
  <circle cx="20" cy="20" r="3.4" fill="#fff"/>
  <path d="M20 9.5V16.6M29.1 14.8l-6.2 3.6M29.1 25.2l-6.2-3.6M20 30.5v-7.1M10.9 25.2l6.2-3.6M10.9 14.8l6.2 3.6" stroke="#8ea0ff" stroke-width="1.2"/>
</svg>`);
