"""Run the gateway:  python -m backend.main"""
import uvicorn

from backend.api.app import create_app
from backend.config import Settings
from backend.devices.store import Store
from backend.evidence.chain import EvidenceChain, EvidenceSigner
from backend.recovery.orchestrator import RecoveryOrchestrator
from backend.security.credentials import load_or_create_master_key
from backend.security.keystore import KIND_SIG, PqcKeyStore, signer_kek
from backend.security.pqc import get_backend
from backend.security.pqc_gateway import PqcGateway
from backend.security.tls import TlsConfigError, tls_options
from backend.trust.config import TrustConfig
from backend.trust.service import TrustService
from backend.twin.twin import DigitalTwin

EVIDENCE_KEY_ID = "gateway-evidence-1"


def build_pqc(settings: Settings, store: Store) -> PqcGateway | None:
    if not settings.pqc_enabled:
        return None
    master = load_or_create_master_key(settings.keys_dir, settings.master_key_hex)
    return PqcGateway.from_keystore(
        store, get_backend(settings.pqc_kem_algorithm, settings.pqc_sig_algorithm),
        PqcKeyStore(f"{settings.keys_dir}/pqc"), master, list(settings.pqc_gateway_kem_key_ids),
        max_skew_s=settings.pqc_max_skew_s, session_ttl_s=settings.pqc_session_ttl_s)


def build_evidence(settings: Settings, store: Store) -> EvidenceChain:
    """ML-DSA-signed evidence chain. The gateway evidence key is created on first start (sealed under the master key,
    like every other PQC key); with PQC disabled the chain is hash-linked but explicitly reported as UNSIGNED."""
    if not settings.pqc_enabled:
        return EvidenceChain(store, None)
    backend = get_backend(settings.pqc_kem_algorithm, settings.pqc_sig_algorithm)
    master = load_or_create_master_key(settings.keys_dir, settings.master_key_hex)
    ks, kek = PqcKeyStore(f"{settings.keys_dir}/pqc"), signer_kek(master, EVIDENCE_KEY_ID)
    if not ks.exists(EVIDENCE_KEY_ID):
        ks.create(backend, KIND_SIG, EVIDENCE_KEY_ID, kek)
    rec, sk = ks.load_private(backend, EVIDENCE_KEY_ID, kek)
    return EvidenceChain(store, EvidenceSigner(backend, sk, rec.public_key, EVIDENCE_KEY_ID))


def build_services(settings: Settings, store: Store) -> dict:
    """Trust + twin + evidence + recovery (empty when TRUST_ENABLED=false: Phase 1-3 behaviour, no enforcement)."""
    if not settings.trust_enabled:
        return {}
    twin = DigitalTwin(store)
    trust = TrustService(store, TrustConfig.load(settings.trust_config_path), twin=twin)
    return {"trust": trust, "twin": twin, "evidence": build_evidence(settings, store),
            "recovery": RecoveryOrchestrator(store, trust, twin)}


def main() -> None:
    settings = Settings.load()
    store = Store(settings.db_path)
    try:
        pqc = build_pqc(settings, store)
        services = build_services(settings, store)
    except Exception as e:  # missing/corrupt PQC keys: say what to do, do not start half-secured
        raise SystemExit(f"PQC is enabled but a gateway key cannot be loaded: {e}\n"
                         "Run: python scripts/pqc_provision.py init-gateway   (or set PQC_ENABLED=false)")
    try:
        tls = tls_options(settings.tls_cert, settings.tls_key, settings.require_tls)
    except TlsConfigError as e:
        raise SystemExit(f"TLS configuration error: {e}. Development cert: python scripts/gen_dev_cert.py")
    if tls:
        print(f"Q-SHIELD gateway: HTTPS on {settings.host}:{settings.port} (cert {settings.tls_cert})")
    else:
        print("WARNING: Q-SHIELD gateway in development HTTP mode: operator/ingest tokens travel in CLEARTEXT. "
              "Set QSHIELD_TLS_CERT/QSHIELD_TLS_KEY (python scripts/gen_dev_cert.py) for HTTPS.")
    if settings.allow_shared_operator_token:
        print("NOTE: the shared operator token is enabled as 'bootstrap-admin'. Create named operators "
              "(python scripts/operators.py create ...) and set ALLOW_SHARED_OPERATOR_TOKEN=false.")
    uvicorn.run(create_app(settings, store=store, pqc=pqc, **services), host=settings.host, port=settings.port, **tls)


if __name__ == "__main__":
    main()
