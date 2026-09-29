"""Full-stack fixture: real gateway app with trust engine, enforcement, digital twin, ML-DSA evidence chain and
recovery orchestrator, driven over HTTP (TestClient) with a controllable clock."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from attack_simulation import AttackSimulator, SignerHandle
from backend.api.app import create_app
from backend.config import Settings
from backend.evidence.chain import EvidenceChain, EvidenceSigner
from backend.recovery.orchestrator import RecoveryConfig, RecoveryOrchestrator
from backend.trust.config import TrustConfig
from backend.trust.service import TrustService
from backend.twin.twin import DigitalTwin
from device_agent.agent import DeviceAgent
from tests.conftest import INGEST_TOKEN, OPERATOR_TOKEN

EXPECTED = {"fw_version": "agent-0.1", "cfg_hash": "cfg-good-1", "capabilities": ["tamper", "temperature", "vibration"],
            "sensor_ranges": {"temperature_c": [-20, 60]}}


@pytest.fixture(scope="session")
def evidence_keys(pqc_backend):
    kp = pqc_backend.sig_keygen()
    return kp


@pytest.fixture
def stack(store, creds, clock, device_secret, pqc_world, pqc_backend, evidence_keys):
    twin = DigitalTwin(store)
    evidence = EvidenceChain(store, EvidenceSigner(pqc_backend, evidence_keys.secret_key, evidence_keys.public_key,
                                                   "gateway-evidence-1"))
    trust = TrustService(store, TrustConfig(), clock=clock, twin=twin)
    recovery = RecoveryOrchestrator(store, trust, twin, clock=clock, cfg=RecoveryConfig(health_checks_required=3,
                                                                                         deadline_s=900, ramp_timeout_s=7200))
    app = create_app(Settings(db_path=":memory:"), clock=clock, store=store, creds=creds, operator_token=OPERATOR_TOKEN,
                     ingest_token=INGEST_TOKEN, pqc=pqc_world.gateway, trust=trust, twin=twin, evidence=evidence,
                     recovery=recovery)
    gw = TestClient(app)
    op = TestClient(app, headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"})
    agent = DeviceAgent("DEVICE-001", device_secret, gw)
    sim = AttackSimulator(gw, op, "DEVICE-001", agent=agent,
                          signer=SignerHandle(pqc_backend, pqc_world.signers["vision-1"], "vision-1"), clock=clock)
    return SimpleNamespace(store=store, clock=clock, twin=twin, evidence=evidence, trust=trust, recovery=recovery,
                           app=app, gw=gw, op=op, agent=agent, sim=sim, secret=device_secret)


def trusted(s):
    """Register + clean telemetry + expected twin state -> TRUSTED at 100."""
    assert s.op.put("/api/v1/devices/DEVICE-001/twin/expected", json=EXPECTED).status_code == 200
    s.agent.cfg_hash = "cfg-good-1"
    assert s.agent.register().status_code == 200
    assert s.agent.telemetry().status_code == 200
    t = s.op.get("/api/v1/trust/DEVICE-001").json()
    assert t["state"] == "TRUSTED" and t["score"] == 100
    return t


def state(s, dev="DEVICE-001"):
    return s.op.get(f"/api/v1/trust/{dev}").json().get("state")


def quarantine_by_correlated_attack(s):
    trusted(s)
    res = s.sim.correlated()
    assert state(s) == "QUARANTINED", res.to_dict()
    return res
