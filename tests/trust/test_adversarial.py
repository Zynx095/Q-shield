"""Phase 4 adversarial tests: malformed records, missing metadata, extreme rates, conflicting signals. The engine fails closed."""
import json
import time

import pytest

from backend.trust import adapters
from backend.trust.config import TrustConfig
from backend.trust.model import Auth, Kind
from backend.trust.service import TrustService
from tests.trust.helpers import T0, engine, evidence, healthy, sig, tamper, unauth, visual


class Row(dict):
    __getattr__ = dict.__getitem__


def obs_row(body, auth="ML-DSA-65:vision-1", received=T0, rid=1):
    return Row(id=rid, received_at=received, body=json.dumps(body) if not isinstance(body, str) else body, auth=auth)


def good_body(**over):
    b = {"observation_id": "o1", "device_id": "D1", "event_type": "visual_observation", "timestamp": "2023-11-14T22:13:20Z",
         "anomaly": True, "confidence": 0.9, "zone": "z", "object": "person"}
    b.update(over)
    return b


def test_observation_with_unknown_authenticity_label_yields_no_signal():
    for label in ("", "none", "unauthenticated", "hmac", "ML-KEM:x"):
        r = adapters.from_observation(obs_row(good_body(), auth=label), TrustConfig())
        assert r.signals == [] and "authenticity" in r.note


@pytest.mark.parametrize("body", ["not json", "[]", "null", "{}", json.dumps({"device_id": "D1"})])
def test_malformed_observation_records_yield_no_signal(body):
    assert adapters.from_observation(obs_row(body), TrustConfig()).signals == []


def test_observation_time_skew_becomes_unscored_stale_signal():
    r = adapters.from_observation(obs_row(good_body(), received=T0 + 10_000), TrustConfig())
    assert [s.kind for s in r.signals] == [Kind.STALE_OBSERVATION]


def test_observation_unparseable_time_is_stale_not_anomaly():
    r = adapters.from_observation(obs_row(good_body(timestamp="yesterday")), TrustConfig())
    assert [s.kind for s in r.signals] == [Kind.STALE_OBSERVATION]


def test_authenticity_comes_from_the_gateway_label_not_the_body():
    b = good_body(auth="ML-DSA-65", authenticity="SIGNER_MLDSA")         # attacker-controlled extra fields are ignored
    r = adapters.from_observation(obs_row(b, auth="ingest-token"), TrustConfig())
    assert r.signals[0].auth is Auth.TOKEN_ONLY


def test_out_of_range_confidence_in_stored_body_is_rejected_by_engine():
    e = engine()
    healthy(e)
    r = adapters.from_observation(obs_row(good_body(confidence=7.5)), TrustConfig())
    from backend.trust.model import SignalRejected
    with pytest.raises(SignalRejected):
        e.apply(r.signals[0])


def test_device_message_with_garbage_payload_only_gives_evidence():
    row = Row(id=1, device_id="D1", received_at=T0, kind="telemetry", payload="{{{")
    r = adapters.from_device_message(row, TrustConfig(sensor_limits={"temperature_c": (0, 50)}), None)
    assert [s.kind for s in r.signals] == [Kind.DEVICE_EVIDENCE]


@pytest.mark.parametrize("v", ["hot", None, float("nan"), True, [1]])
def test_unreadable_value_in_limited_field_fails_closed(v):
    payload = json.dumps({"temperature_c": v, "tamper": False}) if v is not float("nan") else '{"temperature_c": NaN, "tamper": false}'
    row = Row(id=1, device_id="D1", received_at=T0, kind="telemetry", payload=payload)
    r = adapters.from_device_message(row, TrustConfig(sensor_limits={"temperature_c": (0, 50)}), None)
    kinds = {s.kind: s for s in r.signals}
    if v is None:
        assert Kind.SENSOR_OUT_OF_RANGE not in kinds                  # absent sensor: unavailable, never 0, never anomaly
    else:
        assert kinds[Kind.SENSOR_OUT_OF_RANGE].value["active"] is True


def test_tamper_must_be_boolean_in_telemetry():
    row = Row(id=1, device_id="D1", received_at=T0, kind="telemetry", payload=json.dumps({"tamper": "false"}))
    assert [s.kind for s in adapters.from_device_message(row, TrustConfig(), None).signals] == [Kind.DEVICE_EVIDENCE]


def test_unknown_event_types_never_score(store):
    for et in ("mystery", "pqc_new_thing", "OPERATOR_TOKEN_STOLEN"):
        r = adapters.from_security_event(Row(id=1, received_at=T0, device_id="D1", event_type=et, details="{}"), store)
        assert r.signals == [] and "unmapped" in r.note


def test_event_attribution_by_signer_only_when_single_device(store, pqc_world, clock):
    ev = lambda sid: Row(id=1, received_at=T0, device_id=None, event_type="pqc_invalid_signature",  # noqa: E731
                         details=json.dumps({"claimed_signer_id": sid}))
    assert adapters.from_security_event(ev("vision-1"), store).signals[0].device_id == "DEVICE-001"
    assert adapters.from_security_event(ev("nobody"), store).signals == []
    store.add_signer("multi", "ML-DSA-65", b"k", "usb_webcam", ["DEVICE-001", "DEVICE-002"], clock())
    assert adapters.from_security_event(ev("multi"), store).signals == []       # ambiguous -> unattributed
    bad = Row(id=1, received_at=T0, device_id=None, event_type="pqc_invalid_signature", details="not json")
    assert adapters.from_security_event(bad, store).signals == []


def test_forged_events_can_only_ever_produce_unauthenticated_signals(store):
    for et, (kind, auth) in adapters.EVENT_MAP.items():
        if auth is Auth.UNAUTHENTICATED:
            assert kind in TrustConfig().pressure_points, et


def test_conflicting_signals_take_worst_case_and_stay_bounded():
    e = engine()
    healthy(e)
    e.apply(tamper(T0 + 20))
    e.apply(tamper(T0 + 21, False))
    e.apply(tamper(T0 + 22))
    e.apply(evidence(T0 + 23))
    s = e.snapshot("D1", T0 + 23)
    assert s["score"] <= 55 and 0 <= s["factors"]["physical"]["penalty"] <= 100


def test_repeated_identical_tamper_reports_do_not_stack():
    e = engine()
    healthy(e)
    for i in range(100):
        e.apply(tamper(T0 + 20 + i * 0.01))
    assert e.snapshot("D1", T0 + 21)["factors"]["physical"]["penalty"] == 100.0


def test_future_timestamps_do_not_rewind_or_freeze_time():
    e = engine()
    healthy(e)
    e.apply(evidence(T0 + 50_000_000))                                # absurd but accepted-as-finite receipt time
    e.apply(evidence(T0 + 40))                                        # later "normal" signal is treated as out of order
    assert e.devices["D1"].last_ts >= T0 + 50_000_000
    assert e.snapshot("D1", T0 + 40)["score"] <= 100


def test_extreme_event_rate_is_bounded_and_fast():
    e = engine()
    healthy(e)
    t0 = time.perf_counter()
    for i in range(20_000):
        e.apply(unauth(Kind.INVALID_TAG, T0 + 20 + i * 1e-4, sid=f"f{i}"))
    dt = time.perf_counter() - t0
    assert e.snapshot("D1", T0 + 30)["pressure"] <= 25
    assert len(e.devices["D1"].seen) <= TrustConfig().max_seen_ids
    assert dt < 30                                                     # generous CI bound; real numbers are in docs/results


def test_service_survives_rows_the_adapters_cannot_read(store, clock, device_secret):
    store._db.execute("INSERT INTO device_messages(device_id, received_at, kind, payload) VALUES ('DEVICE-001', ?, 'telemetry', '<<<')",
                      (clock(),))
    store._db.execute("INSERT INTO observations(observation_id, received_at, device_id, event_type, observed_at, anomaly, body, auth) "
                      "VALUES ('x', ?, 'DEVICE-001', 'visual_observation', 'x', 1, 'garbage', 'ingest-token')", (clock(),))
    store._db.commit()
    svc = TrustService(store, clock=clock)
    changes = svc.process_pending()
    assert svc.snapshot("DEVICE-001")["score"] == 100
    assert any(d["reason"] == "malformed_observation_record" for d in store.list_trust_diagnostics())
    assert svc.process_pending() == []
    assert changes is not None


def test_revoked_device_cannot_regain_score_through_fresh_evidence():
    e = engine()
    healthy(e)
    e.apply(sig(Kind.DEVICE_REVOKED, T0 + 20, auth=Auth.GATEWAY_LOCAL))
    for i in range(50):
        e.apply(evidence(T0 + 30 + i * 10))
    assert e.snapshot("D1", T0 + 600)["score"] == 0
