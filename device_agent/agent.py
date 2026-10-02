"""Software device agent: speaks the Q-SHIELD device protocol without hardware.

Values are SIMULATED and the agent registers with hw="software-agent" so gateway data is
never mistaken for real ESP32 sensor readings. It uses the same hmac-sha256-psk profile
as the ESP32 (symmetric, not post-quantum). Readings come from a SensorSource
(device_agent/sensors.py): simulated by default, or replayed from a recording.
"""
from __future__ import annotations

import json
from typing import Protocol

from backend.protocol.envelope import (
    MSG_HEARTBEAT, MSG_RECOVERY, MSG_REGISTER, MSG_TELEMETRY, build_hmac_envelope,
)
from device_agent.sensors import SensorSource, SimulatedSensors


class Transport(Protocol):
    def post(self, path: str, json: dict): ...  # httpx.Client or starlette TestClient


class DeviceAgent:
    def __init__(self, device_id: str, secret: bytes, transport: Transport,
                 fw_version: str = "agent-0.1", seed: int = 1, start_counter: int = 0,
                 sensors: SensorSource | None = None, hw: str = "software-agent"):
        self.device_id = device_id
        self._secret = secret
        self._t = transport
        self.fw_version = fw_version
        self.counter = start_counter
        self.tamper = False
        self.cfg_hash: str | None = None      # simulated configuration identity (None = not reported)
        self.pending_ack: str | None = None
        self.sensors = sensors or SimulatedSensors(seed)
        self.hw = hw                          # "software-agent" unless the readings really come from hardware
        self._uptime_ms = 0

    def _send(self, path: str, msg_type: str, payload: dict):
        self.counter += 1
        payload_text = json.dumps(payload, separators=(",", ":"))
        env = build_hmac_envelope(self._secret, msg_type, self.device_id, self.counter, payload_text)
        return self._t.post(f"/api/v1/{path}", json=env)

    def register(self):
        return self._send("register", MSG_REGISTER, {
            "fw_version": self.fw_version, "hw": self.hw, "capabilities": list(self.sensors.capabilities),
        })

    def heartbeat(self, advance_ms: int = 5000):
        self._uptime_ms += advance_ms
        return self._send("heartbeat", MSG_HEARTBEAT, {"uptime_ms": self._uptime_ms})

    def sample(self) -> dict:
        reading = self.sensors.read()
        if isinstance(self.sensors, SimulatedSensors):
            reading["tamper"] = self.tamper      # the simulated switch is driven by the agent (attack simulation)
        return {
            **reading,
            "fw_version": self.fw_version,
            **({"cfg_hash": self.cfg_hash} if self.cfg_hash is not None else {}),
        }

    def telemetry(self, **overrides):
        return self._send("telemetry", MSG_TELEMETRY, {**self.sample(), **overrides})

    # ---- recovery channel (Phase 6/7): used while the gateway has the device quarantined ----
    def recovery_report(self, **overrides):
        """Authenticated recovery-channel report. If the gateway returns a remediation command the simulated device
        applies it (sets its configuration identity) and acknowledges it in the NEXT report. SIMULATED remediation:
        a real device would have to actually reload its configuration; firmware is never changed here."""
        payload = {**self.sample(), **overrides}
        if self.pending_ack:
            payload["ack_command_id"] = self.pending_ack
            self.pending_ack = None
        r = self._send("recovery/report", MSG_RECOVERY, payload)
        if r.status_code == 200:
            cmd = r.json().get("command")
            if cmd and cmd.get("action") == "apply_known_good_config":
                if cmd.get("cfg_hash"):
                    self.cfg_hash = cmd["cfg_hash"]
                self.pending_ack = cmd["command_id"]
        return r
