"""Where a device's readings come from. The agent signs and sends them; it never invents a field a source lacks.

    SimulatedSensors   the software device agent's readings (SIMULATED values; the default)
    ReplaySensors      readings recorded elsewhere, one JSON object per line: for replaying logs captured from real
                       hardware (an ESP32 serial log, a bench recording) through the same protocol and trust engine

Field names, units and meaning are the gateway's TelemetryPayload (docs/hardware/device-protocol.md). A sensor that
is absent is left out (sent as missing, never as 0). The real ESP32 does not use this module: its firmware builds the
same telemetry payload itself (hardware/esp32/firmware), so moving from the agent to the board changes the sender,
not the protocol, the gateway or the trust engine.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Iterator, Protocol

# Telemetry fields a source may provide (the gateway rejects any other field as a malformed payload).
TELEMETRY_FIELDS = ("temperature_c", "humidity_pct", "pressure_hpa", "vibration_g", "rssi_dbm", "tamper")


class SensorSource(Protocol):
    capabilities: tuple[str, ...]          # reported at registration

    def read(self) -> dict: ...            # one reading: a subset of TELEMETRY_FIELDS


class SimulatedSensors:
    """Plausible indoor values with small noise. SIMULATED: no sensor is read."""

    capabilities = ("temperature", "vibration", "tamper")

    def __init__(self, seed: int = 1):
        self._rng = random.Random(seed)
        self._net = random.Random(seed + 1)          # separate stream: adding a field leaves the others unchanged
        self.tamper = False

    def read(self) -> dict:
        return {
            "temperature_c": round(27.4 + self._rng.uniform(-0.3, 0.3), 2),
            "vibration_g": round(abs(self._rng.gauss(0.02, 0.005)), 3),
            "rssi_dbm": round(-55 + self._net.uniform(-4, 4), 1),
            "tamper": self.tamper,
        }


class ReplaySensors:
    """Replays recorded readings in order (and stops when they run out). Unknown fields are refused, not dropped."""

    def __init__(self, path: str | Path, capabilities: tuple[str, ...] = ()):
        self.capabilities = tuple(capabilities)
        self._rows: Iterator[dict] = iter(self._load(Path(path)))

    @staticmethod
    def _load(path: Path) -> list[dict]:
        rows = []
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{n}: a reading must be a JSON object")
            unknown = set(row) - set(TELEMETRY_FIELDS)
            if unknown:
                raise ValueError(f"{path}:{n}: unknown telemetry fields {sorted(unknown)}")
            if not isinstance(row.get("tamper"), bool):
                raise ValueError(f"{path}:{n}: every reading needs a boolean 'tamper' (the switch state, not a guess)")
            rows.append(row)
        return rows

    def read(self) -> dict:
        row = next(self._rows, None)
        if row is None:
            raise StopIteration("no more recorded readings")
        return dict(row)
