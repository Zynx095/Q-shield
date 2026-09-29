"""Where observations go. The vision service knows only this interface, never the backend's
storage: HttpSink talks to the public ingestion API with the ingest token."""
from __future__ import annotations

import json
import logging
from collections import deque
from pathlib import Path
from typing import Protocol

from backend.protocol.observation import Observation

log = logging.getLogger("qshield.vision")


class ObservationSink(Protocol):
    def emit(self, obs: Observation) -> None: ...


class ListSink:
    def __init__(self):
        self.items: list[Observation] = []

    def emit(self, obs: Observation) -> None:
        self.items.append(obs)


class JsonlSink:
    """Append-only local log (one JSON object per line). Useful offline and as a replay record."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, obs: Observation) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obs.to_wire(), separators=(",", ":")) + "\n")


class HttpSink:
    """POST /api/v1/observations with a bearer ingest token. A gateway outage must not stop the
    camera loop: failed observations are queued (bounded, oldest dropped) and retried."""

    def __init__(self, base_url: str, token: str, client=None, max_queue: int = 1000):
        import httpx

        self._client = client or httpx.Client(base_url=base_url, timeout=3.0)
        self._headers = {"Authorization": f"Bearer {token}"}
        self._queue: deque[dict] = deque(maxlen=max_queue)
        self.dropped = 0

    def emit(self, obs: Observation) -> None:
        if len(self._queue) == self._queue.maxlen:
            self.dropped += 1
        self._queue.append(obs.to_wire())
        while self._queue:
            try:
                r = self._client.post("/api/v1/observations", json=self._queue[0], headers=self._headers)
            except Exception as e:  # network down, timeout...
                log.warning("gateway unreachable, %d observation(s) queued: %s", len(self._queue), e)
                return
            if r.status_code == 200:
                self._queue.popleft()
            elif 400 <= r.status_code < 500:
                log.error("gateway rejected observation (%s); dropping it", r.status_code)
                self._queue.popleft()
            else:
                log.warning("gateway error %s; will retry", r.status_code)
                return


class FanoutSink:
    def __init__(self, *sinks: ObservationSink):
        self._sinks = sinks

    def emit(self, obs: Observation) -> None:
        for s in self._sinks:
            s.emit(obs)
