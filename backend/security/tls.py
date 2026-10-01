"""TLS for the gateway (Phase 13, TD-17). Prototype-grade: a certificate/key pair from configuration, served by uvicorn.

QSHIELD_TLS_CERT / QSHIELD_TLS_KEY  -> HTTPS on QSHIELD_PORT (no plain-HTTP listener on that port).
neither set                          -> development HTTP mode, with an explicit warning (tokens travel in cleartext).
QSHIELD_REQUIRE_TLS=true             -> refuse to start without TLS.

There is no PKI: `scripts/gen_dev_cert.py` makes a SELF-SIGNED development certificate; clients must pin it
(`--cacert` / `verify=<cert>`). No HTTP->HTTPS redirect is provided: an HTTPS-only listener simply does not speak HTTP.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import ssl
from pathlib import Path

from backend.security.fileutil import write_private_file


class TlsConfigError(Exception):
    pass


def tls_options(cert: str | None, key: str | None, require: bool = False) -> dict:
    """uvicorn kwargs for TLS, or {} for HTTP. Fails clearly on half/invalid configuration."""
    if not cert and not key:
        if require:
            raise TlsConfigError("QSHIELD_REQUIRE_TLS is set but QSHIELD_TLS_CERT/QSHIELD_TLS_KEY are not")
        return {}
    if not (cert and key):
        raise TlsConfigError("set BOTH QSHIELD_TLS_CERT and QSHIELD_TLS_KEY (only one was given)")
    for label, p in (("certificate", cert), ("private key", key)):
        if not Path(p).is_file():
            raise TlsConfigError(f"TLS {label} file not found: {p}")
    try:
        ssl.create_default_context(ssl.Purpose.CLIENT_AUTH).load_cert_chain(cert, key)
    except (ssl.SSLError, ValueError, OSError) as e:
        raise TlsConfigError(f"TLS certificate/key cannot be loaded (mismatched or malformed?): {e}") from None
    return {"ssl_certfile": cert, "ssl_keyfile": key}


def generate_dev_cert(cert_path: str | Path, key_path: str | Path, hosts: list[str], days: int = 30) -> None:
    """Self-signed ECDSA P-256 certificate for development. The key file is created owner-only and never
    overwritten."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Q-SHIELD dev gateway (self-signed)")])
    sans = []
    for h in hosts:
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(h)))
        except ValueError:
            sans.append(x509.DNSName(h))
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(now + dt.timedelta(days=days))
            .add_extension(x509.SubjectAlternativeName(sans), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(key, hashes.SHA256()))
    write_private_file(Path(key_path), key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                          serialization.NoEncryption()))
    Path(cert_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cert_path).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
