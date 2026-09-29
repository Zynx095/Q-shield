import secrets

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config import Settings
from backend.devices.store import Store
from backend.protocol.envelope import AUTH_HMAC
from backend.security.credentials import EncryptedCredentialStore

OPERATOR_TOKEN = "test-operator-token-" + "o" * 24
INGEST_TOKEN = "test-ingest-token-" + "i" * 24
MASTER_KEY = bytes(range(32))


class FakeClock:
    def __init__(self, t: float = 1_700_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def creds(store):
    return EncryptedCredentialStore(store, MASTER_KEY)


@pytest.fixture
def device_secret(store, creds, clock):
    secret = secrets.token_bytes(32)
    store.enroll_device("DEVICE-001", AUTH_HMAC, clock())
    creds.put("DEVICE-001", secret)
    return secret


@pytest.fixture
def app(store, creds, clock, device_secret):
    settings = Settings(db_path=":memory:", device_offline_timeout_s=15.0)
    return create_app(settings, clock=clock, store=store, creds=creds,
                      operator_token=OPERATOR_TOKEN, ingest_token=INGEST_TOKEN)


@pytest.fixture
def client(app):
    """Operator-authenticated client. Device endpoints ignore the bearer header (they use
    the HMAC envelope only), so device posts and operator reads can share this client."""
    return TestClient(app, headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"})


@pytest.fixture
def anon_client(app):
    return TestClient(app)


@pytest.fixture
def ingest_client(app):
    return TestClient(app, headers={"Authorization": f"Bearer {INGEST_TOKEN}"})


# ---------------- Phase 3: PQC fixtures ----------------
from backend.security.keystore import KIND_KEM, KIND_SIG, PqcKeyStore, kem_kek, signer_kek  # noqa: E402
from backend.security.pqc import get_backend  # noqa: E402
from backend.security.pqc_gateway import PqcGateway  # noqa: E402


@pytest.fixture(scope="session")
def pqc_backend():
    return get_backend("ML-KEM-768", "ML-DSA-65")


class PqcWorld:
    """Gateway with a KEM key and two enrolled vision signers (vision-1 for DEVICE-001 only)."""


@pytest.fixture
def pqc_world(tmp_path, store, clock, pqc_backend, device_secret):
    w = PqcWorld()
    w.backend, w.dir, w.master = pqc_backend, tmp_path / "pqc", MASTER_KEY
    w.ks = PqcKeyStore(w.dir)
    w.kem_rec = w.ks.create(pqc_backend, KIND_KEM, "gateway-kem-1", kem_kek(MASTER_KEY, "gateway-kem-1"))
    w.signers = {}
    for sid in ("vision-1", "vision-2"):
        kek = signer_kek(MASTER_KEY, sid)
        rec = w.ks.create(pqc_backend, KIND_SIG, sid, kek)
        store.add_signer(sid, rec.algorithm, rec.public_key, "usb_webcam", ["DEVICE-001"], clock())
        w.signers[sid] = w.ks.load_private(pqc_backend, sid, kek)[1]
    store.enroll_device("DEVICE-002", "hmac-sha256-psk", clock())  # exists, but no signer is authorised for it
    w.gateway = PqcGateway.from_keystore(store, pqc_backend, w.ks, MASTER_KEY, ["gateway-kem-1"],
                                         clock=clock, max_skew_s=300.0, session_ttl_s=3600)
    return w


@pytest.fixture
def pqc_app(store, creds, clock, device_secret, pqc_world):
    return create_app(Settings(db_path=":memory:"), clock=clock, store=store, creds=creds,
                      operator_token=OPERATOR_TOKEN, ingest_token=INGEST_TOKEN, pqc=pqc_world.gateway)


@pytest.fixture
def pqc_client(pqc_app):
    """Unauthenticated client: the signed endpoints must work on signature alone."""
    return TestClient(pqc_app)


@pytest.fixture
def pqc_operator(pqc_app):
    return TestClient(pqc_app, headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"})
