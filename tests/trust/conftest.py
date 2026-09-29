import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config import Settings
from backend.trust.config import TrustConfig
from backend.trust.service import TrustService
from tests.conftest import INGEST_TOKEN, OPERATOR_TOKEN


@pytest.fixture
def trust_cfg():
    return TrustConfig()


@pytest.fixture
def trust(store, clock, trust_cfg):
    return TrustService(store, trust_cfg, clock=clock)


@pytest.fixture
def tapp(store, creds, clock, device_secret, pqc_world, trust):
    return create_app(Settings(db_path=":memory:"), clock=clock, store=store, creds=creds, operator_token=OPERATOR_TOKEN,
                      ingest_token=INGEST_TOKEN, pqc=pqc_world.gateway, trust=trust)


@pytest.fixture
def tc(tapp):
    """Unauthenticated client (device + signed endpoints need no bearer)."""
    return TestClient(tapp)


@pytest.fixture
def top(tapp):
    return TestClient(tapp, headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"})


@pytest.fixture
def ingest(tapp):
    return TestClient(tapp, headers={"Authorization": f"Bearer {INGEST_TOKEN}"})
