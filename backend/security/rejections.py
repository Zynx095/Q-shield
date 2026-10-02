"""Bounded recording of routine rejected traffic.

Every rejected message used to become one `security_events` row. Rejections such as forged HMAC tags, forged or
replayed signatures and unknown device ids need no credentials at all, so anyone on the network could grow that table
(and the trust engine's input) without bound. This module puts a ceiling on that without changing what the trust
engine decides.

Two classes of event:

  HIGH-VALUE   everything not listed as routine below: authenticated misbehaviour (a valid signer reporting for a
               device it is not authorised for, an authenticated device sending a malformed payload), enforcement,
               recovery, operator actions, gateway faults. Always stored, one row each, never pruned here.

  ROUTINE      rejections an unauthenticated party can cause: forged or malformed tags and signatures, replays,
               stale or future timestamps, unknown or retired identities, protocol noise. These are SAMPLED:
                 - per (event type, claimed identity) and per window (default 10 s) the first `sample_per_key`
                   (default 3) are stored as they arrive, so the trust engine reacts at once (3 forged messages
                   already saturate the 25-point pressure cap; 3 replays trigger the repeated-replay hold);
                 - the rest are COALESCED into one representative row of the same event type, carrying
                   `aggregated` (how many it stands for), `first_ts`, `last_ts` and a sample of the details, and
                   stored with received_at = `last_ts`. It is written when the window rolls over, before the next
                   authenticated device message is stored, or when an operator reads the event log;
                 - at most `window_cap` (default 120) sampled rows per window in total; beyond that, identities
                   that got no sample are coalesced per event type into an UNATTRIBUTED row listing a sample of
                   the claimed ids (protects against rotating fake identities);
                 - retention: routine rows beyond the newest `keep_rows` (default 20 000) are pruned, oldest
                   first, and only once the trust engine has consumed them.

Why trust scoring is unchanged: an unauthenticated rejection only adds bounded pressure (capped at 25 points) and
marks a violation time that stops recovery credit. The sample saturates the cap immediately; the representative row
keeps the pressure topped up and carries the LAST rejection's time, and it is flushed before the device's next
authenticated message is stored, so "time since the last violation" (credited recovery time) is exactly what it
would have been with one row per rejected message. Rows are fewer; the decisions are the same (tests:
tests/fullstack/test_rejection_flood.py). One deliberate difference: identities beyond the per-window cap (an attacker
rotating more than ~40 claimed identities every 10 s) are counted in an unattributed row, so those identities get no
extra pressure in that window; unauthenticated pressure is a trust-denial vector, never a path to quarantine.
Coalesced counts not yet flushed live in memory and are lost if the gateway stops; the sampled rows are already stored.
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Callable

ROUTINE = frozenset({
    # device path, before or instead of HMAC verification
    "invalid_tag", "replay_or_stale_counter", "auth_profile_mismatch", "unknown_device", "revoked_device",
    "unsupported_protocol_version", "message_type_mismatch", "unknown_auth_profile", "auth_profile_not_implemented",
    "credential_missing",
    # signed observations and sessions, before the signature verified (or about unknown parties)
    "pqc_invalid_signature", "pqc_malformed_signature", "pqc_signer_algorithm_mismatch", "pqc_unknown_signer",
    "pqc_signer_retired", "pqc_signer_revoked", "pqc_signer_session_mismatch", "pqc_stale_timestamp",
    "pqc_future_timestamp", "pqc_malformed_timestamp", "pqc_observation_replay", "pqc_unknown_session",
    "pqc_malformed_ciphertext", "pqc_malformed_envelope", "pqc_unsupported_protocol_version", "pqc_unsupported_algorithm",
    "pqc_unknown_gateway_key", "pqc_too_many_sessions", "pqc_observation_unknown_device", "observation_rejected_device",
})
ROUTINE_PREFIXES = ("pqc_handshake_", "pqc_session_")


def is_routine(event_type: str) -> bool:
    """Unknown event types are treated as high-value (stored), never as routine: fail toward keeping evidence."""
    return event_type in ROUTINE or event_type.startswith(ROUTINE_PREFIXES)


def _claimed(device_id: str | None, details: dict) -> str:
    return str(device_id or details.get("device_id") or details.get("claimed_signer_id")
               or details.get("claimed_device_id") or "-")


@dataclass
class _Pending:
    event_type: str
    device_id: str | None
    severity: str
    first_ts: float
    last_ts: float
    unattributed: bool = False
    count: int = 0
    sample: dict = field(default_factory=dict)
    claimed: list = field(default_factory=list)


_IDENTITY_KEYS = ("device_id", "claimed_signer_id", "claimed_device_id")


class RejectionRecorder:
    def __init__(self, store, *, window_s: float = 10.0, sample_per_key: int = 3, window_cap: int = 120,
                 keep_rows: int = 20_000, consumed_upto: Callable[[], float] | None = None):
        if window_s <= 0 or sample_per_key < 1 or window_cap < sample_per_key or keep_rows < 1:
            raise ValueError("bad rejection-recorder limits")
        self.store, self.window_s, self.sample_per_key = store, window_s, sample_per_key
        self.window_cap, self.keep_rows = window_cap, keep_rows
        self._consumed = consumed_upto or (lambda: math.inf)      # no trust engine: nothing waits for the rows
        self._lock = threading.Lock()
        self._window: int | None = None
        self._per_key: dict[tuple, int] = {}
        self._stored_in_window = 0
        self._pending: dict[tuple, _Pending] = {}
        self.suppressed_total = 0

    # ------------------------------------------------------------------ write
    def record(self, now: float, device_id: str | None, event_type: str, severity: str, details: dict | None = None) -> None:
        details = dict(details or {})
        if not is_routine(event_type):
            self.store.add_event(now, device_id, event_type, severity, details)
            return
        with self._lock:
            self._roll(now)
            key = (event_type, _claimed(device_id, details))
            n = self._per_key.get(key, 0)
            if n < self.sample_per_key and (n > 0 or self._stored_in_window < self.window_cap):
                self._per_key[key] = n + 1
                self._stored_in_window += 1
                self.store.add_event(now, device_id, event_type, severity, details, routine=True)
                return
            # Over the sample: coalesce. A key that never got a sampled row (window cap reached, e.g. rotating fake
            # identities) is coalesced per event type, unattributed.
            pkey = key if n > 0 else (event_type, "*")
            p = self._pending.get(pkey)
            if p is None:
                unattributed = n == 0
                sample = {k: v for k, v in details.items() if not (unattributed and k in _IDENTITY_KEYS)}
                p = self._pending[pkey] = _Pending(event_type, None if unattributed else device_id, severity, now, now,
                                                   unattributed=unattributed, sample=sample)
            p.count += 1
            p.last_ts = max(p.last_ts, now)
            claimed = key[1]
            if claimed not in p.claimed and len(p.claimed) < 10:
                p.claimed.append(claimed)
            self.suppressed_total += 1

    def flush(self, now: float | None = None) -> int:
        """Write every pending representative row (before an authenticated device message is stored, and when the
        event log is read). Returns the number of rows written."""
        with self._lock:
            return self._flush_locked()

    # ------------------------------------------------------------------ internals
    def _roll(self, now: float) -> None:
        w = math.floor(now / self.window_s)
        if w == self._window:
            return
        self._flush_locked()
        self._window, self._per_key, self._stored_in_window = w, {}, 0
        self._prune()

    def _flush_locked(self) -> int:
        written = 0
        for p in sorted(self._pending.values(), key=lambda x: x.last_ts):
            details = {**p.sample, "aggregated": p.count, "first_ts": p.first_ts, "last_ts": p.last_ts,
                       "aggregation": "routine rejections beyond the per-window sample, coalesced into this row"}
            if p.unattributed:
                details["claimed_sample"] = p.claimed
            self.store.add_event(p.last_ts, p.device_id, p.event_type, p.severity, details, routine=True)
            written += 1
        self._pending.clear()
        return written

    def _prune(self) -> None:
        self.store.prune_routine_events(self.keep_rows, self._consumed())
