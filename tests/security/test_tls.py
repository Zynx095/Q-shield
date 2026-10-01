"""Phase 13: the gateway really serves HTTPS with a configured (self-signed dev) certificate."""
import socket
import ssl
import threading
import time

import httpx
import pytest
import uvicorn

from backend.api.app import create_app
from backend.config import Settings
from backend.devices.store import Store
from backend.security.tls import TlsConfigError, generate_dev_cert, tls_options
from tests.conftest import INGEST_TOKEN, OPERATOR_TOKEN


@pytest.fixture(scope="module")
def certs(tmp_path_factory):
    d = tmp_path_factory.mktemp("tls")
    generate_dev_cert(d / "gw.crt", d / "gw.key", ["localhost", "127.0.0.1"], days=1)
    return str(d / "gw.crt"), str(d / "gw.key")


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def https_gateway(certs):
    port = _free_port()
    app = create_app(Settings(db_path=":memory:"), store=Store(":memory:"), creds=object(),
                     operator_token=OPERATOR_TOKEN, ingest_token=INGEST_TOKEN)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                                           **tls_options(*certs)))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    yield port
    server.should_exit = True
    t.join(5)


def test_https_request_succeeds_with_pinned_dev_cert(https_gateway, certs):
    r = httpx.get(f"https://127.0.0.1:{https_gateway}/api/v1/operators/me", verify=certs[0],
                  headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"})
    assert r.status_code == 200 and r.json()["operator_id"] == "bootstrap-admin"
    assert r.http_version.startswith("HTTP/1")


def test_https_still_requires_operator_auth(https_gateway, certs):
    assert httpx.get(f"https://127.0.0.1:{https_gateway}/api/v1/devices", verify=certs[0]).status_code == 401


def test_untrusted_self_signed_cert_is_rejected_by_default_client(https_gateway):
    with pytest.raises(httpx.ConnectError):
        httpx.get(f"https://127.0.0.1:{https_gateway}/api/v1/devices")


def test_plain_http_to_tls_port_gets_no_api_response(https_gateway):
    try:
        r = httpx.get(f"http://127.0.0.1:{https_gateway}/api/v1/devices",
                      headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"}, timeout=3)
        assert r.status_code == 400            # uvicorn answers garbage TLS records with 400, never the API
    except httpx.HTTPError:
        pass


def test_tls_options_validation(certs, tmp_path):
    cert, key = certs
    assert tls_options(None, None) == {}
    assert tls_options(cert, key) == {"ssl_certfile": cert, "ssl_keyfile": key}
    with pytest.raises(TlsConfigError, match="BOTH"):
        tls_options(cert, None)
    with pytest.raises(TlsConfigError, match="not found"):
        tls_options(cert, str(tmp_path / "missing.key"))
    with pytest.raises(TlsConfigError, match="REQUIRE_TLS"):
        tls_options(None, None, require=True)
    other = tmp_path / "o"
    generate_dev_cert(other / "a.crt", other / "a.key", ["localhost"])
    with pytest.raises(TlsConfigError, match="cannot be loaded"):
        tls_options(cert, str(other / "a.key"))                 # mismatched pair
    bad = tmp_path / "bad.crt"
    bad.write_text("not a cert")
    with pytest.raises(TlsConfigError):
        tls_options(str(bad), key)


def test_dev_cert_is_self_signed_and_key_not_overwritten(certs):
    pem = open(certs[0]).read()
    der = ssl.PEM_cert_to_DER_cert(pem)
    from cryptography import x509
    c = x509.load_der_x509_certificate(der)
    assert c.issuer == c.subject and "self-signed" in c.subject.rfc4514_string()
    with pytest.raises(FileExistsError):
        generate_dev_cert(certs[0], certs[1], ["localhost"])
