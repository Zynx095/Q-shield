"""Smoke tests for the PQC abstraction. Standards-conformance (KAT) tests are Phase 3."""
import pytest

from backend.security.pqc import PqcError, PqcryptoBackend, get_backend


@pytest.fixture(scope="module")
def pqc():
    return get_backend("ML-KEM-768", "ML-DSA-65")


def test_algorithms_reported(pqc):
    assert (pqc.kem_algorithm, pqc.sig_algorithm) == ("ML-KEM-768", "ML-DSA-65")


def test_kem_valid_key_establishment(pqc):
    kp = pqc.kem_keygen()
    ct, ss_sender = pqc.kem_encapsulate(kp.public_key)
    assert len(ss_sender) == 32
    assert pqc.kem_decapsulate(kp.secret_key, ct) == ss_sender


def test_kem_corrupted_ciphertext_gives_different_secret(pqc):
    kp = pqc.kem_keygen()
    ct, ss = pqc.kem_encapsulate(kp.public_key)
    bad = bytes([ct[0] ^ 1]) + ct[1:]
    assert pqc.kem_decapsulate(kp.secret_key, bad) != ss


def test_kem_wrong_key_gives_different_secret(pqc):
    a, b = pqc.kem_keygen(), pqc.kem_keygen()
    ct, ss = pqc.kem_encapsulate(a.public_key)
    assert pqc.kem_decapsulate(b.secret_key, ct) != ss


def test_signature_valid(pqc):
    kp = pqc.sig_keygen()
    msg = b"temperature=27.4"
    assert pqc.verify(kp.public_key, msg, pqc.sign(kp.secret_key, msg)) is True


def test_signature_modified_message_rejected(pqc):
    kp = pqc.sig_keygen()
    sig = pqc.sign(kp.secret_key, b"temperature=27.4")
    assert pqc.verify(kp.public_key, b"temperature=97.4", sig) is False


def test_signature_wrong_key_rejected(pqc):
    a, b = pqc.sig_keygen(), pqc.sig_keygen()
    sig = pqc.sign(a.secret_key, b"m")
    assert pqc.verify(b.public_key, b"m", sig) is False


def test_signature_corrupted_or_truncated_rejected(pqc):
    kp = pqc.sig_keygen()
    sig = pqc.sign(kp.secret_key, b"m")
    assert pqc.verify(kp.public_key, b"m", bytes([sig[0] ^ 1]) + sig[1:]) is False
    assert pqc.verify(kp.public_key, b"m", sig[:-1]) is False
    assert pqc.verify(kp.public_key, b"m", b"") is False


def test_unsupported_algorithm_refused():
    with pytest.raises(PqcError):
        PqcryptoBackend("ML-KEM-999", "ML-DSA-65")
