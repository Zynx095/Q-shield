"""Bearer tokens for non-device callers, kept entirely separate from device HMAC auth.

Two scopes, two tokens:
  operator : read/control APIs used by a human or the dashboard.
  ingest   : the local vision/observer service posting observations.
A token for one scope never satisfies the other, and neither is accepted on the device
ingestion endpoints (those use the per-device HMAC envelope).

Simple by design for a local deployment: a random 256-bit token from env or a gitignored
file under keys/, compared in constant time. No sessions, expiry or roles; rotate by
deleting the file (or changing the env var) and restarting. Tokens travel in cleartext over
HTTP, so use only on a trusted network until TLS is added.
"""
from __future__ import annotations

import hmac
import secrets
from pathlib import Path

from backend.security.fileutil import write_private_file

MIN_TOKEN_CHARS = 32
SCOPES = ("operator", "ingest")


class TokenError(Exception):
    pass


def load_or_create_token(scope: str, keys_dir: str | Path, env_value: str | None = None) -> str:
    if scope not in SCOPES:
        raise TokenError(f"unknown token scope {scope!r}")
    if env_value:
        token = env_value.strip()
        if len(token) < MIN_TOKEN_CHARS:
            raise TokenError(f"{scope} token from environment is too short (min {MIN_TOKEN_CHARS} chars)")
        return token
    path = Path(keys_dir) / f"{scope}.token"
    if not path.exists():
        try:
            write_private_file(path, (secrets.token_urlsafe(32) + "\n").encode())
        except FileExistsError:
            pass
    token = path.read_text().strip()
    if len(token) < MIN_TOKEN_CHARS:
        raise TokenError(f"{path} is corrupt or too short")
    return token


def token_matches(presented: str | None, expected: str) -> bool:
    if not presented:
        return False
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def bearer_from_header(header: str | None) -> str | None:
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value.strip() else None
