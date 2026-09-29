"""Phase 1 acceptance: gateway shows DEVICE-001 ONLINE with telemetry, then OFFLINE on silence."""
from device_agent.agent import DeviceAgent


def test_phase1_acceptance(client, device_secret, clock):
    # Enrolled but never heard from.
    d = client.get("/api/v1/devices/DEVICE-001").json()
    assert d["status"] == "ENROLLED" and d["last_seen"] is None

    agent = DeviceAgent("DEVICE-001", device_secret, client)
    assert agent.register().status_code == 200
    assert agent.heartbeat().status_code == 200
    assert agent.telemetry().status_code == 200

    d = client.get("/api/v1/devices").json()[0]
    assert d["device_id"] == "DEVICE-001"
    assert d["status"] == "ONLINE"
    assert d["hw"] == "software-agent"          # simulated data is labelled as such
    assert 26 < d["temperature_c"] < 29
    assert d["vibration_g"] is not None
    assert d["tamper"] is False
    assert d["last_seen"] is not None
    assert "secret" not in d

    clock.advance(14)
    assert client.get("/api/v1/devices/DEVICE-001").json()["status"] == "ONLINE"
    clock.advance(2)
    assert client.get("/api/v1/devices/DEVICE-001").json()["status"] == "OFFLINE"

    assert agent.heartbeat().status_code == 200   # comes back
    assert client.get("/api/v1/devices/DEVICE-001").json()["status"] == "ONLINE"


def test_tamper_flag_visible(client, device_secret):
    agent = DeviceAgent("DEVICE-001", device_secret, client)
    agent.register()
    agent.tamper = True
    agent.telemetry()
    assert client.get("/api/v1/devices/DEVICE-001").json()["tamper"] is True


def test_absent_sensor_is_null_not_zero(client, device_secret):
    agent = DeviceAgent("DEVICE-001", device_secret, client)
    agent.telemetry(vibration_g=None)
    assert client.get("/api/v1/devices/DEVICE-001").json()["vibration_g"] is None


def test_telemetry_history(client, device_secret):
    agent = DeviceAgent("DEVICE-001", device_secret, client)
    for _ in range(3):
        agent.telemetry()
    hist = client.get("/api/v1/devices/DEVICE-001/telemetry").json()
    assert len(hist) == 3 and hist[0]["counter"] > hist[-1]["counter"]


def test_unknown_device_detail_404(client):
    assert client.get("/api/v1/devices/NOPE").status_code == 404
