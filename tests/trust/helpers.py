"""Builders for trust-engine tests."""
import itertools

from backend.trust.engine import TrustEngine
from backend.trust.model import Auth, Kind, Signal

T0 = 1_700_000_000.0
_ids = itertools.count(1)


def sig(kind, t, *, auth=Auth.DEVICE_HMAC, device="D1", sid=None, confidence=None, value=None, prov=""):
    return Signal(sid or f"s{next(_ids)}", device, kind, t, auth, confidence=confidence, value=value or {}, source_ref="test", provenance=prov)


def evidence(t, **kw):
    return sig(Kind.DEVICE_EVIDENCE, t, **kw)


def tamper(t, active=True, **kw):
    return sig(Kind.PHYSICAL_TAMPER, t, value={"active": active}, **kw)


def sensor(t, active=True, **kw):
    return sig(Kind.SENSOR_OUT_OF_RANGE, t, value={"active": active}, **kw)


def integrity(t, mismatch=True, **kw):
    return sig(Kind.INTEGRITY_MISMATCH, t, value={"mismatch": mismatch}, **kw)


def visual(t, c, auth=Auth.SIGNER_MLDSA, zone="z", obj="person", **kw):
    return sig(Kind.VISUAL_RULE_VIOLATION, t, auth=auth, confidence=c, value={"zone": zone, "object": obj}, **kw)


def unauth(kind, t, **kw):
    return sig(kind, t, auth=Auth.UNAUTHENTICATED, **kw)


def engine(cfg=None, device="D1"):
    e = TrustEngine(cfg)
    e.track(device)
    return e


def run(e, *signals):
    """Apply signals; return the last emitted change (or None) and all changes."""
    out = []
    for s in signals:
        out += e.apply(s)
    return (out[-1] if out else None), out


def healthy(e, start=T0, n=3, step=5.0, device="D1"):
    """A healthy authenticated device history: evidence + tamper=false, so identity/network/physical are available."""
    t = start
    for _ in range(n):
        e.apply(evidence(t, device=device))
        e.apply(tamper(t, False, device=device))
        t += step
    return t - step


def score(e, t, device="D1"):
    return e.snapshot(device, t)["score"]
