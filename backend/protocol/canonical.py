"""Unambiguous byte encoding for anything that is signed or MACed.

Signatures never cover a JSON serialization. They cover:

    u16 len(domain) || domain || u16 n_fields || (u32 len(field_i) || field_i) for each field

Every element is length-prefixed and the field count is included, so distinct field lists can
never encode to the same bytes (no concatenation ambiguity, no whitespace/key-order/number
formatting ambiguity). Text fields are UTF-8; opaque bytes (ciphertexts, nonces, payload text as
transmitted) are passed as they are.
"""
from __future__ import annotations

from typing import Sequence

MAX_FIELD_BYTES = 2**32 - 1


def encode_fields(domain: bytes, fields: Sequence[bytes | str]) -> bytes:
    if not (0 < len(domain) < 2**16) or len(fields) >= 2**16:
        raise ValueError("domain/field count out of range")
    out = bytearray(len(domain).to_bytes(2, "big") + domain + len(fields).to_bytes(2, "big"))
    for f in fields:
        b = f.encode("utf-8") if isinstance(f, str) else bytes(f)
        if len(b) > MAX_FIELD_BYTES:
            raise ValueError("field too large")
        out += len(b).to_bytes(4, "big") + b
    return bytes(out)
