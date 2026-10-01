// Cryptography: where post-quantum protection applies, where it does not, and what it has rejected.
import { html } from "../lib/html.js";
import { bytes, short } from "../lib/format.js";
import { S } from "../store.js";
import { UI } from "../model.js";
import { icon } from "../components/icons.js";
import { banner, empty, loadingPanel } from "../components/states.js";

function count(types) {
  return S.events.filter((e) => types.includes(e.event_type)).length;
}

function lane(y, from, via, to, tone, note) {
  return html`<g transform="translate(0 ${y})">
    <rect class="pq-box" x="0" y="0" width="190" height="44" rx="8"/><text class="pq-t" x="95" y="27" text-anchor="middle">${from}</text>
    <line class="pq-line ${tone}" x1="190" y1="22" x2="590" y2="22"/>
    <rect class="pq-via ${tone}" x="250" y="8" width="280" height="28" rx="14"/><text class="pq-via-t ${tone}" x="390" y="27" text-anchor="middle">${via}</text>
    <rect class="pq-box" x="590" y="0" width="150" height="44" rx="8"/><text class="pq-t" x="665" y="27" text-anchor="middle">${to}</text>
    <text class="pq-note ${tone}" x="760" y="27">${note}</text>
  </g>`;
}

export function render() {
  const head = html`<div class="page-head"><div><h1 class="h-page">Cryptography</h1>
    <p class="lead">Post-quantum protection where Q-SHIELD uses it, and clearly marked where it does not.</p></div></div>`;
  if (!S.loaded || !S.system) return html`${head}${loadingPanel(6)}`;
  const sys = S.system, p = sys.pqc || {}, ev = sys.evidence || {};
  if (!p.enabled) {
    return html`${head}<section class="panel">${empty({ title: "Post-quantum cryptography is disabled on this gateway", text: "Signed observations and the ML-KEM session are off; the evidence chain is hash-linked but unsigned. Set PQC_ENABLED=true and provision keys to turn it on.", iconName: "key" })}</section>`;
  }
  const signers = p.signers || [];
  const signed = S.observations.filter((o) => String(o.auth || "").startsWith("ML-DSA")).length;
  const sealed = S.observations.filter((o) => o.transport === "secure").length;     // recorded by the gateway per observation
  const forged = count(["pqc_invalid_signature", "pqc_malformed_signature", "pqc_handshake_invalid_signature"]);
  const replays = count(["pqc_observation_replay", "pqc_handshake_replay", "pqc_session_replayed_or_reordered_message"]);
  const deviceForgeries = count(["invalid_tag", "replay_or_stale_counter"]);
  const sizes = p.sizes_bytes || {};
  const cards = [
    { name: p.kem_algorithm, role: "Key establishment", line: "Agrees a fresh session key with the vision service. Designed to resist quantum attacks on the key exchange.",
      live: html`Gateway key <span class="mono">${p.gateway_kem_key_id}</span>, fingerprint <span class="mono">${short(p.gateway_kem_fingerprint_sha256, 16)}</span>`, status: "Key online" },
    { name: p.sig_algorithm, role: "Digital signatures", line: "Signs every camera observation and every evidence-chain entry. Forged or replayed observations are rejected.",
      live: html`${signers.map((s) => html`Signer <span class="mono">${s.signer_id}</span> (${s.source}, ${s.status}) `)}${ev.key_id ? html`and evidence key <span class="mono">${ev.key_id}</span>` : ""}`, status: `${signers.filter((s) => s.status === "active").length} signer${signers.length === 1 ? "" : "s"} active` },
    { name: "AES-256-GCM", role: "Session encryption", line: "Encrypts and authenticates observation traffic inside the ML-KEM session, with per-message counters.",
      live: S.observations.length ? `${sealed} of the latest ${S.observations.length} observations arrived encrypted inside an ${p.kem_algorithm} session.`
        : "Part of the session protocol.", status: "Protocol component" },
    { name: "HKDF-SHA256", role: "Key derivation", line: "Derives the session encryption keys from the ML-KEM shared secret.",
      live: "Part of the session protocol.", status: "Protocol component" },
  ];
  const tls = sys.transport === "https";
  return html`${head}
  <div class="grid grid-2">${cards.map((c) => html`<section class="panel pq-card" data-key="pq-${c.name}" data-reveal>
    <div class="panel-body stack-sm">
      <div class="row-between"><span class="caption">${c.role}</span><span class="badge ${c.status.startsWith("Protocol") ? "tone-neutral" : "tone-ok"}">${icon(c.status.startsWith("Protocol") ? "info" : "checkCircle")}${c.status}</span></div>
      <div class="pq-name">${c.name}</div>
      <p class="meta">${c.line}</p>
      <p class="caption">${c.live}</p>
    </div></section>`)}</div>

  <section class="panel section" aria-labelledby="paths-title" data-reveal>
    <div class="panel-head"><h2 class="panel-title" id="paths-title">${icon("link")}Which path is protected by what</h2></div>
    <div class="panel-body">
      <div class="table-wrap"><svg class="pq-paths" viewBox="0 0 1040 236" role="img" aria-label="Vision service to gateway: ML-DSA-65 signatures inside an ML-KEM-768 session, post-quantum. Device to gateway: HMAC-SHA256, not post-quantum. Gateway to evidence chain: ML-DSA-65 signed. Operator browser to gateway: bearer token over ${tls ? "HTTPS" : "plain HTTP"}.">
        ${lane(0, "Vision service (YOLO11n)", `${p.sig_algorithm} inside ${p.kem_algorithm}`, "Gateway", "pq", "Post-quantum")}
        ${lane(62, "Device / ESP32 path", "HMAC-SHA256, pre-shared key", "Gateway", "classic", "Not post-quantum")}
        ${lane(124, "Gateway decisions", `${ev.algorithm || "unsigned"} + SHA-256 chain`, "Evidence chain", ev.signed ? "pq" : "classic", ev.signed ? "Post-quantum signed" : "Unsigned")}
        ${lane(186, "Operator browser", `Bearer token over ${tls ? "HTTPS" : "HTTP"}`, "Gateway", tls ? "classic" : "warn", tls ? "TLS (classical)" : "Cleartext: trusted LAN only")}
      </svg></div>
      ${!tls ? html`<div style="margin-top:12px">${banner("warn", "alert", "This dashboard is connected over plain HTTP.", "Operator tokens cross the network in cleartext. Start the gateway with QSHIELD_TLS_CERT and QSHIELD_TLS_KEY for HTTPS.")}</div>` : ""}
    </div>
  </section>

  <div class="grid grid-3 section" data-reveal>
    <section class="panel"><div class="panel-body"><div class="caption">Signed observations accepted</div><div class="pq-stat">${signed}</div><p class="caption">${p.sig_algorithm} verified, in the latest ${S.observations.length} observations; ${sealed} of them inside an ${p.kem_algorithm} session</p></div></section>
    <section class="panel"><div class="panel-body"><div class="caption">Forged signatures rejected</div><div class="pq-stat">${forged}</div><p class="caption">Rejected at the gateway; they add only bounded attack pressure to trust</p></div></section>
    <section class="panel"><div class="panel-body"><div class="caption">Replays rejected</div><div class="pq-stat">${replays}</div><p class="caption">Observation, handshake and session replays${deviceForgeries ? `; plus ${deviceForgeries} forged or replayed device message${deviceForgeries === 1 ? "" : "s"}` : ""}</p></div></section>
  </div>

  <section class="panel section" data-reveal>
    <div class="panel-head"><h2 class="panel-title">${icon("info")}Technical details</h2>
      <button class="btn sm ghost" type="button" data-action="toggle" data-id="pq-tech" aria-expanded="${UI.expanded.has("pq-tech")}" aria-controls="pq-tech">${UI.expanded.has("pq-tech") ? "Hide" : "Show"}</button></div>
    <div class="panel-body" id="pq-tech" ${UI.expanded.has("pq-tech") ? "" : "hidden"}>${UI.expanded.has("pq-tech") ? html`<dl class="kv">
      <dt>Library</dt><dd>${p.library} ${p.library_version}</dd>
      <dt>${p.kem_algorithm} sizes</dt><dd>public key ${bytes(sizes.kem_public_key)}, ciphertext ${bytes(sizes.kem_ciphertext)}, shared secret ${bytes(sizes.kem_shared_secret)}</dd>
      <dt>${p.sig_algorithm} sizes</dt><dd>public key ${bytes(sizes.sig_public_key)}, signature ${bytes(sizes.signature)}</dd>
      <dt>Gateway KEM fingerprint</dt><dd class="mono" style="overflow-wrap:anywhere">${p.gateway_kem_fingerprint_sha256}</dd>
      <dt>Evidence chain</dt><dd>${ev.hash} linked, ${ev.signed ? `${ev.algorithm} signed with ${ev.key_id}` : "unsigned"}</dd>
      <dt>Operator transport</dt><dd>${tls ? "HTTPS" : "HTTP (cleartext)"}${sys.operator_auth && sys.operator_auth.shared_token_enabled ? "; shared bootstrap token enabled" : ""}</dd>
      <dt>Limits</dt><dd>The ML-KEM session protocol has had no external review. The ESP32 firmware path uses HMAC-SHA256 only. The webcam itself has no cryptographic identity; the vision service holds the signing key.</dd>
    </dl>` : ""}</div>
  </section>`;
}
