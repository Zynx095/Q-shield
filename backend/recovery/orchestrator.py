"""Recovery orchestrator: drives QUARANTINED -> RECOVERING -> VERIFIED -> RECOVERED -> TRUSTED (Phase 7, TD-10).

"Self-healing" here means SOFTWARE-CONTROLLED REMEDIATION AND TRUST RESTORATION, nothing more:
  1. operator (control channel) starts recovery of a QUARANTINED, non-revoked device that has a defined expected
     (known-good) state in the digital twin;
  2. the orchestrator moves it to RECOVERING and issues a remediation command: "apply known-good configuration"
     (target cfg_hash / fw_version from the twin). It is delivered in the response to the device's next
     authenticated recovery-channel report. It cannot repair hardware and cannot reflash firmware;
  3. the device must acknowledge the command in a later authenticated report;
  4. health checks: N consecutive authenticated recovery reports after the acknowledgement, each judged on its own
     content: tamper=false and every expected field reported and matching (firmware, config, sensor ranges;
     capabilities from the last authenticated registration);
  5. VERIFIED (explicit, validated transition with the check evidence);
  6. trust ramp: fresh authenticated evidence credits time; RECOVERED once score >= 50 (normal access restored);
  7. TRUSTED once score >= 85 -> recovery completed.

Failure paths (fail closed, all recorded):
  * an authenticated fault report during RECOVERING/VERIFIED -> the trust engine itself returns the device to
    QUARANTINED (Phase 4.1 recovery_fault); the orchestrator marks the recovery failed;
  * a twin mismatch in a report is also an authenticated integrity/sensor fault -> same path;
  * deadline exceeded before VERIFIED, or trust ramp not completed in time -> explicit QUARANTINED;
  * revoked credential -> QUARANTINED, recovery failed (re-enrolment only);
  * insufficient evidence (device silent, fields not reported) -> HOLD until the deadline.
The device's self-reported state is evidence, not attestation (TD-10): a compromised device can lie its way through
these checks. That limitation is documented, not hidden.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from backend.devices.store import Store
from backend.trust.model import IllegalTransition, State
from backend.twin.twin import MATCH, DigitalTwin

SCHEMA = """
CREATE TABLE IF NOT EXISTS recoveries (
    recovery_id  TEXT PRIMARY KEY,
    device_id    TEXT NOT NULL,
    status       TEXT NOT NULL,
    stage        TEXT NOT NULL,
    started_at   REAL NOT NULL,
    deadline     REAL NOT NULL,
    ramp_deadline REAL,
    updated_at   REAL NOT NULL,
    last_msg_id  INTEGER NOT NULL DEFAULT 0,
    body         TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_recoveries_dev ON recoveries(device_id, started_at);
"""

ACTIVE = "active"
STAGES = ("remediation_pending", "health_checks", "trust_ramp", "restoring")


class RecoveryError(ValueError):
    pass


@dataclass(frozen=True)
class RecoveryConfig:
    health_checks_required: int = 3
    deadline_s: float = 900.0          # remediation + health checks must pass within this (gateway clock)
    ramp_timeout_s: float = 7200.0     # VERIFIED -> TRUSTED trust rebuild must finish within this


class RecoveryOrchestrator:
    def __init__(self, store: Store, trust, twin: DigitalTwin, clock: Callable[[], float] = time.time,
                 recorder=None, cfg: RecoveryConfig | None = None):
        self.store, self.trust, self.twin, self.clock = store, trust, twin, clock
        self.recorder, self.cfg = recorder, cfg or RecoveryConfig()
        self._lock = threading.RLock()   # tick() runs from requests AND the background RecoveryTimer
        store.ensure_schema(SCHEMA)

    # ------------------------------------------------------------------ persistence
    def _load(self, row) -> dict:
        d = {k: row[k] for k in row.keys() if k != "body"}
        d.update(json.loads(row["body"]))
        return d

    def _save(self, r: dict) -> None:
        body = {k: v for k, v in r.items() if k not in ("recovery_id", "device_id", "status", "stage", "started_at",
                                                         "deadline", "ramp_deadline", "updated_at", "last_msg_id")}
        self.store.execute(
            "INSERT OR REPLACE INTO recoveries(recovery_id, device_id, status, stage, started_at, deadline, ramp_deadline,"
            " updated_at, last_msg_id, body) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (r["recovery_id"], r["device_id"], r["status"], r["stage"], r["started_at"], r["deadline"], r.get("ramp_deadline"),
             r["updated_at"], r["last_msg_id"], json.dumps(body)))

    def active(self, device_id: str) -> dict | None:
        rows = self.store.query("SELECT * FROM recoveries WHERE device_id=? AND status=? ORDER BY started_at DESC LIMIT 1",
                                (device_id, ACTIVE))
        return self._load(rows[0]) if rows else None

    def latest(self, device_id: str) -> dict | None:
        rows = self.store.query("SELECT * FROM recoveries WHERE device_id=? ORDER BY started_at DESC, rowid DESC LIMIT 1",
                                (device_id,))
        return self._load(rows[0]) if rows else None

    def history(self, device_id: str) -> list[dict]:
        rows = self.store.query("SELECT * FROM recoveries WHERE device_id=? ORDER BY started_at, rowid", (device_id,))
        return [self._load(r) for r in rows]

    # ------------------------------------------------------------------ records
    def _log(self, r: dict, event: str, now: float, **detail) -> None:
        r.setdefault("log", []).append({"t": now, "event": event, **detail})
        severity = "high" if event in ("recovery_failed",) else "medium"
        if event in ("recovery_started", "recovery_failed", "recovery_verified", "recovery_completed"):
            self.store.add_event(now, r["device_id"], event, severity, {"recovery_id": r["recovery_id"], **detail})
        if self.recorder is not None:
            self.recorder.record(event, {"recovery_id": r["recovery_id"], "stage": r["stage"], **detail}, ts=now,
                                 device_id=r["device_id"], source="recovery_orchestrator",
                                 trust_state=self._state_str(r["device_id"]), trust_score=self.trust.score_of(r["device_id"]))

    def _state_str(self, device_id: str) -> str | None:
        dt = self.trust.engine.devices.get(device_id)
        return dt.state.value if dt is not None and dt.state else None

    def _transition(self, r: dict, target: State, reason: str) -> bool:
        try:
            self.trust.request_transition(r["device_id"], target, reason, f"recovery:{r['recovery_id']}")
            return True
        except IllegalTransition as e:
            r.setdefault("log", []).append({"t": self.clock(), "event": "transition_refused", "target": target.value,
                                            "reason": str(e)})
            return False

    def _fail(self, r: dict, reason: str, now: float, force_quarantine: bool) -> None:
        if force_quarantine and self.trust.state_of(r["device_id"]) is not State.QUARANTINED:
            self._transition(r, State.QUARANTINED, f"recovery failed: {reason}")
        r["status"], r["failure_reason"], r["updated_at"] = "failed", reason, now
        self._log(r, "recovery_failed", now, reason=reason)
        self._save(r)

    # ------------------------------------------------------------------ control channel
    def start(self, device_id: str, reason: str, requested_by: str = "operator") -> dict:
        with self._lock:
            return self._start(device_id, reason, requested_by)

    def _start(self, device_id: str, reason: str, requested_by: str) -> dict:
        now = self.clock()
        dev = self.store.get_device(device_id)
        if dev is None:
            raise RecoveryError("unknown_device")
        if dev.revoked:
            raise RecoveryError("device_revoked: re-enrolment required")
        if not reason:
            raise RecoveryError("a reason is required")
        if self.active(device_id):
            raise RecoveryError("recovery_already_active")
        if self.trust.state_of(device_id) is not State.QUARANTINED:
            raise RecoveryError("device_not_quarantined")
        exp = self.twin.expected(device_id)
        if not (exp.get("cfg_hash") or exp.get("fw_version")):
            raise RecoveryError("no_expected_state: set the digital-twin expected state first")
        rid = f"REC-{uuid.uuid4().hex[:12]}"
        cursor = self.store.query("SELECT COALESCE(MAX(id),0) AS m FROM device_messages WHERE device_id=?", (device_id,))[0]["m"]
        r = {"recovery_id": rid, "device_id": device_id, "status": ACTIVE, "stage": "remediation_pending",
             "started_at": now, "deadline": now + self.cfg.deadline_s, "ramp_deadline": None, "updated_at": now,
             "last_msg_id": cursor, "reason": reason, "requested_by": requested_by, "health": [], "log": [],
             "command": {"command_id": f"CMD-{uuid.uuid4().hex[:10]}", "action": "apply_known_good_config",
                         "cfg_hash": exp.get("cfg_hash"), "fw_version": exp.get("fw_version"),
                         "note": "software configuration remediation; firmware is checked, not reflashed"},
             "command_acked": False, "consecutive_clean": 0}
        if not self._transition(r, State.RECOVERING, f"recovery started: {reason}"):
            raise RecoveryError("transition to RECOVERING refused")
        self._log(r, "recovery_started", now, reason=reason, requested_by=requested_by, command=r["command"])
        self._save(r)
        return r

    def abort(self, device_id: str, reason: str) -> dict:
        with self._lock:
            r = self.active(device_id)
            if r is None:
                raise RecoveryError("no_active_recovery")
            self._fail(r, f"aborted: {reason}", self.clock(), force_quarantine=True)
            return r

    # ------------------------------------------------------------------ recovery channel
    def pending_command(self, device_id: str) -> dict | None:
        r = self.active(device_id)
        if r and r["stage"] == "remediation_pending" and not r["command_acked"]:
            return r["command"]
        return None

    # ------------------------------------------------------------------ evaluation
    def tick(self) -> list[dict]:
        """Advance every active recovery. Deterministic given the stored records and the clock."""
        out = []
        with self._lock:
            for row in self.store.query("SELECT * FROM recoveries WHERE status=?", (ACTIVE,)):
                r = self._load(row)
                self._advance(r, self.clock())
                out.append(r)
        return out

    def _new_reports(self, r: dict) -> list:
        rows = self.store.query("SELECT id, payload FROM device_messages WHERE device_id=? AND kind='recovery' AND id>? ORDER BY id",
                                (r["device_id"], r["last_msg_id"]))
        return rows

    def _advance(self, r: dict, now: float) -> None:
        dev = self.store.get_device(r["device_id"])
        state = self.trust.state_of(r["device_id"])
        if dev is None or dev.revoked:
            return self._fail(r, "credential_revoked", now, force_quarantine=False)
        if state is State.QUARANTINED:
            return self._fail(r, "fault_reported_during_recovery (trust engine returned the device to QUARANTINED)", now,
                              force_quarantine=False)

        if r["stage"] in ("remediation_pending", "health_checks"):
            for row in self._new_reports(r):
                r["last_msg_id"] = row["id"]
                rep = json.loads(row["payload"] or "{}")
                if r["stage"] == "remediation_pending":
                    if rep.get("ack_command_id") == r["command"]["command_id"]:
                        r["command_acked"], r["stage"] = True, "health_checks"
                        self._log(r, "remediation_acknowledged", now, msg_id=row["id"])
                    continue
                # Judge THIS report on what it says (not the twin's accumulated state, which keeps the last value
                # ever reported for a field and would let a device pass on configuration it reported before the
                # incident, or let several reports consumed in one tick all borrow the newest one).
                cmp = self.twin.compare_report(r["device_id"], rep)
                clean = rep.get("tamper") is False and cmp.overall == MATCH
                r["consecutive_clean"] = r["consecutive_clean"] + 1 if clean else 0
                r["health"].append({"msg_id": row["id"], "t": now, "tamper": rep.get("tamper"), "twin": cmp.overall,
                                    "fields": {k: v["status"] for k, v in cmp.fields.items()}, "clean": clean})
            state = self.trust.state_of(r["device_id"])       # a report just consumed may have tripped a fault
            if state is State.QUARANTINED:
                return self._fail(r, "fault_reported_during_recovery (trust engine returned the device to QUARANTINED)",
                                  now, force_quarantine=False)
            if r["stage"] == "health_checks" and r["consecutive_clean"] >= self.cfg.health_checks_required:
                if self._transition(r, State.VERIFIED, f"{r['consecutive_clean']} consecutive clean authenticated reports"):
                    r["stage"], r["ramp_deadline"] = "trust_ramp", now + self.cfg.ramp_timeout_s
                    self._log(r, "recovery_verified", now, checks=r["health"][-self.cfg.health_checks_required:])
            elif now > r["deadline"]:
                return self._fail(r, "deadline_exceeded_before_verification", now, force_quarantine=True)

        if r["stage"] == "trust_ramp":
            score = self.trust.score_of(r["device_id"]) or 0
            if score >= self.trust.cfg.quarantine_below and self._transition(r, State.RECOVERED, f"trust rebuilt to {score}"):
                r["stage"] = "restoring"
                self._log(r, "access_restored", now, score=score)
            elif r["ramp_deadline"] and now > r["ramp_deadline"]:
                return self._fail(r, "trust_ramp_timeout", now, force_quarantine=True)

        if r["stage"] == "restoring":
            score = self.trust.score_of(r["device_id"]) or 0
            if score >= self.trust.cfg.trusted_reentry_min and self._transition(r, State.TRUSTED, f"trust rebuilt to {score}"):
                r["status"] = "completed"
                self._log(r, "recovery_completed", now, score=score)
            elif r["ramp_deadline"] and now > r["ramp_deadline"]:
                return self._fail(r, "trust_ramp_timeout", now, force_quarantine=True)

        r["updated_at"] = now
        self._save(r)


class RecoveryTimer:
    """Background clock for recovery deadlines. Without it, deadlines are only evaluated when the gateway handles a
    request, so a silent device in RECOVERING would never time out. Every `interval_s` it runs
    trust.process_pending() + recovery.tick(); errors are recorded as events and never stop the timer."""

    def __init__(self, recovery: RecoveryOrchestrator, interval_s: float = 5.0, on_error: Callable | None = None):
        if interval_s <= 0:
            raise ValueError("interval_s must be > 0")
        self.recovery, self.interval_s, self.on_error = recovery, interval_s, on_error
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.ticks = 0

    def run_once(self) -> None:
        try:
            self.recovery.trust.process_pending()
            self.recovery.tick()
        except Exception as e:  # noqa: BLE001 - the timer must survive a bad tick
            if self.on_error:
                self.on_error(e)
        self.ticks += 1

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            self.run_once()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="qshield-recovery-timer", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)
            self._thread = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())
