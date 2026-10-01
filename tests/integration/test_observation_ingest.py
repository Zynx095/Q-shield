"""Backend ingestion of observations (no vision code or model involved)."""
import copy

import pytest

OBS = {
    "event_type": "visual_observation", "device_id": "DEVICE-001", "timestamp": "2026-01-01T00:00:00Z",
    "source": "usb_webcam", "object": "person", "confidence": 0.91, "zone": "restricted_zone",
    "zone_kind": "restricted", "bbox": {"x1": 0.6, "y1": 0.1, "x2": 0.9, "y2": 0.9},
    "anomaly": True, "anomaly_reason": "restricted_class_in_restricted_zone",
    "model": {"name": "yolo11n", "version": "t"}, "observation_id": "3f0c1c9e-8a7e-4a55-9b0a-2a0e5f1b6d11",
}


def test_ingest_and_query(ingest_client, client):
    r = ingest_client.post("/api/v1/observations", json=OBS)
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    (o,) = client.get("/api/v1/observations").json()
    assert o["object"] == "person" and o["anomaly"] is True and o["zone"] == "restricted_zone"
    assert "received_at" in o
    assert o["auth"] == "ingest-token" and o["transport"] == "token"        # bearer token only: not signed


def test_ingest_is_idempotent_on_observation_id(ingest_client, client):
    ingest_client.post("/api/v1/observations", json=OBS)
    assert ingest_client.post("/api/v1/observations", json=OBS).json()["status"] == "duplicate"
    assert len(client.get("/api/v1/observations").json()) == 1


def test_ingest_requires_ingest_token(anon_client, client):
    assert anon_client.post("/api/v1/observations", json=OBS).status_code == 401
    assert client.post("/api/v1/observations", json=OBS).status_code == 401  # operator token is not enough


@pytest.mark.parametrize("patch", [
    {"confidence": 1.5}, {"confidence": -0.1}, {"timestamp": "2026-01-01T00:00:00"},
    {"bbox": {"x1": 0.9, "y1": 0.1, "x2": 0.6, "y2": 0.9}}, {"event_type": "trust_update"},
    {"trust_score": 12}, {"device_id": "bad id"},
])
def test_malformed_observations_rejected_and_not_stored(ingest_client, client, patch):
    r = ingest_client.post("/api/v1/observations", json={**OBS, **patch})
    assert r.status_code == 422
    assert client.get("/api/v1/observations").json() == []


def test_missing_fields_rejected(ingest_client):
    for field in ("device_id", "timestamp", "anomaly", "confidence", "bbox"):
        d = copy.deepcopy(OBS)
        del d[field]
        assert ingest_client.post("/api/v1/observations", json=d).status_code == 422
    assert ingest_client.post("/api/v1/observations", json={}).status_code == 422
    assert ingest_client.post("/api/v1/observations", content=b"not json",
                              headers={"content-type": "application/json"}).status_code == 422


def test_unknown_device_rejected_and_logged(ingest_client, client):
    r = ingest_client.post("/api/v1/observations", json={**OBS, "device_id": "ROGUE-9"})
    assert r.status_code == 422
    assert client.get("/api/v1/events").json()[0]["event_type"] == "observation_rejected_device"


def test_revoked_device_rejected(ingest_client, store):
    store.revoke_device("DEVICE-001")
    assert ingest_client.post("/api/v1/observations", json=OBS).status_code == 422


def test_filters(ingest_client, client):
    ingest_client.post("/api/v1/observations", json=OBS)
    calm = {**OBS, "observation_id": "4f0c1c9e-8a7e-4a55-9b0a-2a0e5f1b6d12", "anomaly": False,
            "anomaly_reason": None, "zone": None, "zone_kind": None}
    ingest_client.post("/api/v1/observations", json=calm)
    assert len(client.get("/api/v1/observations").json()) == 2
    assert len(client.get("/api/v1/observations?anomalies_only=true").json()) == 1
    assert client.get("/api/v1/observations?device_id=NOPE").json() == []


def test_observation_does_not_change_device_status_or_touch_last_seen(ingest_client, client):
    """Observations are evidence only: they neither mark the device online nor alter trust state."""
    before = client.get("/api/v1/devices/DEVICE-001").json()
    ingest_client.post("/api/v1/observations", json=OBS)
    assert client.get("/api/v1/devices/DEVICE-001").json() == before
