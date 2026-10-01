// Operator actions: what each action needs, why it may be unavailable, and the confirmation dialog for it.
// Availability shown here is a hint for the operator; the gateway re-checks every precondition and its answer wins.
import { html } from "./lib/html.js";
import { STAGES, failureLabel } from "./lib/copy.js";
import { duration } from "./lib/format.js";
import { openActionModal } from "./components/modal.js";
import { S, abortRecovery, setExpected, startRecovery } from "./store.js";

export const canAct = () => !!(S.me && (S.me.role === "operator" || S.me.role === "admin"));

function ctx(id) {
  const d = S.detail.get(id) || {};
  const t = S.trust.get(id) || {};
  const cur = d.recovery && d.recovery.current;
  const active = !!(cur && cur.status === "active");
  const exp = (d.twin && d.twin.expected) || {};
  return { d, t, cur, active, exp, state: t.state || null };
}

/** { ok, why } for each action on a device. */
export function availability(id) {
  const { t, active, exp, d } = ctx(id);
  const role = canAct() ? null : `Your role (${S.me ? S.me.role : "unknown"}) can view but not act.`;
  const noRec = d.unavailable ? "Recovery is not enabled on this gateway." : null;
  return {
    start: role || noRec ? { ok: false, why: role || noRec }
      : active ? { ok: false, why: "A recovery is already running for this device." }
      : t.state !== "QUARANTINED" ? { ok: false, why: "Recovery can be started only while the device is quarantined." }
      : !(exp.fw_version || exp.cfg_hash) ? { ok: false, why: "Set a known-good state first; recovery restores the device to it." }
      : { ok: true, why: "" },
    abort: role || noRec ? { ok: false, why: role || noRec }
      : !active ? { ok: false, why: "There is no active recovery to abort." }
      : { ok: true, why: "" },
    expected: role ? { ok: false, why: role }
      : active ? { ok: false, why: "The known-good state is locked while a recovery is verifying against it." }
      : { ok: true, why: "" },
  };
}

const REASON = { name: "reason", label: "Reason", type: "textarea", required: true, minLength: 3, maxLength: 200,
  hint: "Recorded in the evidence chain with your operator identity." };

export function openStart(id) {
  const { state, exp } = ctx(id);
  const rc = (S.system && S.system.recovery) || {};
  openActionModal({
    title: "Start recovery", icon: "refresh", tone: "proc", deviceId: id, state,
    intro: "The gateway sends the known-good configuration over the recovery channel. Normal access returns only after health checks pass and trust is rebuilt.",
    context: html`<dt>Restores to</dt><dd class="mono">${exp.cfg_hash || "—"} / ${exp.fw_version || "—"}</dd>
      ${rc.health_checks_required ? html`<dt>Must pass</dt><dd>${rc.health_checks_required} consecutive clean reports within ${duration(rc.deadline_s)}</dd>` : ""}`,
    fields: [{ ...REASON, placeholder: "e.g. Incident contained; restore known-good configuration" }],
    confirmLabel: "Start recovery", busyLabel: "Starting…",
    submit: (v) => startRecovery(id, v.reason),
    describe: (r) => ({ title: "Recovery started",
      text: `${r.recovery_id} is at "${STAGES[r.stage] || r.stage}". Command ${r.command ? r.command.action : "issued"}; the device receives it on its next recovery report. Device state is now ${(S.trust.get(id) || {}).state || "unknown"}.` }),
  });
}

export function openAbort(id) {
  const { state, cur } = ctx(id);
  openActionModal({
    title: "Abort recovery", icon: "stop", tone: "crit", deviceId: id, state,
    intro: "The recovery is marked failed and the device returns to quarantine. Normal access stays blocked.",
    context: cur ? html`<dt>Recovery</dt><dd class="mono">${cur.recovery_id}</dd><dt>Stage</dt><dd>${STAGES[cur.stage] || cur.stage}</dd>` : "",
    fields: [{ ...REASON, placeholder: "e.g. New indicator of compromise" }],
    confirmLabel: "Abort recovery", busyLabel: "Aborting…",
    submit: (v) => abortRecovery(id, v.reason),
    describe: (r) => ({ title: "Recovery aborted",
      text: `${r.recovery_id}: ${failureLabel(r.failure_reason)}. Device state is now ${(S.trust.get(id) || {}).state || "unknown"}.` }),
  });
}

export function openExpected(id) {
  const { state, exp } = ctx(id);
  const kept = [exp.capabilities ? `capabilities (${exp.capabilities.length})` : null, exp.sensor_ranges ? "sensor ranges" : null].filter(Boolean);
  openActionModal({
    title: "Set known-good state", icon: "edit", tone: "proc", deviceId: id, state,
    intro: `The state this device is expected to report. Recovery restores it and health checks compare against it.${kept.length ? ` ${kept.join(" and ")} stay as configured.` : ""}`,
    fields: [
      { name: "fw_version", label: "Firmware version", mono: true, maxLength: 128, value: exp.fw_version || "", placeholder: "e.g. agent-0.1" },
      { name: "cfg_hash", label: "Configuration hash", mono: true, maxLength: 128, value: exp.cfg_hash || "", placeholder: "e.g. cfg-good-1",
        hint: "At least one of firmware version or configuration hash is required." },
    ],
    validate: (v) => (String(v.fw_version || "").trim() || String(v.cfg_hash || "").trim() ? null : { cfg_hash: "Enter a firmware version or a configuration hash." }),
    confirmLabel: "Save known-good state", busyLabel: "Saving…",
    submit: (v) => setExpected(id, { ...exp, fw_version: v.fw_version || null, cfg_hash: v.cfg_hash || null }),
    describe: (r) => ({ title: "Known-good state saved",
      text: `Firmware ${r.expected.fw_version || "not set"}, configuration ${r.expected.cfg_hash || "not set"}. The digital twin now compares against it.` }),
  });
}
