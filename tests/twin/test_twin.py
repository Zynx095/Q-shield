"""Phase 9: expected vs observed device state."""
import pytest

from backend.twin.twin import MATCH, MISMATCH, UNKNOWN, DigitalTwin, TwinError


@pytest.fixture
def twin(store):
    return DigitalTwin(store)


EXP = {"fw_version": "1.2", "cfg_hash": "abc", "capabilities": ["tamper", "temperature"],
       "sensor_ranges": {"temperature_c": [-10, 50]}}


def test_unknown_until_observed(twin):
    twin.set_expected("D", EXP, 1.0)
    c = twin.compare("D")
    assert c.overall == UNKNOWN and all(f["status"] == UNKNOWN for f in c.fields.values())
    assert "not attestation" in c.note


def test_match(twin):
    twin.set_expected("D", EXP, 1.0)
    twin.observe("D", 2.0, info={"fw_version": "1.2", "capabilities": ["temperature", "tamper"]})
    twin.observe("D", 3.0, telemetry={"fw_version": "1.2", "cfg_hash": "abc", "temperature_c": 20.0, "tamper": False})
    assert twin.compare("D").overall == MATCH


@pytest.mark.parametrize("tel,field", [({"cfg_hash": "evil"}, "cfg_hash"), ({"fw_version": "0.9"}, "fw_version"),
                                        ({"temperature_c": 99.0}, "sensor:temperature_c")])
def test_mismatch(twin, tel, field):
    twin.set_expected("D", EXP, 1.0)
    twin.observe("D", 2.0, info={"fw_version": "1.2", "capabilities": ["temperature", "tamper"]})
    base = {"fw_version": "1.2", "cfg_hash": "abc", "temperature_c": 20.0}
    twin.observe("D", 3.0, telemetry={**base, **tel})
    c = twin.compare("D")
    assert c.overall == MISMATCH and c.fields[field]["status"] == MISMATCH


def test_capability_mismatch(twin):
    twin.set_expected("D", EXP, 1.0)
    twin.observe("D", 2.0, info={"fw_version": "1.2", "capabilities": ["temperature"]})
    assert twin.compare("D").fields["capabilities"]["status"] == MISMATCH


def test_partial_observation_is_unknown_not_match(twin):
    twin.set_expected("D", EXP, 1.0)
    twin.observe("D", 2.0, telemetry={"fw_version": "1.2"})
    assert twin.compare("D").overall == UNKNOWN


def test_no_expected_state_is_unknown(twin):
    twin.observe("D", 2.0, telemetry={"fw_version": "1.2"})
    assert twin.compare("D").overall == UNKNOWN


@pytest.mark.parametrize("bad", [{"nope": 1}, {"fw_version": ""}, {"capabilities": "x"},
                                 {"sensor_ranges": {"t": [5, 1]}}, {"sensor_ranges": {"t": [float("nan"), 1]}},
                                 {"sensor_ranges": {"t": [1]}}])
def test_invalid_expected_rejected(twin, bad):
    with pytest.raises(TwinError):
        twin.set_expected("D", bad, 1.0)


def test_trust_expectations_mapping(twin):
    twin.set_expected("D", EXP, 1.0)
    e = twin.trust_expectations("D")
    assert e == {"expected_fw_version": "1.2", "expected_cfg_hash": "abc", "sensor_limits": {"temperature_c": (-10, 50)}}
    assert twin.trust_expectations("other") == {}


def test_set_expected_preserves_observed(twin):
    twin.observe("D", 2.0, telemetry={"cfg_hash": "abc"})
    twin.set_expected("D", {"cfg_hash": "abc"}, 3.0)
    assert twin.observed("D")["cfg_hash"] == "abc" and twin.compare("D").overall == MATCH


def test_compare_report_judges_only_what_the_report_says(twin):
    """Recovery health checks: a field missing from the report is UNKNOWN, never borrowed from an older report."""
    twin.set_expected("D", EXP, 1.0)
    twin.observe("D", 2.0, info={"fw_version": "1.2", "capabilities": ["temperature", "tamper"]})
    twin.observe("D", 3.0, telemetry={"fw_version": "1.2", "cfg_hash": "abc", "temperature_c": 20.0, "tamper": False})
    assert twin.compare("D").overall == MATCH
    silent = twin.compare_report("D", {"fw_version": "1.2", "temperature_c": 20.0, "tamper": False, "cfg_hash": None})
    assert silent.overall == UNKNOWN and silent.fields["cfg_hash"]["status"] == UNKNOWN
    assert twin.compare("D").fields["cfg_hash"]["status"] == MATCH          # the accumulated view still remembers it
    full = twin.compare_report("D", {"fw_version": "1.2", "cfg_hash": "abc", "temperature_c": 21.0, "tamper": False,
                                     "ack_command_id": "CMD-1"})
    assert full.overall == MATCH and full.fields["capabilities"]["status"] == MATCH   # from the last registration
    bad = twin.compare_report("D", {"fw_version": "1.2", "cfg_hash": "abc", "temperature_c": 99.0, "tamper": False})
    assert bad.overall == MISMATCH and bad.fields["sensor:temperature_c"]["status"] == MISMATCH


def test_each_observed_field_carries_when_it_was_last_reported(twin):
    twin.set_expected("D", EXP, 1.0)
    twin.observe("D", 2.0, info={"fw_version": "1.2", "capabilities": ["temperature", "tamper"]})
    twin.observe("D", 3.0, telemetry={"fw_version": "1.2", "cfg_hash": "abc", "temperature_c": 20.0, "tamper": False})
    twin.observe("D", 9.0, telemetry={"fw_version": "1.2", "temperature_c": 21.0, "tamper": True})   # no cfg_hash now
    f = twin.compare("D").fields
    assert f["cfg_hash"]["reported_at"] == 3.0 and f["fw_version"]["reported_at"] == 9.0
    assert f["capabilities"]["reported_at"] == 2.0 and f["sensor:temperature_c"]["reported_at"] == 9.0
    obs = twin.observed("D")
    assert obs["observed_at"] == 9.0 and obs["reported_at"]["tamper"] == 9.0 and obs["tamper"] is True
