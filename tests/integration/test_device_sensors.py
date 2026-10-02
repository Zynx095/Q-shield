"""Device-agent sensor sources: the simulated default, and recorded readings replayed through the same protocol."""
import json
import random

import pytest

from device_agent.agent import DeviceAgent
from device_agent.sensors import TELEMETRY_FIELDS, ReplaySensors, SimulatedSensors


def test_simulated_readings_are_unchanged_by_the_sensor_interface(client, device_secret):
    """Same seed, same temperature and vibration sequence as before the readings moved to SimulatedSensors."""
    rng = random.Random(1)
    agent = DeviceAgent("DEVICE-001", device_secret, client)
    for _ in range(3):
        s = agent.sample()
        assert s["temperature_c"] == round(27.4 + rng.uniform(-0.3, 0.3), 2)
        assert s["vibration_g"] == round(abs(rng.gauss(0.02, 0.005)), 3)
        assert -60 <= s["rssi_dbm"] <= -50 and s["tamper"] is False and s["fw_version"] == "agent-0.1"
    agent.tamper = True
    assert agent.sample()["tamper"] is True


def test_simulated_device_registers_as_software_agent(client, device_secret):
    agent = DeviceAgent("DEVICE-001", device_secret, client)
    assert agent.register().status_code == 200 and agent.telemetry().status_code == 200
    d = client.get("/api/v1/devices/DEVICE-001").json()
    assert d["hw"] == "software-agent" and isinstance(d["rssi_dbm"], float)


def test_recorded_readings_replay_through_the_same_protocol(client, device_secret, tmp_path):
    log = tmp_path / "bench.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in [
        {"temperature_c": 24.1, "humidity_pct": 40.0, "tamper": False, "rssi_dbm": -62},
        {"temperature_c": 24.2, "humidity_pct": 40.5, "tamper": True, "rssi_dbm": -63},
    ]) + "\n", encoding="utf-8")
    agent = DeviceAgent("DEVICE-001", device_secret, client, sensors=ReplaySensors(log, ("temperature", "humidity", "tamper")),
                        hw="replay")
    assert agent.register().status_code == 200
    assert agent.telemetry().status_code == 200 and agent.telemetry().status_code == 200
    rows = client.get("/api/v1/devices/DEVICE-001/telemetry").json()
    assert [(r["tamper"], r["temperature_c"]) for r in rows] == [(True, 24.2), (False, 24.1)]     # newest first
    d = client.get("/api/v1/devices/DEVICE-001").json()
    assert d["hw"] == "replay" and d["humidity_pct"] == 40.5
    with pytest.raises(StopIteration):
        agent.sample()                                           # recordings end: nothing is invented


@pytest.mark.parametrize("row,err", [({"temperature_c": 20, "tamper": False, "co2_ppm": 400}, "unknown telemetry fields"),
                                     ({"temperature_c": 20}, "boolean 'tamper'"), ({"temperature_c": 20, "tamper": "no"}, "boolean")])
def test_replay_refuses_what_the_gateway_would_refuse(tmp_path, row, err):
    log = tmp_path / "bad.jsonl"
    log.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=err):
        ReplaySensors(log)


def test_sensor_fields_match_the_gateway_telemetry_schema():
    from backend.api.app import TelemetryPayload

    gateway_fields = set(TelemetryPayload.model_fields) - {"fw_version", "cfg_hash"}
    assert set(TELEMETRY_FIELDS) == gateway_fields
    assert set(SimulatedSensors().read()) <= set(TELEMETRY_FIELDS)
