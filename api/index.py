"""Vercel serverless entrypoint. Vercel's filesystem is read-only except /tmp, so the demo database and
PQC keys live there and are re-created on each cold start (demo state is not persistent)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/qshield.db")
os.environ.setdefault("KEYS_DIR", "/tmp/keys")

from backend.config import Settings  # noqa: E402
from backend.devices.store import Store  # noqa: E402
from backend.main import build_pqc, build_services  # noqa: E402
from backend.api.app import create_app  # noqa: E402
from backend.security.credentials import load_or_create_master_key  # noqa: E402
from backend.security.keystore import KIND_KEM, PqcKeyStore, kem_kek  # noqa: E402
from backend.security.pqc import get_backend  # noqa: E402

settings = Settings.load()
store = Store(settings.db_path)
if settings.pqc_enabled:  # provision the gateway KEM key on cold start (same as scripts/pqc_provision.py init-gateway)
    backend = get_backend(settings.pqc_kem_algorithm, settings.pqc_sig_algorithm)
    ks = PqcKeyStore(Path(settings.keys_dir) / "pqc")
    master = load_or_create_master_key(settings.keys_dir, settings.master_key_hex)
    for kid in settings.pqc_gateway_kem_key_ids:
        if not ks.exists(kid):
            ks.create(backend, KIND_KEM, kid, kem_kek(master, kid))
app = create_app(settings, store=store, pqc=build_pqc(settings, store), **build_services(settings, store))
