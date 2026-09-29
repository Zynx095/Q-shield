"""Production wiring: backend.main builds trust + twin + signed evidence + recovery from Settings."""
from backend.config import Settings
from backend.devices.store import Store
from backend.main import EVIDENCE_KEY_ID, build_services


def test_build_services_creates_signed_evidence_key_once(tmp_path):
    s = Settings(db_path=":memory:", keys_dir=str(tmp_path), pqc_enabled=True, master_key_hex="11" * 32)
    store = Store(":memory:")
    svc = build_services(s, store)
    assert set(svc) == {"trust", "twin", "evidence", "recovery"}
    assert svc["trust"].twin is svc["twin"]
    assert (tmp_path / "pqc" / f"{EVIDENCE_KEY_ID}.pub.json").exists()
    svc["evidence"].append_event("boot", {}, ts=1.0)
    assert svc["evidence"].verify_chain().signed
    again = build_services(s, store)                   # second start reuses the existing key
    assert again["evidence"].verify_chain().ok


def test_trust_disabled_means_no_enforcement_services():
    assert build_services(Settings(db_path=":memory:", trust_enabled=False), Store(":memory:")) == {}


def test_pqc_disabled_gives_unsigned_but_linked_chain(tmp_path):
    svc = build_services(Settings(db_path=":memory:", keys_dir=str(tmp_path), pqc_enabled=False), Store(":memory:"))
    svc["evidence"].append_event("boot", {}, ts=1.0)
    v = svc["evidence"].verify_chain()
    assert v.ok and not v.signed
