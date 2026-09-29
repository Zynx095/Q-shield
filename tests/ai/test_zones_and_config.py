"""Zone classification and vision config validation."""
import pytest

from ai.vision.config import ConfigError, parse_config
from ai.vision.zones import Zone, ZoneError, ZoneSet, anchor_point, point_in_polygon
from backend.protocol.observation import ZoneKind

SQUARE = ((0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8))
TRIANGLE = ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))


def test_point_in_polygon_basic():
    assert point_in_polygon((0.5, 0.5), SQUARE)
    assert not point_in_polygon((0.1, 0.5), SQUARE)
    assert not point_in_polygon((0.5, 0.9), SQUARE)


def test_point_on_edge_and_vertex_counts_inside():
    assert point_in_polygon((0.2, 0.5), SQUARE)
    assert point_in_polygon((0.2, 0.2), SQUARE)


def test_concave_polygon():
    L = ((0, 0), (1, 0), (1, 0.3), (0.3, 0.3), (0.3, 1), (0, 1))
    assert point_in_polygon((0.1, 0.9), L)
    assert not point_in_polygon((0.8, 0.8), L)  # in the notch


def test_triangle():
    assert point_in_polygon((0.2, 0.2), TRIANGLE)
    assert not point_in_polygon((0.8, 0.8), TRIANGLE)


def test_anchor_points():
    box = (0.2, 0.2, 0.6, 0.8)
    assert anchor_point(box, "bottom_center") == (0.4, 0.8)
    assert anchor_point(box, "center") == (0.4, 0.5)
    with pytest.raises(ZoneError):
        anchor_point(box, "top")


def zs(anchor="bottom_center"):
    return ZoneSet([
        Zone("mon", ZoneKind.MONITORED, ((0, 0), (1, 0), (1, 1), (0, 1))),   # whole image
        Zone("restr", ZoneKind.RESTRICTED, ((0.5, 0), (1, 0), (1, 1), (0.5, 1))),
    ], anchor)


def test_classification_prefers_restricted_over_monitored_when_overlapping():
    assert zs().classify((0.6, 0.1, 0.8, 0.9)).name == "restr"
    assert zs().classify((0.1, 0.1, 0.3, 0.9)).name == "mon"


def test_classification_outside_all_zones_is_none():
    only = ZoneSet([Zone("r", ZoneKind.RESTRICTED, SQUARE)])
    assert only.classify((0.85, 0.85, 0.95, 0.95)) is None


def test_anchor_choice_changes_result():
    z = ZoneSet([Zone("floor", ZoneKind.RESTRICTED, ((0, 0.6), (1, 0.6), (1, 1), (0, 1)))], "bottom_center")
    box = (0.4, 0.2, 0.6, 0.9)  # tall box: feet in zone, center above it
    assert z.classify(box) is not None
    assert ZoneSet(z.zones, "center").classify(box) is None


def test_overlap_tie_broken_by_config_order():
    a = Zone("a", ZoneKind.MONITORED, SQUARE)
    b = Zone("b", ZoneKind.MONITORED, SQUARE)
    assert ZoneSet([a, b]).classify((0.4, 0.3, 0.6, 0.6)).name == "a"


@pytest.mark.parametrize("kwargs", [
    dict(name="", kind=ZoneKind.RESTRICTED, polygon=SQUARE),
    dict(name="bad name!", kind=ZoneKind.RESTRICTED, polygon=SQUARE),
    dict(name="z", kind=ZoneKind.RESTRICTED, polygon=((0, 0), (1, 1))),
    dict(name="z", kind=ZoneKind.RESTRICTED, polygon=((0, 0), (1, 0), (2, 1))),
    dict(name="z", kind=ZoneKind.RESTRICTED, polygon=((0, 0), (0.5, 0.5), (1, 1))),  # collinear: zero area
])
def test_invalid_zone_rejected(kwargs):
    with pytest.raises(ZoneError):
        Zone(**kwargs)


def test_zone_from_dict_rejects_unknown_kind_and_keys():
    with pytest.raises(ZoneError):
        Zone.from_dict({"name": "z", "kind": "secret", "polygon": [[0, 0], [1, 0], [1, 1]]})
    with pytest.raises(ZoneError):
        Zone.from_dict({"name": "z", "kind": "restricted", "polygon": [[0, 0], [1, 0], [1, 1]], "x": 1})


BASE = {"device_id": "DEVICE-001"}


def test_default_config_file_is_valid():
    from ai.vision.config import load_config
    cfg = load_config("config/vision.json")
    assert cfg.device_id == "DEVICE-001" and len(cfg.zones) == 2
    assert cfg.model.name == "yolo11n"


@pytest.mark.parametrize("patch", [
    {"device_id": ""}, {"device_id": "a b"}, {"unknown": 1},
    {"camera": {"target_fps": 0}}, {"camera": {"backend": "v4l9"}}, {"camera": {"width": 1}},
    {"camera": {"nope": 1}}, {"model": {"conf_threshold": 0}}, {"model": {"conf_threshold": 1.5}},
    {"model": {"classes_of_interest": []}}, {"model": {"imgsz": 4}},
    {"zone_anchor": "top"}, {"health": {"consecutive_frames": 0}}, {"emit": {"repeat_interval_s": 0}},
    {"zones": [{"name": "a", "kind": "restricted", "polygon": [[0, 0], [1, 0]]}]},
    {"zones": [{"name": "a", "kind": "restricted", "polygon": [[0, 0], [1, 0], [1, 1]]},
               {"name": "a", "kind": "monitored", "polygon": [[0, 0], [1, 0], [1, 1]]}]},
])
def test_invalid_config_rejected(patch):
    with pytest.raises(ConfigError):
        parse_config({**BASE, **patch})


def test_missing_device_id_and_non_object():
    with pytest.raises(ConfigError):
        parse_config({})
    with pytest.raises(ConfigError):
        parse_config([])


def test_unreadable_config_file(tmp_path):
    from ai.vision.config import load_config
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(ConfigError):
        load_config(bad)
