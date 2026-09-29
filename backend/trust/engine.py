"""Deterministic, explainable trust engine (pure logic; no I/O, no ML, no crypto).

Implements docs/architecture/trust-engine.md. The score is a pure function of the ordered signal history, the
configuration and the evaluation time. Every change is attributed exactly: the reasons sum to the exact score delta.

    raw      = 100 - sum_{i in available} (w_i / W) * p_i
    uncapped = clamp(raw - pressure, 0, 100)
    final    = min(uncapped, active caps);   score = round_half_up(final)
"""
from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from backend.trust import state_machine as sm
from backend.trust.config import SEVERITY_POINTS, TrustConfig
from backend.trust.model import (
    Auth, Factor, IllegalTransition, Kind, Reason, Signal, SignalRejected, State, TrustChange,
)

EPS = 1e-9
PERSISTENT = [f.value for f in Factor if f is not Factor.NETWORK]
_MODALITY_OF = {Kind.PHYSICAL_TAMPER: "PHYSICAL", Kind.SENSOR_OUT_OF_RANGE: "SENSOR", Kind.VISUAL_RULE_VIOLATION: "VISUAL"}


def _round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


@dataclass
class Comp:
    """A computed (published) score with all its components."""
    raw: float = 100.0
    pressure: float = 0.0
    p: dict = field(default_factory=dict)          # available factor -> penalty (network: staleness penalty)
    w: dict = field(default_factory=dict)          # available factor -> effective (renormalised) weight
    coverage: float = 0.0
    unavailable: list = field(default_factory=list)
    uncapped: float = 100.0
    caps: list = field(default_factory=list)       # [(name, ceiling)]
    final: float = 100.0

    def to_dict(self) -> dict:
        return {"raw": self.raw, "pressure": self.pressure, "p": self.p, "w": self.w, "coverage": self.coverage,
                "unavailable": self.unavailable, "uncapped": self.uncapped, "caps": [list(c) for c in self.caps], "final": self.final}

    @classmethod
    def from_dict(cls, d: dict) -> "Comp":
        return cls(d["raw"], d["pressure"], dict(d["p"]), dict(d["w"]), d["coverage"], list(d["unavailable"]),
                   d["uncapped"], [tuple(c) for c in d["caps"]], d["final"])


@dataclass
class DeviceTrust:
    device_id: str
    started: bool = False
    available: set = field(default_factory=set)
    penalties: dict = field(default_factory=lambda: {f: 0.0 for f in PERSISTENT})
    pressure: float = 0.0
    credit_clock: float = 0.0
    last_device_evidence_ts: float | None = None
    last_violation_ts: float | None = None
    last_ts: float = 0.0                 # engine time: last signal OR time-driven evaluation (never moves back)
    last_signal_ts: float = 0.0          # receipt time of the newest applied signal (defines 'out of order')
    holds: dict = field(default_factory=dict)
    tamper_active: bool = False
    sensor_active: bool = False
    integrity_mismatch: bool = False
    modality_last: dict = field(default_factory=dict)        # modality -> (timestamp, signal_id)
    episodes: dict = field(default_factory=dict)             # key -> {"last": ts, "applied": points}
    replay_times: list = field(default_factory=list)
    seen: OrderedDict = field(default_factory=OrderedDict)
    state: State | None = None
    score: int | None = None
    score_exact: float | None = None
    revoked: bool = False
    seq: int = 0
    incident_seq: int = 0
    incident: dict | None = None
    provenance: dict = field(default_factory=dict)
    duplicates: int = 0
    recovery_fault: bool = False
    last_comp: Comp = field(default_factory=Comp)

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id, "started": self.started, "available": sorted(self.available), "penalties": self.penalties,
            "pressure": self.pressure, "credit_clock": self.credit_clock, "last_device_evidence_ts": self.last_device_evidence_ts,
            "last_violation_ts": self.last_violation_ts, "last_ts": self.last_ts, "last_signal_ts": self.last_signal_ts, "holds": self.holds,
            "tamper_active": self.tamper_active, "sensor_active": self.sensor_active, "integrity_mismatch": self.integrity_mismatch,
            "modality_last": {k: list(v) for k, v in self.modality_last.items()}, "episodes": self.episodes,
            "replay_times": self.replay_times, "seen": list(self.seen), "state": self.state.value if self.state else None,
            "score": self.score, "score_exact": self.score_exact, "revoked": self.revoked, "seq": self.seq,
            "incident_seq": self.incident_seq, "incident": self.incident, "provenance": self.provenance,
            "duplicates": self.duplicates, "recovery_fault": self.recovery_fault, "last_comp": self.last_comp.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DeviceTrust":
        dt = cls(d["device_id"])
        dt.started, dt.available = d["started"], set(d["available"])
        dt.penalties = {f: float(d["penalties"].get(f, 0.0)) for f in PERSISTENT}
        dt.pressure, dt.credit_clock = d["pressure"], d["credit_clock"]
        dt.last_device_evidence_ts, dt.last_violation_ts, dt.last_ts = d["last_device_evidence_ts"], d["last_violation_ts"], d["last_ts"]
        dt.last_signal_ts = d.get("last_signal_ts", d["last_ts"])
        dt.holds, dt.tamper_active, dt.sensor_active = dict(d["holds"]), d["tamper_active"], d["sensor_active"]
        dt.integrity_mismatch = d["integrity_mismatch"]
        dt.modality_last = {k: (v[0], v[1]) for k, v in d["modality_last"].items()}
        dt.episodes, dt.replay_times = dict(d["episodes"]), list(d["replay_times"])
        dt.seen = OrderedDict((s, None) for s in d["seen"])
        dt.state = State(d["state"]) if d["state"] else None
        dt.score, dt.score_exact, dt.revoked, dt.seq = d["score"], d["score_exact"], d["revoked"], d["seq"]
        dt.incident_seq, dt.incident, dt.provenance, dt.duplicates = d["incident_seq"], d["incident"], dict(d["provenance"]), d["duplicates"]
        dt.recovery_fault = bool(d.get("recovery_fault", False))
        dt.last_comp = Comp.from_dict(d["last_comp"])
        return dt


@dataclass
class _Stages:
    p0: dict
    p1: dict
    p2: dict
    q0: float
    q1: float
    q2: float
    credited: float = 0.0


class TrustEngine:
    def __init__(self, cfg: TrustConfig | None = None):
        self.cfg = (cfg or TrustConfig()).validate()
        self.devices: dict[str, DeviceTrust] = {}
        self._diag: list[dict] = []

    # ------------------------------------------------------------------ bookkeeping
    def track(self, device_id: str) -> DeviceTrust:
        return self.devices.setdefault(device_id, DeviceTrust(device_id))

    def pop_diagnostics(self) -> list[dict]:
        d, self._diag = self._diag, []
        return d

    def _note(self, sig: Signal | None, reason: str, **detail) -> None:
        self._diag.append({"device_id": sig.device_id if sig else None, "signal_id": sig.signal_id if sig else None,
                           "kind": sig.kind.value if sig else None, "reason": reason, **detail})

    def export_state(self) -> dict:
        return {k: v.to_dict() for k, v in self.devices.items()}

    def import_state(self, data: dict) -> None:
        self.devices = {k: DeviceTrust.from_dict(v) for k, v in data.items()}

    # ------------------------------------------------------------------ score computation (pure)
    def _network_p(self, dt: DeviceTrust, now: float) -> float:
        if dt.last_device_evidence_ts is None:
            return 0.0
        a = max(0.0, now - dt.last_device_evidence_ts)
        c = self.cfg
        if a <= c.offline_timeout_s:
            return 0.0
        return 100.0 * min(1.0, (a - c.offline_timeout_s) / (c.stale_full_s - c.offline_timeout_s))

    def _active_caps(self, dt: DeviceTrust, now: float) -> list:
        caps, out = self.cfg.caps, []

        def add(name):
            out.append((name, caps[name][0]))

        held = lambda n: dt.holds.get(n, -1.0) > dt.credit_clock  # noqa: E731
        if dt.revoked:
            add("revoked_device")
        if held("confirmed_incident"):
            add("confirmed_incident")
        if dt.tamper_active or held("physical_tamper"):
            add("physical_tamper")
        if held("correlated_incident"):
            add("correlated_incident")
        if held("repeated_replay"):
            add("repeated_replay")
        if dt.integrity_mismatch:
            add("integrity_mismatch")
        if held("auth_violation"):
            add("auth_violation")
        if dt.last_device_evidence_ts is not None and now - dt.last_device_evidence_ts > self.cfg.stale_cap_after_s:
            add("stale_device")
        return out

    def _compute(self, dt: DeviceTrust, now: float) -> Comp:
        cfg = self.cfg
        avail = [f for f in Factor if f.value in dt.available]
        W = sum(cfg.weights[f] for f in avail) or 1.0
        p, w = {}, {}
        for f in avail:
            w[f.value] = cfg.weights[f] / W
            p[f.value] = self._network_p(dt, now) if f is Factor.NETWORK else dt.penalties.get(f.value, 0.0)
        raw = 100.0 - sum(w[k] * p[k] for k in p)
        uncapped = min(100.0, max(0.0, raw - dt.pressure))
        caps = self._active_caps(dt, now)
        final = min([uncapped] + [c for _, c in caps])
        return Comp(raw, dt.pressure, p, w, W if avail else 0.0, [f.value for f in Factor if f.value not in dt.available],
                    uncapped, caps, final)

    # ------------------------------------------------------------------ attribution (exact)
    def _attribute(self, b: Comp, a: Comp, s: _Stages, trig: str | None, trig_detail: dict, trig_factor: str | None) -> list[Reason]:
        R: list[Reason] = []

        def add(signal, impact, factor=None, **detail):
            if abs(impact) > 1e-12:
                R.append(Reason(signal, impact, factor, detail))

        for f, wa in a.w.items():
            if f == Factor.NETWORK.value:
                continue
            add("healthy_evidence_recovery", -(wa * (s.p1[f] - s.p0[f])), f, credited_s=round(s.credited, 6))
            add(trig or "signal", -(wa * (s.p2[f] - s.p1[f])), f, **trig_detail)
        if Factor.NETWORK.value in a.w:
            add("network_liveness", -(a.w[Factor.NETWORK.value] * (a.p[Factor.NETWORK.value] - b.p.get(Factor.NETWORK.value, 0.0))),
                Factor.NETWORK.value)
        add("healthy_evidence_recovery", -(s.q1 - s.q0), "pressure", credited_s=round(s.credited, 6))
        add(trig or "signal", -(s.q2 - s.q1), "pressure", **trig_detail)
        add("coverage_change", -sum((a.w.get(f, 0.0) - wb) * b.p.get(f, 0.0) for f, wb in b.w.items()))
        d_unclamped = (a.raw - a.pressure) - (b.raw - b.pressure)
        add("bounds", (a.uncapped - b.uncapped) - d_unclamped)
        cap_a, cap_b = a.final - a.uncapped, b.final - b.uncapped
        if abs(cap_a - cap_b) > 1e-12:
            src = a.caps if a.caps and cap_a < -1e-12 else b.caps
            name = min(src, key=lambda c: c[1])[0] if src else "cap"
            add(f"cap:{name}", cap_a - cap_b)
        residual = (a.final - b.final) - sum(r.impact for r in R)
        if abs(residual) > 1e-6:                                # fail-safe: never leave a change unexplained
            add("unattributed_residual", residual)
        R.sort(key=lambda r: (-abs(r.impact), r.signal, r.factor or ""))
        return R

    # ------------------------------------------------------------------ change emission
    def _publish(self, dt: DeviceTrust, before: Comp, after: Comp, stages: _Stages, ts: float, triggers: tuple,
                 trig: str | None, trig_detail: dict, trig_factor: str | None, kind: str,
                 incident_new: dict | None) -> TrustChange | None:
        score = _round_half_up(after.final)
        new_state = sm.automatic_state(self.cfg, dt.state, score, dt.revoked, dt.recovery_fault)
        sm.assert_legal(dt.state, new_state)
        if new_state != dt.state:
            dt.recovery_fault = False
        prev_state, prev_exact = dt.state, before.final
        prev_score = dt.score if dt.score is not None else _round_half_up(before.final)
        caps_before = {c for c, _ in before.caps}
        caps_after = {c for c, _ in after.caps}
        material = (score != prev_score or new_state != prev_state or caps_before != caps_after
                    or incident_new is not None or not dt.started)
        # Routine clean evidence / time passing only emits an event when it changes the published score, state or caps;
        # sub-point decay is tracked exactly in the state but is not an event.
        scored_trigger = trig not in (None, Kind.DEVICE_EVIDENCE.value) and abs(after.final - before.final) > EPS
        if not (material or scored_trigger):
            dt.last_comp, dt.score_exact = after, after.final
            return None
        reasons = self._attribute(before, after, stages, trig, trig_detail, trig_factor)
        dt.seq += 1
        first = not dt.started
        dt.started = True
        dt.state, dt.score, dt.score_exact, dt.last_comp = new_state, score, after.final, after
        return TrustChange(
            event_id=f"TC-{dt.device_id}-{dt.seq}", device_id=dt.device_id, timestamp=ts, previous_score=prev_score, new_score=score,
            delta=score - prev_score, previous_exact=prev_exact, new_exact=after.final, previous_state=prev_state, new_state=new_state,
            trigger_signals=triggers, reasons=tuple(reasons), caps_active=tuple(sorted(caps_after)), incident=incident_new,
            coverage=after.coverage, unavailable=tuple(after.unavailable), kind="created" if first else kind)

    # ------------------------------------------------------------------ time-driven evaluation
    def evaluate(self, device_id: str, now: float) -> list[TrustChange]:
        dt = self.devices.get(device_id)
        if dt is None or not dt.started:
            return []
        now = max(now, dt.last_ts)
        out = self._advance(dt, now)
        return out

    def _advance(self, dt: DeviceTrust, now: float) -> list[TrustChange]:
        if not dt.started:
            dt.last_ts = max(dt.last_ts, now)
            return []
        before = dt.last_comp
        after = self._compute(dt, now)
        dt.last_ts = max(dt.last_ts, now)
        st = _Stages(dict(dt.penalties), dict(dt.penalties), dict(dt.penalties), dt.pressure, dt.pressure, dt.pressure)
        c = self._publish(dt, before, after, st, now, (), None, {}, None, "time_driven", None)
        return [c] if c else []

    # ------------------------------------------------------------------ signals
    def apply(self, sig: Signal) -> list[TrustChange]:
        """Apply one signal. Returns 0-2 changes (a time-driven one first, then the signal-driven one).
        Raises SignalRejected for invalid input: a rejected signal never changes a score."""
        sig.validate()
        dt = self.devices.get(sig.device_id)
        if dt is None:
            raise SignalRejected("unknown_device", sig.device_id)
        if sig.signal_id in dt.seen:
            dt.duplicates += 1
            self._note(sig, "duplicate_signal_ignored")
            return []
        dt.seen[sig.signal_id] = None
        while len(dt.seen) > self.cfg.max_seen_ids:
            dt.seen.popitem(last=False)

        receipt = sig.timestamp
        # Out of order = older than a signal already applied. A time-driven evaluation that ran between this record's
        # receipt and its processing (enforcement check, dashboard poll) does NOT make it out of order; it is still
        # processed at the engine's current time so published time never moves backwards (Phase 11 finding).
        out_of_order = receipt < dt.last_signal_ts
        if out_of_order:
            self._note(sig, "out_of_order_signal_processed_at_latest_time")
        ts = max(receipt, dt.last_ts)
        changes = self._advance(dt, ts)
        before = dt.last_comp if dt.started else Comp()
        dt.available.add(Factor.IDENTITY.value)                       # a record starts at the first accepted signal

        p0, q0 = dict(dt.penalties), dt.pressure
        credited = self._recover(dt, sig, receipt, out_of_order)
        p1, q1 = dict(dt.penalties), dt.pressure
        trig_detail: dict[str, Any] = {"authenticity": sig.auth.value, "source_ref": sig.source_ref}
        if sig.confidence is not None:
            trig_detail["confidence"] = sig.confidence
        if sig.provenance:
            trig_detail["provenance"] = sig.provenance
        trig_factor = self._handle(dt, sig, ts, trig_detail)
        if dt.state in (State.RECOVERING, State.VERIFIED) and self._violation_report(sig):
            dt.recovery_fault = True                      # remediation failed / not effective: fail closed
        incident_new = self._update_incident(dt, sig, ts)
        after = self._compute(dt, ts)
        st = _Stages(p0, p1, dict(dt.penalties), q0, q1, dt.pressure, credited)
        c = self._publish(dt, before, after, st, ts, (sig.signal_id,), sig.kind.value, trig_detail, trig_factor,
                          "score_change", incident_new)
        dt.last_ts = ts
        dt.last_signal_ts = max(dt.last_signal_ts, receipt)
        if c:
            changes.append(c)
        return changes

    def _violation_report(self, sig: Signal) -> bool:
        """An authenticated report that a fault condition is (still/again) present. Unauthenticated pressure and
        token-only observations never count: they must not be able to knock a device out of recovery."""
        k = sig.kind
        if k is Kind.PHYSICAL_TAMPER:
            return bool(sig.value["active"])
        if k is Kind.SENSOR_OUT_OF_RANGE:
            return bool(sig.value["active"])
        if k is Kind.INTEGRITY_MISMATCH:
            return bool(sig.value["mismatch"])
        if k in (Kind.AUTH_MISBEHAVIOR, Kind.MALFORMED_PAYLOAD):
            return True
        if k is Kind.VISUAL_RULE_VIOLATION:
            return sig.auth is Auth.SIGNER_MLDSA and sig.confidence >= self.cfg.confidence_floor
        if k in (Kind.CAMERA_OBSTRUCTED, Kind.CAMERA_SOURCE_LOST):
            return sig.auth is Auth.SIGNER_MLDSA
        return False

    def _recover(self, dt: DeviceTrust, sig: Signal, ts: float, out_of_order: bool) -> float:
        """Credit time and decay penalties. Only clean, authenticated DEVICE evidence credits time.
        `ts` is the record's gateway receipt time."""
        if sig.kind is not Kind.DEVICE_EVIDENCE or out_of_order:
            return 0.0
        prev = dt.last_device_evidence_ts
        if prev is None:
            return 0.0
        start = max(prev, dt.last_violation_ts) if dt.last_violation_ts is not None else prev
        credit = min(max(0.0, ts - start), self.cfg.credit_cap_s)
        if credit <= 0:
            return 0.0
        dt.credit_clock += credit
        blocked = {Factor.PHYSICAL.value: dt.tamper_active, Factor.SENSOR.value: dt.sensor_active,
                   Factor.CONFIG.value: dt.integrity_mismatch}
        for f, h in ((f.value, h) for f, h in self.cfg.half_life_s.items()):
            if blocked.get(f):
                continue                                              # an active episode does not heal
            v = dt.penalties[f] * 2.0 ** (-credit / h)
            dt.penalties[f] = 0.0 if v < 1e-9 else v
        v = dt.pressure * 2.0 ** (-credit / self.cfg.pressure_half_life_s)
        dt.pressure = 0.0 if v < 1e-9 else v
        return credit

    def _add_penalty(self, dt: DeviceTrust, factor: str, points: float) -> None:
        dt.penalties[factor] = min(100.0, dt.penalties[factor] + points)

    def _episode(self, dt: DeviceTrust, key: str, impact: float, ts: float) -> float:
        """Points to add for this observation given the episode maximum already applied."""
        ep = dt.episodes.get(key)
        if ep and ts - ep["last"] <= self.cfg.episode_gap_s:
            add = max(0.0, impact - ep["applied"])
            ep["applied"] = max(ep["applied"], impact)
            ep["last"] = ts
        else:
            add = impact
            dt.episodes[key] = {"last": ts, "applied": impact}
        return add

    def _hold(self, dt: DeviceTrust, cap: str) -> None:
        dt.holds[cap] = dt.credit_clock + self.cfg.caps[cap][1]

    def _handle(self, dt: DeviceTrust, sig: Signal, ts: float, detail: dict) -> str | None:
        cfg, k = self.cfg, sig.kind
        m_auth = 1.0 if sig.auth is Auth.SIGNER_MLDSA else cfg.token_only_multiplier
        if sig.provenance:
            dt.provenance[k.value] = sig.provenance

        if k is Kind.DEVICE_EVIDENCE:
            dt.available.add(Factor.NETWORK.value)
            dt.last_device_evidence_ts = ts
            return None
        if k is Kind.PHYSICAL_TAMPER:
            dt.available.add(Factor.PHYSICAL.value)
            if sig.value["active"]:
                dt.modality_last["PHYSICAL"] = (ts, sig.signal_id)
                if not dt.tamper_active:
                    self._add_penalty(dt, Factor.PHYSICAL.value, cfg.penalty_points(k))
                    dt.last_violation_ts = ts
                dt.tamper_active = True
                self._hold(dt, "physical_tamper")
            else:
                dt.tamper_active = False
            return Factor.PHYSICAL.value
        if k is Kind.SENSOR_OUT_OF_RANGE:
            dt.available.add(Factor.SENSOR.value)
            if sig.value["active"]:
                dt.modality_last["SENSOR"] = (ts, sig.signal_id)
                if not dt.sensor_active:
                    self._add_penalty(dt, Factor.SENSOR.value, cfg.penalty_points(k))
                    dt.last_violation_ts = ts
                dt.sensor_active = True
            else:
                dt.sensor_active = False
            return Factor.SENSOR.value
        if k is Kind.INTEGRITY_MISMATCH:
            dt.available.add(Factor.CONFIG.value)
            if sig.value["mismatch"] and not dt.integrity_mismatch:
                self._add_penalty(dt, Factor.CONFIG.value, cfg.penalty_points(k))
                dt.last_violation_ts = ts
            dt.integrity_mismatch = sig.value["mismatch"]
            return Factor.CONFIG.value

        if k in (Kind.VISUAL_RULE_VIOLATION, Kind.VISUAL_CLEAR, Kind.CAMERA_OBSTRUCTED, Kind.CAMERA_SOURCE_LOST, Kind.CAMERA_OK):
            dt.available.add(Factor.VISUAL.value)
            if k is Kind.CAMERA_OK:
                dt.episodes.pop("camera_obstructed", None)
                dt.episodes.pop("camera_source_lost", None)
                return Factor.VISUAL.value
            if k is Kind.VISUAL_CLEAR:
                return Factor.VISUAL.value
            if k is Kind.VISUAL_RULE_VIOLATION:
                c = sig.confidence
                if c < cfg.confidence_floor:
                    self._note(sig, "below_confidence_floor_no_impact", confidence=c)
                    return Factor.VISUAL.value
                impact = cfg.visual_base_points * (c ** cfg.confidence_exponent) * m_auth
                key = f"visual|{sig.value.get('zone')}|{sig.value.get('object')}"
                detail["impact_points"] = round(impact, 6)
                add = self._episode(dt, key, impact, ts)
                if c >= cfg.correlation_min_confidence and sig.auth is Auth.SIGNER_MLDSA:
                    dt.modality_last["VISUAL"] = (ts, sig.signal_id)
            else:
                impact = cfg.penalty_points(k) * m_auth
                add = self._episode(dt, k.value, impact, ts)
            if add > 0:
                self._add_penalty(dt, Factor.VISUAL.value, add)
                dt.last_violation_ts = ts
            return Factor.VISUAL.value

        if k in cfg.pressure_points:
            if k is Kind.STALE_OBSERVATION and sig.auth is not Auth.UNAUTHENTICATED:
                self._note(sig, "stale_or_future_observation_not_scored")
                return None
            dt.pressure = min(cfg.pressure_cap, dt.pressure + cfg.pressure_points[k])
            dt.last_violation_ts = ts
            if k in (Kind.DEVICE_REPLAY, Kind.OBSERVATION_REPLAY, Kind.HANDSHAKE_REPLAY):
                dt.replay_times = [t for t in dt.replay_times if ts - t <= cfg.replay_window_s] + [ts]
                if len(dt.replay_times) >= cfg.replay_threshold:
                    self._hold(dt, "repeated_replay")
            return "pressure"
        if k in cfg.penalties:                                         # AUTH_MISBEHAVIOR, MALFORMED_PAYLOAD
            self._add_penalty(dt, cfg.penalties[k][0].value, cfg.penalty_points(k))
            dt.last_violation_ts = ts
            if k is Kind.AUTH_MISBEHAVIOR:
                self._hold(dt, "auth_violation")
            return cfg.penalties[k][0].value
        if k is Kind.DEVICE_REVOKED:
            dt.revoked = True
            dt.last_violation_ts = ts
            return Factor.IDENTITY.value
        raise SignalRejected("unhandled_signal_kind", k.value)          # fail closed

    def _update_incident(self, dt: DeviceTrust, sig: Signal, ts: float) -> dict | None:
        if sig.kind not in _MODALITY_OF and sig.kind is not Kind.PHYSICAL_TAMPER:
            return None
        win = self.cfg.correlation_window_s
        present = {}
        for m, (t, sid) in dt.modality_last.items():
            if (m == "PHYSICAL" and dt.tamper_active) or (m == "SENSOR" and dt.sensor_active) or ts - t <= win:
                present[m] = sid
        if len(present) < 2:
            return None
        cls = "confirmed_incident" if "PHYSICAL" in present else "correlated_incident"
        prev = dt.incident["class"] if dt.incident and self._incident_live(dt) else None
        self._hold(dt, cls)
        if prev == cls or (prev == "confirmed_incident" and cls == "correlated_incident"):
            return None
        dt.incident_seq += 1
        dt.incident = {"id": f"INC-{dt.device_id}-{dt.incident_seq}", "class": cls, "modalities": sorted(present),
                       "members": dict(sorted(present.items())), "started": ts}
        return dict(dt.incident)

    def _incident_live(self, dt: DeviceTrust) -> bool:
        cls = dt.incident["class"]
        return dt.holds.get(cls, -1.0) > dt.credit_clock

    # ------------------------------------------------------------------ explicit transitions (validated only)
    def request_transition(self, device_id: str, target: State, reason: str, evidence_id: str, now: float) -> list[TrustChange]:
        dt = self.devices.get(device_id)
        if dt is None or not dt.started:
            raise IllegalTransition("device has no trust record")
        if not reason or not evidence_id:
            raise IllegalTransition("a reason and an evidence id are required")
        if not isinstance(target, State):
            raise IllegalTransition("unknown target state")
        changes = self._advance(dt, max(now, dt.last_ts))
        sm.assert_legal(dt.state, target)
        if target == dt.state:
            raise IllegalTransition(f"already {target.value}")
        sm.transition_guard(self.cfg, dt.state, target, dt.score, dt.revoked)
        prev = dt.state
        dt.seq += 1
        dt.state = target
        dt.recovery_fault = False
        c = TrustChange(
            event_id=f"TC-{dt.device_id}-{dt.seq}", device_id=dt.device_id, timestamp=max(now, dt.last_ts), previous_score=dt.score,
            new_score=dt.score, delta=0, previous_exact=dt.score_exact, new_exact=dt.score_exact, previous_state=prev, new_state=target,
            trigger_signals=(evidence_id,),
            reasons=(Reason("state_transition_request", 0.0, None, {"reason": reason, "evidence_id": evidence_id,
                                                                        "from": prev.value, "to": target.value}),),
            caps_active=tuple(sorted(c for c, _ in dt.last_comp.caps)), incident=None, coverage=dt.last_comp.coverage,
            unavailable=tuple(dt.last_comp.unavailable), kind="state_transition_request")
        return changes + [c]

    # ------------------------------------------------------------------ read model
    def snapshot(self, device_id: str, now: float) -> dict:
        dt = self.devices.get(device_id)
        if dt is None or not dt.started:
            return {"device_id": device_id, "status": "NO_EVIDENCE"}
        now = max(now, dt.last_ts)
        comp = self._compute(dt, now)
        score = _round_half_up(comp.final)
        cfg = self.cfg
        return {
            "device_id": device_id, "status": "TRACKED", "state": dt.state.value, "score": score, "score_exact": comp.final,
            "recommended_action": sm.RECOMMENDED_ACTION[dt.state], "coverage": comp.coverage, "unavailable": comp.unavailable,
            "factors": {f.value: {"available": f.value in comp.p, "nominal_weight": cfg.weights[f],
                                  "effective_weight": comp.w.get(f.value), "penalty": comp.p.get(f.value)} for f in Factor},
            "pressure": comp.pressure, "raw": comp.raw, "uncapped": comp.uncapped, "caps": [{"name": n, "ceiling": c} for n, c in comp.caps],
            "revoked": dt.revoked, "tamper_active": dt.tamper_active, "incident": dt.incident, "provenance": dt.provenance,
            "last_device_evidence_age_s": None if dt.last_device_evidence_ts is None else max(0.0, now - dt.last_device_evidence_ts),
            "credit_clock_s": dt.credit_clock, "duplicates_ignored": dt.duplicates,
            "notes": "score reflects only available signals; see coverage and unavailable",
        }
