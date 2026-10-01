"""The dashboard's operator actions call real gateway routes with the right methods (no fake frontend state)."""
import re
from pathlib import Path

from tests.fullstack.conftest import quarantine_by_correlated_attack

JS = (Path(__file__).resolve().parents[2] / "dashboard" / "app.js").read_text(encoding="utf-8")
HTML = (Path(__file__).resolve().parents[2] / "dashboard" / "index.html").read_text(encoding="utf-8")


def _routes(app):
    out = set()
    for r in app.routes:
        for m in getattr(r, "methods", ()) or ():
            out.add((m, re.sub(r"\{[^}]+\}", "X", r.path)))
    return out


def test_every_dashboard_action_targets_an_existing_operator_route(stack):
    calls = re.findall(r'act\("(\w+)", `([^`]+)`', JS)
    assert len(calls) == 3
    routes = _routes(stack.app)
    for method, tmpl in calls:
        path = re.sub(r"\$\{[^}]+\}", "X", tmpl)
        assert (method, path) in routes, (method, path)


def test_dashboard_has_action_controls_and_is_served(stack):
    for el in ("btn-start", "btn-abort", "btn-twin", "exp-fw", "exp-cfg", "act-reason", "act-msg"):
        assert f'id="{el}"' in HTML
    assert stack.gw.get("/dashboard/").status_code == 200
    norm = lambda t: t.replace(chr(13), "")  # noqa: E731
    assert norm(stack.gw.get("/dashboard/app.js").text) == norm(JS)


def test_dashboard_action_sequence_against_the_gateway(stack):
    """Replays exactly the requests the dashboard buttons send (same paths, bodies, bearer header)."""
    quarantine_by_correlated_attack(stack)
    d = "DEVICE-001"
    exp = stack.op.get(f"/api/v1/devices/{d}/twin").json()["expected"]
    body = {**exp, "fw_version": "agent-0.1", "cfg_hash": "cfg-good-1"}               # SAVE EXPECTED STATE
    assert stack.op.put(f"/api/v1/devices/{d}/twin/expected", json=body).json()["expected"]["capabilities"] == exp["capabilities"]
    r = stack.op.post(f"/api/v1/devices/{d}/recovery/start", json={"reason": "incident contained"})   # START
    assert r.status_code == 200 and stack.op.get(f"/api/v1/trust/{d}").json()["state"] == "RECOVERING"
    assert stack.op.put(f"/api/v1/devices/{d}/twin/expected", json=body).status_code == 409        # frozen
    r = stack.op.post(f"/api/v1/devices/{d}/recovery/abort", json={"reason": "operator abort"})      # ABORT
    assert r.status_code == 200 and stack.op.get(f"/api/v1/trust/{d}").json()["state"] == "QUARANTINED"
    assert stack.op.get(f"/api/v1/devices/{d}/recovery").json()["current"]["status"] == "failed"   # what refresh shows
