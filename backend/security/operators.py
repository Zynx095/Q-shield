"""Per-operator identities for the control API (Phase 13, TD-17).

Replaces "one shared operator token" with named operators:
  operator_id, display_name, role, status (active | revoked), optional expiry, and a bearer token.

Token handling:
  * tokens are 256-bit random (`secrets.token_urlsafe(32)`), prefixed `qso_` so a leaked token is recognisable;
  * only SHA-256(token) is stored. A token is high-entropy, so an unsalted fast hash is sufficient (no
    dictionary attack is possible); the plaintext is shown ONCE at creation and never again;
  * lookup is by hash; the stored hash is then re-compared in constant time;
  * revocation and expiry take effect on the next request (no caching).

Roles (smallest model that separates viewing, acting and administration):
  viewer   : read-only operator API (dashboard viewing)
  operator : viewer + security actions (start/abort recovery, set expected state, manual quarantine)
  admin    : operator + operator management (create, list, revoke)

Bootstrap: the legacy shared operator token (OPERATOR_TOKEN / keys/operator.token) still authenticates, as the
identity `bootstrap-admin` (role admin), so an installation can create its first named operators. Set
ALLOW_SHARED_OPERATOR_TOKEN=false once named operators exist; every action by it is attributed to
`bootstrap-admin`, which is NOT a person.

Operator tokens are a different namespace from the ingest token and device HMAC keys; none satisfies the other.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

ROLES = ("viewer", "operator", "admin")
RANK = {r: i for i, r in enumerate(ROLES)}
ACTIVE, REVOKED = "active", "revoked"
TOKEN_PREFIX = "qso_"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,63}$")
BOOTSTRAP_ID = "bootstrap-admin"

SCHEMA = """
CREATE TABLE IF NOT EXISTS operators (
    operator_id   TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL,
    status        TEXT NOT NULL,
    token_hash    TEXT NOT NULL UNIQUE,
    created_at    REAL NOT NULL,
    created_by    TEXT,
    expires_at    REAL,
    revoked_at    REAL,
    revoked_by    TEXT
);
"""


class OperatorError(Exception):
    pass


@dataclass(frozen=True)
class Operator:
    operator_id: str
    display_name: str
    role: str
    status: str = ACTIVE
    expires_at: float | None = None
    bootstrap: bool = False

    def allows(self, role: str) -> bool:
        return RANK[self.role] >= RANK[role]

    def public(self) -> dict:
        return {"operator_id": self.operator_id, "display_name": self.display_name, "role": self.role,
                "status": self.status, "expires_at": self.expires_at, "bootstrap": self.bootstrap}


BOOTSTRAP = Operator(BOOTSTRAP_ID, "Bootstrap admin (shared token, not a person)", "admin", bootstrap=True)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class OperatorStore:
    def __init__(self, store):
        self.store = store
        store.ensure_schema(SCHEMA)

    def create(self, operator_id: str, display_name: str, role: str, now: float, *, created_by: str | None = None,
               ttl_s: float | None = None) -> tuple[Operator, str]:
        """Returns (operator, plaintext token). The token is not stored and cannot be recovered."""
        if not ID_RE.match(operator_id or "") or operator_id == BOOTSTRAP_ID:
            raise OperatorError("operator_id must be 2-64 chars [A-Za-z0-9_.-] and not reserved")
        if role not in ROLES:
            raise OperatorError(f"role must be one of {ROLES}")
        display_name = (display_name or "").strip()
        if not (1 <= len(display_name) <= 80):
            raise OperatorError("display_name must be 1-80 characters")
        if ttl_s is not None and ttl_s <= 0:
            raise OperatorError("ttl_s must be > 0")
        if self.store.query("SELECT 1 FROM operators WHERE operator_id=?", (operator_id,)):
            raise OperatorError("operator_exists")
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        expires = now + ttl_s if ttl_s else None
        self.store.execute("INSERT INTO operators(operator_id, display_name, role, status, token_hash, created_at,"
                           " created_by, expires_at) VALUES (?,?,?,?,?,?,?,?)",
                           (operator_id, display_name, role, ACTIVE, _hash(token), now, created_by, expires))
        return Operator(operator_id, display_name, role, ACTIVE, expires), token

    def revoke(self, operator_id: str, now: float, by: str | None = None) -> Operator:
        op = self.get(operator_id)
        if op is None:
            raise OperatorError("not_found")
        if op.status == REVOKED:
            raise OperatorError("already_revoked")
        self.store.execute("UPDATE operators SET status=?, revoked_at=?, revoked_by=? WHERE operator_id=?",
                           (REVOKED, now, by, operator_id))
        return self.get(operator_id)

    def get(self, operator_id: str) -> Operator | None:
        rows = self.store.query("SELECT * FROM operators WHERE operator_id=?", (operator_id,))
        return self._op(rows[0]) if rows else None

    def list(self) -> list[dict]:
        rows = self.store.query("SELECT * FROM operators ORDER BY created_at")
        return [{**self._op(r).public(), "created_at": r["created_at"], "created_by": r["created_by"],
                 "revoked_at": r["revoked_at"], "revoked_by": r["revoked_by"]} for r in rows]

    def authenticate(self, token: str | None, now: float) -> Operator | None:
        if not token or not token.startswith(TOKEN_PREFIX):
            return None
        h = _hash(token)
        rows = self.store.query("SELECT * FROM operators WHERE token_hash=?", (h,))
        if not rows or not hmac.compare_digest(rows[0]["token_hash"], h):
            return None
        op = self._op(rows[0])
        if op.status != ACTIVE or (op.expires_at is not None and now >= op.expires_at):
            return None
        return op

    @staticmethod
    def _op(r) -> Operator:
        return Operator(r["operator_id"], r["display_name"], r["role"], r["status"], r["expires_at"])
