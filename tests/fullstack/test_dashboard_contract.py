"""The dashboard talks only to real gateway routes, with the right methods, and renders API data safely.

The dashboard is native ES modules under dashboard/src (no build step). Every route it uses is declared in
dashboard/src/lib/api.js (ROUTES); the operator actions are the POST/PUT calls in dashboard/src/store.js.
"""
import re
from pathlib import Path

from tests.fullstack.conftest import quarantine_by_correlated_attack

DASH = Path(__file__).resolve().parents[2] / "dashboard"
SRC = DASH / "src"
API_JS = (SRC / "lib" / "api.js").read_text(encoding="utf-8")
STORE_JS = (SRC / "store.js").read_text(encoding="utf-8")
MODULES = {p.relative_to(DASH).as_posix(): p.read_text(encoding="utf-8") for p in SRC.rglob("*.js")}


def _app_routes(app):
    out = set()
    for r in app.routes:
        for m in getattr(r, "methods", ()) or ():
            out.add((m, re.sub(r"\{[^}]+\}", "X", r.path)))
    return out


def _declared_routes():
    """name -> normalised path, parsed from ROUTES in api.js."""
    out = {}
    for name, body in re.findall(r"^\s{2}(\w+): \([^)]*\) => ([`\"][^`\"]+[`\"]),", API_JS, re.M):
        path = re.sub(r"\$\{[^}]+\}", "X", body.strip("`\"")).split("?")[0]
        out[name] = path
    return out


def test_every_declared_route_exists_on_the_gateway(stack):
    declared = _declared_routes()
    assert len(declared) >= 18, declared
    paths = {p for _, p in _app_routes(stack.app)}
    for name, path in declared.items():
        assert path in paths, (name, path)


def test_operator_actions_use_the_right_methods(stack):
    declared, routes = _declared_routes(), _app_routes(stack.app)
    calls = re.findall(r"api\.(get|post|put)\(R\.(\w+)\(", STORE_JS)
    assert ("post", "recoveryStart") in calls and ("post", "recoveryAbort") in calls and ("put", "twinExpected") in calls
    for method, name in calls:
        assert (method.upper(), declared[name]) in routes, (method, name, declared[name])


def test_dashboard_is_served_as_es_modules(stack):
    index = stack.gw.get("/dashboard/")
    assert index.status_code == 200 and '<script type="module" src="src/main.js">' in index.text
    for path in ("src/main.js", "src/lib/api.js", "src/pages/overview.js"):
        r = stack.gw.get(f"/dashboard/{path}")
        assert r.status_code == 200 and "javascript" in r.headers["content-type"], path     # module MIME check
    assert stack.gw.get("/dashboard/styles/tokens.css").status_code == 200
    assert stack.gw.get("/dashboard/assets/fonts/archivo-latin-wdth-normal.woff2").status_code == 200   # offline-capable


def test_dashboard_never_injects_unescaped_markup_or_invents_data():
    # innerHTML is used only by the morph renderer (on html`` output, which escapes every value) and the toast,
    # which also renders html``. Everything else goes through html`` + render().
    users = {name for name, src in MODULES.items() if "innerHTML" in src}
    assert users == {"src/lib/morph.js", "src/main.js"}, users
    assert "innerHTML = String(html`" in MODULES["src/main.js"]
    for name, src in MODULES.items():
        assert "Math.random" not in src, f"{name}: no generated/fake values in the dashboard"
        assert "eval(" not in src and "new Function" not in src, name
        assert "localStorage" not in src, f"{name}: the operator token must not outlive the tab"
    assert "raw(" not in MODULES["src/pages/overview.js"], "pages must not bypass escaping"


def test_ambient_background_cannot_see_live_data():
    """The decorative background is built from constants only: no store, no API, so no token or key can reach it."""
    src = MODULES["src/components/ambient.js"]
    assert not re.search(r"^\s*import\b", src, re.M), "ambient.js must stay self-contained"
    for banned in ("fetch(", "XMLHttpRequest", "WebSocket", "qshield_operator_token"):
        assert banned not in src, banned
    index = (DASH / "index.html").read_text(encoding="utf-8")
    assert '<div id="ambient" aria-hidden="true"></div>' in index


def test_camera_preview_stays_in_the_browser():
    """The browser preview is local only: it must not send, record or capture frames. Signed observations come from
    the Python vision service, never from this page."""
    src = MODULES["src/components/camera.js"]
    for banned in ("fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "MediaRecorder", "captureStream",
                   "toDataURL", "toBlob", "drawImage", "getImageData", "ImageCapture"):
        assert banned not in src, banned
    assert not re.search(r"^\s*import\b", src, re.M), "camera.js reaches neither the store nor the API"
    assert "audio: false" in src


def test_vision_page_is_routed_labelled_and_releases_the_camera(stack):
    main, vision = MODULES["src/main.js"], MODULES["src/pages/vision.js"]
    assert 'vision: [vision, "Camera & vision"]' in main
    assert 'route: "vision"' in MODULES["src/components/shell.js"]
    assert '<div id="cam-mount" data-morph-skip></div>' in vision, "the refresh must never replace the <video>"
    assert "Local preview only." in vision and "not sent to the gateway" in vision
    assert 'if (route.name !== "vision") vision.release();' in main and main.count("vision.release()") >= 2
    assert stack.gw.get("/dashboard/src/pages/vision.js").status_code == 200
    assert stack.gw.get("/dashboard/src/components/camera.js").status_code == 200


def test_dashboard_action_sequence_against_the_gateway(stack):
    """Replays exactly the requests the dashboard's operator dialogs send (same paths, bodies, bearer header)."""
    quarantine_by_correlated_attack(stack)
    d = "DEVICE-001"
    exp = stack.op.get(f"/api/v1/devices/{d}/twin").json()["expected"]
    body = {**exp, "fw_version": "agent-0.1", "cfg_hash": "cfg-good-1"}               # Set known-good state
    assert stack.op.put(f"/api/v1/devices/{d}/twin/expected", json=body).json()["expected"]["capabilities"] == exp["capabilities"]
    r = stack.op.post(f"/api/v1/devices/{d}/recovery/start", json={"reason": "incident contained"})   # Start recovery
    assert r.status_code == 200 and stack.op.get(f"/api/v1/trust/{d}").json()["state"] == "RECOVERING"
    assert stack.op.put(f"/api/v1/devices/{d}/twin/expected", json=body).status_code == 409        # locked while verifying
    r = stack.op.post(f"/api/v1/devices/{d}/recovery/abort", json={"reason": "operator abort"})      # Abort recovery
    assert r.status_code == 200 and stack.op.get(f"/api/v1/trust/{d}").json()["state"] == "QUARANTINED"
    assert stack.op.get(f"/api/v1/devices/{d}/recovery").json()["current"]["status"] == "failed"   # what the refresh shows
    sysinfo = stack.op.get("/api/v1/system").json()                                    # thresholds the UI draws
    assert sysinfo["trust"]["quarantine_below"] == 50 and sysinfo["recovery"]["health_checks_required"] == 3
