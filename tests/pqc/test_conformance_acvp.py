"""Known-answer conformance tests against NIST ACVP vectors (usnistgov/ACVP-Server, pinned commit).

Vectors are copied verbatim by scripts/fetch_acvp_vectors.py; see tests/vectors/pqc/MANIFEST.json for
the source URL, commit and SHA-256 of the source files. Everything runs through the PqcBackend
interface. Coverage limits (documented in pqc/README.md): keygen and signing are randomised in
this library, so ACVP keyGen/sigGen answers cannot be reproduced; verification, decapsulation and
key-validity checks are deterministic and are covered here.
"""
import hashlib
import json
from pathlib import Path

import pytest

from backend.security.pqc import PqcError, get_backend

VEC = Path(__file__).resolve().parents[1] / "vectors" / "pqc"
H = bytes.fromhex
truthy = lambda v: v in (True, "True", "true")  # noqa: E731


@pytest.fixture(scope="module")
def pqc():
    return get_backend("ML-KEM-768", "ML-DSA-65")


@pytest.fixture(scope="module")
def kem_vectors():
    return json.loads((VEC / "acvp_mlkem768.json").read_text())


@pytest.fixture(scope="module")
def dsa_vectors():
    return json.loads((VEC / "acvp_mldsa65_sigver.json").read_text())


def group(vectors, function):
    (g,) = [g for g in vectors["testGroups"] if g["function"] == function]
    return g["tests"]


def test_vector_provenance_recorded():
    m = json.loads((VEC / "MANIFEST.json").read_text())
    assert m["acvp_server_commit"] == "975de31eb83d87039ec88934fdc47d8c312b892d"
    for name, src in m["sources"].items():
        assert src["url"].startswith("https://raw.githubusercontent.com/usnistgov/ACVP-Server/975de31")
        assert len(src["sha256"]) == 64
        assert json.loads((VEC / name).read_text())["source_sha256"] == src["sha256"]


def test_vectors_are_for_the_profiles_we_use(kem_vectors, dsa_vectors):
    assert (kem_vectors["algorithm"], kem_vectors["revision"], kem_vectors["parameterSet"]) == ("ML-KEM", "FIPS203", "ML-KEM-768")
    assert (dsa_vectors["algorithm"], dsa_vectors["revision"], dsa_vectors["parameterSet"]) == ("ML-DSA", "FIPS204", "ML-DSA-65")


# ---------------- ML-KEM-768 ----------------

def test_mlkem768_decapsulation_kat(pqc, kem_vectors):
    tests = group(kem_vectors, "decapsulation")
    assert len(tests) == 10
    for t in tests:
        assert pqc.kem_decapsulate(H(t["dk"]), H(t["c"])) == H(t["k"]), f"tcId {t['tcId']}"


def test_mlkem768_encapsulation_group_ciphertexts_decapsulate_to_expected_secret(pqc, kem_vectors):
    """ACVP encapsulation AFT cases carry (dk, c, k): decapsulating NIST's ciphertext must give NIST's k."""
    tests = group(kem_vectors, "encapsulation")
    assert len(tests) == 25
    for t in tests:
        assert pqc.kem_decapsulate(H(t["dk"]), H(t["c"])) == H(t["k"]), f"tcId {t['tcId']}"


def test_mlkem768_encapsulation_key_check(pqc, kem_vectors):
    tests = group(kem_vectors, "encapsulationKeyCheck")
    assert any(truthy(t["testPassed"]) for t in tests) and any(not truthy(t["testPassed"]) for t in tests)
    for t in tests:
        if truthy(t["testPassed"]):
            pqc.kem_encapsulate(H(t["ek"]))
        else:
            with pytest.raises(PqcError):
                pqc.kem_encapsulate(H(t["ek"]))


def test_mlkem768_decapsulation_key_check(pqc, kem_vectors):
    tests = group(kem_vectors, "decapsulationKeyCheck")
    assert any(truthy(t["testPassed"]) for t in tests) and any(not truthy(t["testPassed"]) for t in tests)
    dummy_ct = bytes(pqc.info()["sizes_bytes"]["kem_ciphertext"])
    for t in tests:
        if truthy(t["testPassed"]):
            pqc.kem_decapsulate(H(t["dk"]), dummy_ct)
        else:
            with pytest.raises(PqcError):
                pqc.kem_decapsulate(H(t["dk"]), dummy_ct)


def test_mlkem768_generated_keys_follow_fips203_layout(pqc):
    """dk = dkPKE(1152) || ek(1184) || SHA3-256(ek)(32) || z(32)  (FIPS 203, Algorithm 16/ 'ML-KEM.KeyGen_internal')."""
    for _ in range(5):
        kp = pqc.kem_keygen()
        assert (len(kp.public_key), len(kp.secret_key)) == (1184, 2400)
        assert kp.secret_key[1152:1152 + 1184] == kp.public_key
        assert kp.secret_key[1152 + 1184:1152 + 1184 + 32] == hashlib.sha3_256(kp.public_key).digest()


# ---------------- ML-DSA-65 ----------------

def test_mldsa65_signature_verification_kat(pqc, dsa_vectors):
    (g,) = dsa_vectors["testGroups"]
    tests = g["tests"]
    assert len(tests) == 15
    n_valid = 0
    for t in tests:
        expected = truthy(t["testPassed"])
        got = pqc.verify(H(t["pk"]), H(t["message"]), H(t["signature"]), H(t["context"]))
        assert got is expected, f"tcId {t['tcId']} ({t.get('reason')})"
        n_valid += expected
    assert 0 < n_valid < len(tests)  # both accepting and rejecting cases exercised
