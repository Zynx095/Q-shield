"""Configurable image zones and detection-to-zone classification.

Zones are polygons in normalized image coordinates (0..1, origin top-left). A detection is
assigned to a zone by testing one anchor point of its bounding box (bottom-center by
default, which approximates where a person stands; or the box center). Where zones overlap
the most sensitive kind wins (restricted over monitored), then config order.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from backend.protocol.observation import ZoneKind

Point = tuple[float, float]
_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_PRIORITY = {ZoneKind.RESTRICTED: 0, ZoneKind.MONITORED: 1}


class ZoneError(ValueError):
    pass


@dataclass(frozen=True)
class Zone:
    name: str
    kind: ZoneKind
    polygon: tuple[Point, ...]

    def __post_init__(self) -> None:
        if not _NAME.match(self.name):
            raise ZoneError(f"invalid zone name {self.name!r}")
        if len(self.polygon) < 3:
            raise ZoneError(f"zone {self.name}: polygon needs at least 3 points")
        for x, y in self.polygon:
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ZoneError(f"zone {self.name}: point ({x}, {y}) outside 0..1")
        if _area(self.polygon) == 0.0:
            raise ZoneError(f"zone {self.name}: polygon has zero area")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Zone":
        extra = set(d) - {"name", "kind", "polygon"}
        if extra:
            raise ZoneError(f"unknown zone keys {sorted(extra)}")
        try:
            kind = ZoneKind(d["kind"])
        except ValueError:
            raise ZoneError(f"zone kind must be one of {[k.value for k in ZoneKind]}") from None
        return cls(d["name"], kind, tuple((float(x), float(y)) for x, y in d["polygon"]))

    def contains(self, point: Point) -> bool:
        return point_in_polygon(point, self.polygon)


def _area(poly: Sequence[Point]) -> float:
    s = 0.0
    for i, (x1, y1) in enumerate(poly):
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def point_in_polygon(p: Point, poly: Sequence[Point]) -> bool:
    """Ray casting; points on an edge count as inside."""
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        # on-edge test
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if abs(cross) < 1e-12 and min(x1, x2) - 1e-12 <= x <= max(x1, x2) + 1e-12 \
                and min(y1, y2) - 1e-12 <= y <= max(y1, y2) + 1e-12:
            return True
        if (y1 > y) != (y2 > y):
            x_int = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_int:
                inside = not inside
    return inside


def anchor_point(box: tuple[float, float, float, float], anchor: str) -> Point:
    x1, y1, x2, y2 = box
    if anchor == "bottom_center":
        return ((x1 + x2) / 2.0, y2)
    if anchor == "center":
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    raise ZoneError(f"unknown anchor {anchor!r}")


class ZoneSet:
    def __init__(self, zones: Sequence[Zone], anchor: str = "bottom_center"):
        self.zones = tuple(zones)
        self.anchor = anchor

    def classify(self, box: tuple[float, float, float, float]) -> Zone | None:
        """Zone containing the box's anchor point, most sensitive first; None if outside all."""
        p = anchor_point(box, self.anchor)
        hits = [(i, z) for i, z in enumerate(self.zones) if z.contains(p)]
        if not hits:
            return None
        return min(hits, key=lambda h: (_PRIORITY[h[1].kind], h[0]))[1]
