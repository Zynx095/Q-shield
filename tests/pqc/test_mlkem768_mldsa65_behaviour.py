"""Behavioural tests for ML-KEM-768 and ML-DSA-65 through the PqcBackend interface."""
import pytest

from backend.security.pqc import PqcError, get_backend


@pytest.fixture(scope="module")
def pqc():
    return get_backend("ML-KEM-768", "ML-DSA-65")


# ---------------- ML-KEM-768 ----------------

def test_kem_sizes_match_fips203(pqc):
    s = pqc.info()["sizes_bytes"]
    assert (s["kem_public_key"], s["kem_secret_key"], s["kem_ciphertext"], s["kem_shared_secret"]) == (1184, 2400, 1088, 32)


def test_kem_keygen_encaps_decaps_matching_secret(pqc):
    kp = pqc.kem_keygen()
    ct, ss = pqc.kem_encapsulate(kp.public_key)
    assert len(ct) == 1088 and len(ss) == 32
    assert pqc.kem_decapsulate(kp.secret_key, ct) == ss


def test_kem_decapsulation_is_deterministic(pqc):
    kp = pqc.kem_keygen()
    ct, _ = pqc.kem_encapsulate(kp.public_key)
    assert pqc.kem_decapsulate(kp.secret_key, ct) == pqc.kem_decapsulate(kp.secret_key, ct)


@pytest.mark.parametrize("pos", [0, 1, 500, 1000, 1086, 1087])
def test_kem_modified_ciphertext_yields_different_secret(pqc, pos):
    kp = pqc.kem_keygen()
    ct, ss = pqc.kem_encapsulate(kp.public_key)
    bad = bytearray(ct)
    bad[pos] ^= 0x01
    out = pqc.kem_decapsulate(kp.secret_key, bytes(bad))
    assert len(out) == 32 and out != ss  # implicit rejection: no error, unrelated secret


def test_kem_wrong_private_key_yields_different_secret(pqc):
    a, b = pqc.kem_keygen(), pqc.kem_keygen()
    ct, ss = pqc.kem_encapsulate(a.public_key)
    assert pqc.kem_decapsulate(b.secret_key, ct) != ss


@pytest.mark.parametrize("bad_ct", [b"", b"\x00" * 1087, b"\x00" * 1089, b"\x00" * 32, None, "text", 12])
def test_kem_malformed_ciphertext_rejected(pqc, bad_ct):
    kp = pqc.kem_keygen()
    with pytest.raises(PqcError):
        pqc.kem_decapsulate(kp.secret_key, bad_ct)


@pytest.mark.parametrize("bad_pk", [b"", b"\x00" * 1183, b"\x00" * 1185, None])
def test_kem_malformed_public_key_rejected(pqc, bad_pk):
    with pytest.raises(PqcError):
        pqc.kem_encapsulate(bad_pk)


def test_kem_malformed_secret_key_rejected(pqc):
    kp = pqc.kem_keygen()
    ct, _ = pqc.kem_encapsulate(kp.public_key)
    for bad in (b"", kp.secret_key[:-1], kp.secret_key + b"\x00", None):
        with pytest.raises(PqcError):
            pqc.kem_decapsulate(bad, ct)


def test_kem_repeated_independent_operations(pqc):
    pubs, cts, secrets_ = set(), set(), set()
    kp = pqc.kem_keygen()
    for _ in range(25):
        k = pqc.kem_keygen()
        pubs.add(k.public_key)
        ct, ss = pqc.kem_encapsulate(k.public_key)
        assert pqc.kem_decapsulate(k.secret_key, ct) == ss
        secrets_.add(ss)
        ct2, ss2 = pqc.kem_encapsulate(kp.public_key)  # same recipient key, fresh randomness each time
        assert pqc.kem_decapsulate(kp.secret_key, ct2) == ss2
        cts.add(ct2)
        secrets_.add(ss2)
    assert len(pubs) == 25 and len(cts) == 25 and len(secrets_) == 50


# ---------------- ML-DSA-65 ----------------

def test_dsa_sizes_match_fips204(pqc):
    s = pqc.info()["sizes_bytes"]
    assert (s["sig_public_key"], s["sig_secret_key"], s["signature"]) == (1952, 4032, 3309)


def test_dsa_keygen_sign_verify(pqc):
    kp = pqc.sig_keygen()
    sig = pqc.sign(kp.secret_key, b"observation")
    assert len(sig) == 3309 and pqc.verify(kp.public_key, b"observation", sig) is True


@pytest.mark.parametrize("msg", [b"", b"x", b"\x00" * 10_000, bytes(range(256)) * 1000],
                         ids=["empty", "1-byte", "10KB", "256KB"])
def test_dsa_message_sizes(pqc, msg):
    kp = pqc.sig_keygen()
    assert pqc.verify(kp.public_key, msg, pqc.sign(kp.secret_key, msg)) is True


def test_dsa_modified_message_rejected(pqc):
    kp = pqc.sig_keygen()
    msg = b"temperature=27.4;tamper=false"
    sig = pqc.sign(kp.secret_key, msg)
    for i in range(len(msg)):
        bad = bytearray(msg)
        bad[i] ^= 0x01
        assert pqc.verify(kp.public_key, bytes(bad), sig) is False
    assert pqc.verify(kp.public_key, msg + b"!", sig) is False
    assert pqc.verify(kp.public_key, msg[:-1], sig) is False


@pytest.mark.parametrize("pos", [0, 1, 100, 1000, 2000, 3000, 3307, 3308])
def test_dsa_modified_signature_rejected(pqc, pos):
    kp = pqc.sig_keygen()
    sig = bytearray(pqc.sign(kp.secret_key, b"m"))
    sig[pos] ^= 0x01
    assert pqc.verify(kp.public_key, b"m", bytes(sig)) is False


def test_dsa_wrong_public_key_rejected(pqc):
    a, b = pqc.sig_keygen(), pqc.sig_keygen()
    assert pqc.verify(b.public_key, b"m", pqc.sign(a.secret_key, b"m")) is False


@pytest.mark.parametrize("bad", [b"", b"\x00" * 3308, b"\x00" * 3310, b"\x00" * 3309, None, "sig", 5])
def test_dsa_malformed_signature_rejected(pqc, bad):
    kp = pqc.sig_keygen()
    assert pqc.verify(kp.public_key, b"m", bad) is False


def test_dsa_malformed_public_key_rejected(pqc):
    kp = pqc.sig_keygen()
    sig = pqc.sign(kp.secret_key, b"m")
    for bad in (b"", kp.public_key[:-1], kp.public_key + b"\x00", None):
        assert pqc.verify(bad, b"m", sig) is False


def test_dsa_malformed_secret_key_rejected_on_sign(pqc):
    kp = pqc.sig_keygen()
    for bad in (b"", kp.secret_key[:-1], None):
        with pytest.raises(PqcError):
            pqc.sign(bad, b"m")


def test_dsa_context_domain_separation(pqc):
    kp = pqc.sig_keygen()
    sig = pqc.sign(kp.secret_key, b"m", b"ctx-A")
    assert pqc.verify(kp.public_key, b"m", sig, b"ctx-A") is True
    assert pqc.verify(kp.public_key, b"m", sig, b"ctx-B") is False
    assert pqc.verify(kp.public_key, b"m", sig) is False
    with pytest.raises(PqcError):
        pqc.sign(kp.secret_key, b"m", b"x" * 256)  # FIPS 204: context <= 255 bytes


def test_dsa_signatures_are_randomised_but_all_verify(pqc):
    kp = pqc.sig_keygen()
    sigs = {pqc.sign(kp.secret_key, b"same") for _ in range(5)}
    assert len(sigs) == 5  # hedged signing in this library
    assert all(pqc.verify(kp.public_key, b"same", s) for s in sigs)


def test_dsa_repeated_independent_keys(pqc):
    pubs = set()
    for i in range(15):
        kp = pqc.sig_keygen()
        pubs.add(kp.public_key)
        assert pqc.verify(kp.public_key, b"n=%d" % i, pqc.sign(kp.secret_key, b"n=%d" % i))
    assert len(pubs) == 15
