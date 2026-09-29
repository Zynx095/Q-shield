"""Lightweight digital twin: EXPECTED vs OBSERVED device state (Phase 9).

EXPECTED state is set by the operator on the security control channel. OBSERVED state is taken only from
HMAC-authenticated device messages (register / telemetry / recovery). Comparison yields MATCH / MISMATCH / UNKNOWN
per field.

Honesty boundary: every observed field is SELF-REPORTED by the device. A matching firmware version or config hash is
evidence, not proof: without secure boot and remote attestation a compromised device can report whatever it likes.
Nothing here performs attestation.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

from backend.devices.store import Store

SCHEMA = """
CREATE TABLE IF NOT EXISTS device_twin (
    device_id  TEXT PRIMARY KEY,
    expected   TEXT NOT NULL DEFAULT '{}',
    observed   TEXT NOT NULL DEFAULT '{}',
    updated_at REAL NOT NULL
);
"""

MATCH, MISMATCH, UNKNOWN = "MATCH", "MISMATCH", "UNKNOWN"
EXPECTED_KEYS = {"fw_version", "cfg_hash", "capabilities", "sensor_ranges"}


class TwinError(ValueError):
    pass


def _validate_expected(exp: dict) -> dict:
    extra = set(exp) - EXPECTED_KEYS
    if extra:
        raise TwinError(f"unknown expected-state keys: {sorted(extra)}")
    out: dict[str, Any] = {}
    for k in ("fw_version", "cfg_hash"):
        if exp.get(k) is not None:
            if not isinstance(exp[k], str) or not (0 < len(exp[k]) <= 128):
                raise TwinError(f"{k} must be a non-empty string")
            out[k] = exp[k]
    if exp.get("capabilities") is not None:
        caps = exp["capabilities"]
        if not isinstance(caps, list) or not all(isinstance(c, str) for c in caps):
            raise TwinError("capabilities must be a list of strings")
        out["capabilities"] = sorted(set(caps))
    if exp.get("sensor_ranges") is not None:
        rng = {}
        for f, v in exp["sensor_ranges"].items():
            if not (isinstance(v, (list, tuple)) and len(v) == 2):
                raise TwinError("sensor_ranges values must be [min, max]")
            lo, hi = v
            for b in (lo, hi):
                if b is not None and (isinstance(b, bool) or not isinstance(b, (int, float)) or not math.isfinite(b)):
                    raise TwinError("sensor range bounds must be finite numbers or null")
            if lo is not None and hi is not None and lo > hi:
                raise TwinError(f"sensor range for {f} has min > max")
            rng[f] = [lo, hi]
        out["sensor_ranges"] = rng
    return out


@dataclass
class Comparison:
    device_id: str
    fields: dict = field(default_factory=dict)       # field -> {"expected", "observed", "status"}
    overall: str = UNKNOWN
    note: str = "observed values are self-reported by the device; a MATCH is evidence, not attestation"

    def to_dict(self) -> dict:
        return {"device_id": self.device_id, "overall": self.overall, "fields": self.fields, "note": self.note}


def _in_range(value, lo, hi) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return False
    return (lo is None or value >= lo) and (hi is None or value <= hi)


class DigitalTwin:
    def __init__(self, store: Store):
        self.store = store
        store.ensure_schema(SCHEMA)

    def _row(self, device_id: str) -> tuple[dict, dict]:
        rows = self.store.query("SELECT expected, observed FROM device_twin WHERE device_id=?", (device_id,))
        if not rows:
            return {}, {}
        return json.loads(rows[0]["expected"]), json.loads(rows[0]["observed"])

    def expected(self, device_id: str) -> dict:
        return self._row(device_id)[0]

    def observed(self, device_id: str) -> dict:
        return self._row(device_id)[1]

    def set_expected(self, device_id: str, expected: dict, now: float) -> dict:
        exp = _validate_expected(expected)
        _, obs = self._row(device_id)
        self.store.execute("INSERT OR REPLACE INTO device_twin(device_id, expected, observed, updated_at) VALUES (?,?,?,?)",
                           (device_id, json.dumps(exp), json.dumps(obs), now))
        return exp

    def observe(self, device_id: str, now: float, *, info: dict | None = None, telemetry: dict | None = None) -> None:
        """Record authenticated, self-reported state. Called only after the HMAC envelope verified."""
        exp, obs = self._row(device_id)
        if info:
            for k in ("fw_version",):
                if info.get(k) is not None:
                    obs[k] = info[k]
            if isinstance(info.get("capabilities"), list):
                obs["capabilities"] = sorted(set(info["capabilities"]))
        if telemetry:
            for k in ("fw_version", "cfg_hash"):
                if telemetry.get(k) is not None:
                    obs[k] = telemetry[k]
            sensors = {k: v for k, v in telemetry.items() if k not in ("fw_version", "cfg_hash", "tamper") and v is not None}
            if sensors:
                obs["sensors"] = sensors
            if isinstance(telemetry.get("tamper"), bool):
                obs["tamper"] = telemetry["tamper"]
        obs["observed_at"] = now
        self.store.execute("INSERT OR REPLACE INTO device_twin(device_id, expected, observed, updated_at) VALUES (?,?,?,?)",
                           (device_id, json.dumps(exp), json.dumps(obs), now))

    def compare(self, device_id: str) -> Comparison:
        exp, obs = self._row(device_id)
        cmp = Comparison(device_id)
        for k in ("fw_version", "cfg_hash"):
            if k in exp:
                o = obs.get(k)
                status = UNKNOWN if o is None else (MATCH if o == exp[k] else MISMATCH)
                cmp.fields[k] = {"expected": exp[k], "observed": o, "status": status}
        if "capabilities" in exp:
            o = obs.get("capabilities")
            status = UNKNOWN if o is None else (MATCH if sorted(o) == exp["capabilities"] else MISMATCH)
            cmp.fields["capabilities"] = {"expected": exp["capabilities"], "observed": o, "status": status}
        sensors = obs.get("sensors", {})
        for f, (lo, hi) in exp.get("sensor_ranges", {}).items():
            o = sensors.get(f)
            status = UNKNOWN if o is None else (MATCH if _in_range(o, lo, hi) else MISMATCH)
            cmp.fields[f"sensor:{f}"] = {"expected": [lo, hi], "observed": o, "status": status}
        statuses = [v["status"] for v in cmp.fields.values()]
        if not statuses or all(s == UNKNOWN for s in statuses):
            cmp.overall = UNKNOWN
        elif MISMATCH in statuses:
            cmp.overall = MISMATCH
        elif UNKNOWN in statuses:
            cmp.overall = UNKNOWN          # partially observed: not enough to call it a match
        else:
            cmp.overall = MATCH
        return cmp

    def trust_expectations(self, device_id: str) -> dict:
        """Per-device expectations for the trust adapters (overrides the global trust config when present)."""
        exp = self.expected(device_id)
        out = {}
        if "fw_version" in exp:
            out["expected_fw_version"] = exp["fw_version"]
        if "cfg_hash" in exp:
            out["expected_cfg_hash"] = exp["cfg_hash"]
        if "sensor_ranges" in exp:
            out["sensor_limits"] = {f: tuple(v) for f, v in exp["sensor_ranges"].items()}
        return out
