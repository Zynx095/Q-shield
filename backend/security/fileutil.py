"""Tiny dependency-free file helper (no DB imports, so the vision service can use it)."""
from __future__ import annotations

import os
from pathlib import Path


def write_private_file(path: Path, data: bytes) -> None:
    """Create a new file readable only by the owner (POSIX 0600). Never overwrites.
    On Windows POSIX modes do not apply; the file inherits the directory ACL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
