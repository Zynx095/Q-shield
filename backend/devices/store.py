"""SQLite persistence for devices, telemetry and security events (stdlib sqlite3).

security_events is the Phase 1 precursor of the Phase 8 evidence chain; it is a plain
table with no tamper-evidence yet.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    device_id     TEXT PRIMARY KEY,
    auth_profile  TEXT NOT NULL,
    revoked       INTEGER NOT NULL DEFAULT 0,
    last_counter  INTEGER NOT NULL DEFAULT -1,
    enrolled_at   REAL NOT NULL,
    registered_at REAL,
    last_seen     REAL,
    info          TEXT NOT NULL DEFAULT '{}',
    last_telemetry TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS credential_blobs (
    device_id   TEXT PRIMARY KEY,
    blob        BLOB NOT NULL,
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS signers (
    signer_id       TEXT PRIMARY KEY,
    algorithm       TEXT NOT NULL,
    public_key      BLOB NOT NULL,
    source          TEXT NOT NULL,
    allowed_devices TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      REAL NOT NULL,
    retired_at      REAL
);
CREATE TABLE IF NOT EXISTS observations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id TEXT NOT NULL UNIQUE,
    received_at    REAL NOT NULL,
    device_id      TEXT NOT NULL,
    event_type     TEXT NOT NULL,
    observed_at    TEXT NOT NULL,
    anomaly        INTEGER NOT NULL,
    body           TEXT NOT NULL,
    auth           TEXT NOT NULL DEFAULT 'ingest-token',
    envelope       TEXT,
    transport      TEXT
);
CREATE INDEX IF NOT EXISTS idx_obs_dev ON observations(device_id, id);
CREATE TABLE IF NOT EXISTS device_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT NOT NULL,
    received_at REAL NOT NULL,
    kind        TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS trust_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    ts        REAL NOT NULL,
    event_id  TEXT NOT NULL UNIQUE,
    body      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trust_dev ON trust_events(device_id, id);
CREATE TABLE IF NOT EXISTS trust_state (device_id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trust_cursors (source TEXT PRIMARY KEY, last_id INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS trust_diagnostics (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, device_id TEXT, reason TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS telemetry (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT NOT NULL,
    received_at REAL NOT NULL,
    counter     INTEGER NOT NULL,
    payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_telemetry_dev ON telemetry(device_id, id);
CREATE TABLE IF NOT EXISTS security_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at REAL NOT NULL,
    device_id   TEXT,
    event_type  TEXT NOT NULL,
    severity    TEXT NOT NULL,
    details     TEXT NOT NULL DEFAULT '{}',
    routine     INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass(frozen=True)
class SignerRecord:
    """A trusted software component (e.g. the vision service) with an ML-DSA public key."""
    signer_id: str
    algorithm: str
    public_key: bytes
    source: str
    allowed_devices: tuple[str, ...]
    status: str  # active | retired | revoked
    created_at: float


@dataclass(frozen=True)
class DeviceRecord:
    device_id: str
    auth_profile: str
    revoked: bool
    last_counter: int
    enrolled_at: float
    registered_at: float | None
    last_seen: float | None
    info: dict[str, Any]
    last_telemetry: dict[str, Any]


def _row_to_device(r: sqlite3.Row) -> DeviceRecord:
    return DeviceRecord(
        device_id=r["device_id"], auth_profile=r["auth_profile"],
        revoked=bool(r["revoked"]), last_counter=r["last_counter"], enrolled_at=r["enrolled_at"],
        registered_at=r["registered_at"], last_seen=r["last_seen"],
        info=json.loads(r["info"]), last_telemetry=json.loads(r["last_telemetry"]),
    )


class Store:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        if path != ":memory:":
            self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        cols = {r["name"] for r in self._db.execute("PRAGMA table_info(observations)")}
        for col, ddl in (("auth", "TEXT NOT NULL DEFAULT 'ingest-token'"), ("envelope", "TEXT"), ("transport", "TEXT")):
            if col not in cols:  # databases created before Phase 3 (auth, envelope) or before transport was recorded
                self._db.execute(f"ALTER TABLE observations ADD COLUMN {col} {ddl}")
        if "routine" not in {r["name"] for r in self._db.execute("PRAGMA table_info(security_events)")}:
            self._db.execute("ALTER TABLE security_events ADD COLUMN routine INTEGER NOT NULL DEFAULT 0")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # --- generic access for feature modules that own their tables (twin, evidence, recovery) ---
    def ensure_schema(self, ddl: str) -> None:
        with self._lock:
            self._db.executescript(ddl)

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    def execute(self, sql: str, params: tuple = ()) -> int:
        """Run one write statement in its own transaction; returns lastrowid."""
        with self._lock, self._db:
            return self._db.execute(sql, params).lastrowid

    # --- devices ---
    def enroll_device(self, device_id: str, auth_profile: str, now: float) -> None:
        """Register a device identity. Its secret lives in the CredentialStore, not here."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO devices(device_id, auth_profile, enrolled_at) VALUES (?,?,?)",
                (device_id, auth_profile, now),
            )

    def get_device(self, device_id: str) -> DeviceRecord | None:
        with self._lock:
            r = self._db.execute("SELECT * FROM devices WHERE device_id=?", (device_id,)).fetchone()
        return _row_to_device(r) if r else None

    def list_devices(self) -> list[DeviceRecord]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM devices ORDER BY device_id").fetchall()
        return [_row_to_device(r) for r in rows]

    def revoke_device(self, device_id: str) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE devices SET revoked=1 WHERE device_id=?", (device_id,))

    def advance_counter(self, device_id: str, counter: int) -> bool:
        """Atomically accept `counter` only if strictly greater than the stored one."""
        with self._lock, self._db:
            cur = self._db.execute(
                "UPDATE devices SET last_counter=? WHERE device_id=? AND last_counter<?",
                (counter, device_id, counter),
            )
            return cur.rowcount == 1

    def touch(self, device_id: str, now: float, *, info: dict | None = None,
              telemetry: dict | None = None, registered: bool = False, message_kind: str | None = None) -> None:
        """Record an authenticated device message. `message_kind` (register|heartbeat|telemetry) also appends to the
        device_messages evidence stream the trust engine consumes."""
        with self._lock, self._db:
            self._db.execute("UPDATE devices SET last_seen=? WHERE device_id=?", (now, device_id))
            if message_kind:
                self._db.execute("INSERT INTO device_messages(device_id, received_at, kind, payload) VALUES (?,?,?,?)",
                                 (device_id, now, message_kind, json.dumps(telemetry if telemetry is not None else (info or {}))))
            if registered:
                self._db.execute("UPDATE devices SET registered_at=? WHERE device_id=?", (now, device_id))
            if info is not None:
                self._db.execute("UPDATE devices SET info=? WHERE device_id=?", (json.dumps(info), device_id))
            if telemetry is not None:
                self._db.execute(
                    "UPDATE devices SET last_telemetry=? WHERE device_id=?", (json.dumps(telemetry), device_id)
                )

    # --- opaque credential blobs (encryption is done by backend.security.credentials) ---
    def put_credential_blob(self, device_id: str, blob: bytes, now: float) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO credential_blobs(device_id, blob, created_at) VALUES (?,?,?)",
                (device_id, blob, now),
            )

    def get_credential_blob(self, device_id: str) -> bytes | None:
        with self._lock:
            r = self._db.execute("SELECT blob FROM credential_blobs WHERE device_id=?", (device_id,)).fetchone()
        return bytes(r["blob"]) if r else None

    def delete_credential_blob(self, device_id: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM credential_blobs WHERE device_id=?", (device_id,))

    # --- observations (Phase 2: vision and other observers; NOT trust decisions) ---
    def add_observation(self, now: float, obs: dict, auth: str = "ingest-token",
                        envelope: str | None = None, transport: str = "token") -> bool:
        """Store a normalized observation. Returns False if observation_id was already stored.
        `auth` records how it was authenticated ('ingest-token' or 'ML-DSA-65:<signer_id>');
        `envelope` keeps the signed envelope text as verifiable evidence;
        `transport` records how it reached the gateway: 'token' (ingest bearer token), 'signed' (ML-DSA envelope posted
        directly) or 'secure' (ML-DSA envelope inside an ML-KEM-768 / AES-256-GCM session)."""
        try:
            with self._lock, self._db:
                self._db.execute(
                    "INSERT INTO observations(observation_id, received_at, device_id, event_type, observed_at, anomaly,"
                    " body, auth, envelope, transport) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (obs["observation_id"], now, obs["device_id"], obs["event_type"], obs["timestamp"],
                     1 if obs["anomaly"] else 0, json.dumps(obs), auth, envelope, transport),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def list_observations(self, device_id: str | None = None, limit: int = 100,
                          anomalies_only: bool = False) -> list[dict]:
        q, args = "SELECT received_at, body, auth, transport FROM observations WHERE 1=1", []
        if device_id:
            q += " AND device_id=?"; args.append(device_id)
        if anomalies_only:
            q += " AND anomaly=1"
        q += " ORDER BY id DESC LIMIT ?"; args.append(limit)
        with self._lock:
            rows = self._db.execute(q, args).fetchall()
        return [{"received_at": r["received_at"], **json.loads(r["body"]), "auth": r["auth"], "transport": r["transport"]}
                for r in rows]

    def get_observation_envelope(self, observation_id: str) -> str | None:
        with self._lock:
            r = self._db.execute("SELECT envelope FROM observations WHERE observation_id=?",
                                 (observation_id,)).fetchone()
        return r["envelope"] if r else None

    # --- signers (trusted PQC signing components; public keys only) ---
    def add_signer(self, signer_id: str, algorithm: str, public_key: bytes, source: str,
                   allowed_devices: list[str], now: float) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO signers(signer_id, algorithm, public_key, source, allowed_devices, created_at)"
                " VALUES (?,?,?,?,?,?)", (signer_id, algorithm, public_key, source, json.dumps(allowed_devices), now))

    def get_signer(self, signer_id: str) -> SignerRecord | None:
        with self._lock:
            r = self._db.execute("SELECT * FROM signers WHERE signer_id=?", (signer_id,)).fetchone()
        return self._signer_row(r) if r else None

    def list_signers(self) -> list[SignerRecord]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM signers ORDER BY signer_id").fetchall()
        return [self._signer_row(r) for r in rows]

    def set_signer_status(self, signer_id: str, status: str, now: float) -> bool:
        with self._lock, self._db:
            cur = self._db.execute("UPDATE signers SET status=?, retired_at=? WHERE signer_id=?",
                                   (status, now if status != "active" else None, signer_id))
            return cur.rowcount == 1

    @staticmethod
    def _signer_row(r: sqlite3.Row) -> SignerRecord:
        return SignerRecord(r["signer_id"], r["algorithm"], bytes(r["public_key"]), r["source"],
                            tuple(json.loads(r["allowed_devices"])), r["status"], r["created_at"])

    # --- trust engine persistence and evidence cursors (Phase 4) ---
    def rows_after(self, table: str, last_id: int, limit: int = 1000) -> list[sqlite3.Row]:
        assert table in ("security_events", "observations", "device_messages")
        with self._lock:
            return self._db.execute(f"SELECT * FROM {table} WHERE id>? ORDER BY id LIMIT ?", (last_id, limit)).fetchall()

    def get_cursor(self, source: str) -> int:
        with self._lock:
            r = self._db.execute("SELECT last_id FROM trust_cursors WHERE source=?", (source,)).fetchone()
        return r["last_id"] if r else 0

    def set_cursor(self, source: str, last_id: int) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO trust_cursors(source, last_id) VALUES (?,?)", (source, last_id))

    def save_trust_state(self, device_id: str, body: dict) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO trust_state(device_id, body) VALUES (?,?)", (device_id, json.dumps(body)))

    def load_trust_states(self) -> dict[str, dict]:
        with self._lock:
            rows = self._db.execute("SELECT device_id, body FROM trust_state").fetchall()
        return {r["device_id"]: json.loads(r["body"]) for r in rows}

    def add_trust_event(self, device_id: str, ts: float, event_id: str, body: dict) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT OR IGNORE INTO trust_events(device_id, ts, event_id, body) VALUES (?,?,?,?)",
                             (device_id, ts, event_id, json.dumps(body)))

    def trust_history(self, device_id: str, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT body FROM trust_events WHERE device_id=? ORDER BY id DESC LIMIT ?", (device_id, limit)).fetchall()
        return [json.loads(r["body"]) for r in rows]

    def add_trust_diagnostic(self, ts: float, device_id: str | None, reason: str, detail: dict) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT INTO trust_diagnostics(ts, device_id, reason, detail) VALUES (?,?,?,?)",
                             (ts, device_id, reason, json.dumps(detail)))

    def list_trust_diagnostics(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM trust_diagnostics ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": r["id"], "ts": r["ts"], "device_id": r["device_id"], "reason": r["reason"], "detail": json.loads(r["detail"])} for r in rows]

    # --- telemetry ---
    def add_telemetry(self, device_id: str, now: float, counter: int, payload: dict) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO telemetry(device_id, received_at, counter, payload) VALUES (?,?,?,?)",
                (device_id, now, counter, json.dumps(payload)),
            )

    def recent_telemetry(self, device_id: str, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT received_at, counter, payload FROM telemetry WHERE device_id=? ORDER BY id DESC LIMIT ?",
                (device_id, limit),
            ).fetchall()
        return [{"received_at": r["received_at"], "counter": r["counter"], **json.loads(r["payload"])} for r in rows]

    # --- security events ---
    def add_event(self, now: float, device_id: str | None, event_type: str, severity: str,
                  details: dict | None = None, routine: bool = False) -> None:
        """`routine`: an unauthenticated rejection sampled by backend.security.rejections (subject to retention)."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO security_events(received_at, device_id, event_type, severity, details, routine) VALUES (?,?,?,?,?,?)",
                (now, device_id, event_type, severity, json.dumps(details or {}), 1 if routine else 0),
            )

    def prune_routine_events(self, keep: int, consumed_upto: float) -> int:
        """Delete routine rejection rows beyond the newest `keep`, but only rows with id <= `consumed_upto` (already read
        by the trust engine). High-value rows are never touched. Returns the number of rows deleted."""
        with self._lock, self._db:
            row = self._db.execute("SELECT id FROM security_events WHERE routine=1 ORDER BY id DESC LIMIT 1 OFFSET ?",
                                   (keep,)).fetchone()
            if row is None:
                return 0
            limit = min(row["id"], consumed_upto)
            return self._db.execute("DELETE FROM security_events WHERE routine=1 AND id<=?", (limit,)).rowcount

    def count_events(self, routine: bool | None = None) -> int:
        q = "SELECT COUNT(*) AS n FROM security_events" + ("" if routine is None else " WHERE routine=?")
        with self._lock:
            return self._db.execute(q, () if routine is None else (1 if routine else 0,)).fetchone()["n"]

    def list_events(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM security_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {"id": r["id"], "received_at": r["received_at"], "device_id": r["device_id"],
             "event_type": r["event_type"], "severity": r["severity"], "details": json.loads(r["details"])}
            for r in rows
        ]
