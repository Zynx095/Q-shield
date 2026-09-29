"""Trust service: runs the trust engine over the gateway's own records.

    Vision -> observations table         Security layer -> security_events table (authenticity results)
    Device -> device_messages table      Trust engine   -> trust_events (explainable decisions)

The service is pull-based: it reads new rows after persisted cursors, converts them with backend.trust.adapters,
applies them in (time, source, id) order and stores the resulting TrustChange records. The engine never touches the
vision detector, the camera, the ESP32 or any cryptographic primitive.
Phase 4 records state and recommendations only: it revokes nothing, blocks nothing and recovers nothing.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

from backend.devices.store import Store
from backend.trust import adapters
from backend.trust.config import TrustConfig
from backend.trust.engine import TrustEngine
from backend.trust.model import Auth, Kind, Signal, SignalRejected, State, TrustChange

_SOURCES = (("device_messages", 0), ("security_events", 1), ("observations", 2))   # tie-break order at equal timestamps


class TrustService:
    def __init__(self, store: Store, cfg: TrustConfig | None = None, clock: Callable[[], float] = time.time,
                 twin=None):
        self.store, self.clock = store, clock
        self.cfg = (cfg or TrustConfig()).validate()
        self.engine = TrustEngine(self.cfg)
        self.twin = twin                                  # optional backend.twin.DigitalTwin (per-device expectations)
        self.listeners: list[Callable[[TrustChange], None]] = []   # e.g. the evidence chain
        self._lock = threading.RLock()
        saved = store.load_trust_states()
        if saved:
            self.engine.import_state(saved)

    def state_of(self, device_id: str) -> State | None:
        """Current trust state after consuming every pending record (None = no trust record yet)."""
        with self._lock:
            self.process_pending()
            dt = self.engine.devices.get(device_id)
            return dt.state if dt is not None and dt.started else None

    def score_of(self, device_id: str) -> int | None:
        with self._lock:
            dt = self.engine.devices.get(device_id)
            return dt.score if dt is not None and dt.started else None

    # ------------------------------------------------------------------ ingestion
    def _hw(self, device_id: str) -> str | None:
        d = self.store.get_device(device_id)
        return d.info.get("hw") if d else None

    def process_pending(self) -> list[TrustChange]:
        with self._lock:
            for d in self.store.list_devices():
                self.engine.track(d.device_id)
            items, new_cursor = [], {}
            for source, order in _SOURCES:
                last = self.store.get_cursor(source)
                while True:
                    rows = self.store.rows_after(source, last)
                    if not rows:
                        break
                    for r in rows:
                        items.append((r["received_at"], order, r["id"], source, r))
                    last = rows[-1]["id"]
                new_cursor[source] = last
            items.sort(key=lambda t: (t[0], t[1], t[2]))
            changes: list[TrustChange] = []
            touched: set[str] = set()
            for ts, _, _, source, row in items:
                ad = (adapters.from_security_event(row, self.store) if source == "security_events"
                      else adapters.from_observation(row, self.cfg) if source == "observations"
                      else adapters.from_device_message(row, self.cfg, self._hw(row["device_id"]),
                                                        self.twin.trust_expectations(row["device_id"]) if self.twin else None))
                if not ad.signals:
                    self._diag(ts, ad.device_id, ad.note or "no_signal", {"source": source, "id": row["id"]})
                    continue
                for sig in ad.signals:
                    changes += self._apply(sig, touched)
            now = self.clock()
            for d in self.store.list_devices():                       # revocation gate (from the device record)
                dt = self.engine.devices.get(d.device_id)
                if d.revoked and dt is not None and not dt.revoked:
                    changes += self._apply(Signal(f"revoked:{d.device_id}", d.device_id, Kind.DEVICE_REVOKED, now, Auth.GATEWAY_LOCAL,
                                                  source_ref="device_record"), touched)
            for dev in list(self.engine.devices):                     # time-driven evaluation (staleness)
                for c in self.engine.evaluate(dev, now):
                    self._store_change(c)
                    touched.add(dev)
                    changes.append(c)
            for diag in self.engine.pop_diagnostics():
                self._diag(now, diag.get("device_id"), diag["reason"], {k: v for k, v in diag.items() if k not in ("device_id", "reason")})
            for dev in touched:
                self.store.save_trust_state(dev, self.engine.devices[dev].to_dict())
            for source, last in new_cursor.items():
                self.store.set_cursor(source, last)
            return changes

    def _apply(self, sig: Signal, touched: set) -> list[TrustChange]:
        try:
            out = self.engine.apply(sig)
        except SignalRejected as e:                                   # fail closed: rejected input changes no score
            self._diag(sig.timestamp, sig.device_id, f"signal_rejected:{e.reason}", {"signal_id": sig.signal_id, "kind": sig.kind.value,
                                                                                    "detail": e.detail})
            return []
        touched.add(sig.device_id)
        for c in out:
            self._store_change(c)
        return out

    def _store_change(self, c: TrustChange) -> None:
        self.store.add_trust_event(c.device_id, c.timestamp, c.event_id, c.to_dict())
        for fn in self.listeners:
            try:
                fn(c)
            except Exception as e:  # noqa: BLE001 - a listener fault must never corrupt trust bookkeeping
                self._diag(c.timestamp, c.device_id, "trust_listener_error", {"error": type(e).__name__, "event_id": c.event_id})

    def _diag(self, ts, device_id, reason, detail) -> None:
        self.store.add_trust_diagnostic(ts, device_id, reason, detail)

    # ------------------------------------------------------------------ read model
    def snapshot(self, device_id: str) -> dict:
        with self._lock:
            self.process_pending()
            return self.engine.snapshot(device_id, self.clock())

    def snapshot_all(self) -> list[dict]:
        with self._lock:
            self.process_pending()
            now = self.clock()
            return [self.engine.snapshot(d, now) for d in sorted(self.engine.devices)]

    def history(self, device_id: str, limit: int = 50) -> list[dict]:
        return self.store.trust_history(device_id, limit)

    def request_transition(self, device_id: str, target: State, reason: str, evidence_id: str) -> list[TrustChange]:
        """Validated explicit transition (used by later phases). Not exposed over HTTP in Phase 4."""
        with self._lock:
            self.process_pending()
            changes = self.engine.request_transition(device_id, target, reason, evidence_id, self.clock())
            for c in changes:
                self._store_change(c)
            self.store.save_trust_state(device_id, self.engine.devices[device_id].to_dict())
            return changes
