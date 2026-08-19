"""Ships the encoded state vector to the Referee (laptop 05) over HTTP.

This is the one place observer/ crosses a laptop boundary. If the Referee is
briefly unreachable (it's mid-restart, the LAN hiccuped), failed sends are
queued locally and retried before the next send rather than silently
dropped — short of a sustained outage, the Referee shouldn't miss episodes
just because of an HTTP blip.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import Optional

import numpy as np
import requests

logger = logging.getLogger("observer.publisher")


class Publisher:
    def __init__(self, referee_url: str, max_queue: int = 256, timeout: float = 1.0):
        self.referee_url = referee_url
        self.timeout = timeout
        self._queue: deque[dict] = deque(maxlen=max_queue)

    def publish(self, vector: np.ndarray, field_names: list[str], timestamp: Optional[float] = None) -> bool:
        payload = {
            "timestamp": timestamp or time.time(),
            "field_names": field_names,
            "state": vector.tolist(),
        }
        self._queue.append(payload)
        return self._flush_queue()

    def _flush_queue(self) -> bool:
        sent_all = True
        while self._queue:
            payload = self._queue[0]
            try:
                resp = requests.post(self.referee_url, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                self._queue.popleft()
            except requests.RequestException as exc:
                logger.warning("publish failed (%s); %d event(s) queued for retry", exc, len(self._queue))
                sent_all = False
                break
        return sent_all

    @property
    def queue_depth(self) -> int:
        return len(self._queue)
