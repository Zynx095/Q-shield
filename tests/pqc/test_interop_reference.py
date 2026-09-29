"""Interoperability with independent pure-Python reference implementations (kyber-py, dilithium-py).

These libraries are used ONLY as a test cross-check (they state they are not for production).
They first have to agree with the NIST vectors themselves, so the cross-check is meaningful.
"""
import json
from pathlib import Path

import pytest

from backend.security.pqc import get_backend

kyber = pytest.importorskip("kyber_py.ml_kem")
dilithium = pytest.importorskip("dilithium_py.ml_dsa")
REF_KEM, REF_DSA = kyber.ML_KEM_768, dilithium.ML_DSA_65

VEC = Path(__file__).resolve().parents[1] / "vectors" / "pqc"
H = bytes.fromhex


@pytest.fixture(scope="module")
def pqc():
    return get_backend()


def test_reference_kem_agrees_with_nist_decapsulation_vectors():
    v = json.loads((VEC / "acvp_mlkem768.json").read_text())
    (g,) = [g for g in v["testGroups"] if g["function"] == "decapsulation"]
    for t in g["tests"]:
        assert REF_KEM.decaps(H(t["dk"]), H(t["c"])) == H(t["k"])


def test_reference_dsa_agrees_with_nist_verification_vectors():
    v = json.loads((VEC / "acvp_mldsa65_sigver.json").read_text())
    for t in v["testGroups"][0]["tests"]:
        expected = t["testPassed"] in (True, "True")
        try:
            got = bool(REF_DSA.verify(H(t["pk"]), H(t["message"]), H(t["signature"]), ctx=H(t["context"])))
        except Exception:
            got = False
        assert got is expected, t["tcId"]


def test_kem_library_encaps_reference_decaps(pqc):
    ek, dk = REF_KEM.keygen()
    ct, ss = pqc.kem_encapsulate(ek)
    assert REF_KEM.decaps(dk, ct) == ss


def test_kem_reference_encaps_library_decaps(pqc):
    kp = pqc.kem_keygen()
    ss, ct = REF_KEM.encaps(kp.public_key)
    assert pqc.kem_decapsulate(kp.secret_key, ct) == ss


def test_dsa_library_signs_reference_verifies(pqc):
    pk, sk = REF_DSA.keygen()
    del pk
    kp = pqc.sig_keygen()
    sig = pqc.sign(kp.secret_key, b"hello", b"ctx")
    assert REF_DSA.verify(kp.public_key, b"hello", sig, ctx=b"ctx") is True
    assert REF_DSA.verify(kp.public_key, b"hellO", sig, ctx=b"ctx") is False
    assert REF_DSA.verify(kp.public_key, b"hello", sig, ctx=b"other") is False


def test_dsa_reference_signs_library_verifies(pqc):
    pk, sk = REF_DSA.keygen()
    sig = REF_DSA.sign(sk, b"hello", ctx=b"ctx")
    assert pqc.verify(pk, b"hello", sig, b"ctx") is True
    assert pqc.verify(pk, b"hellO", sig, b"ctx") is False
    assert pqc.verify(pk, b"hello", sig, b"other") is False
