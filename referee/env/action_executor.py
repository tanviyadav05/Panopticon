"""The only place panopticon_env.py talks to anything outside its own
process, when mode="live".

Two responsibilities:

1. Host an HTTP ingest endpoint (POST /ingest) that observer/pipeline/
   publisher.py sends encoded-state payloads to, and keep the latest one
   available to the env on demand.
2. Translate an agent's chosen action into a real call against the Red or
   Blue laptop's own HTTP API (red-team's red_attacker.py / blue-team's
   blue_controller.py), and report back whatever those services say they
   did.

This module makes no decisions of its own about what an "attack" or
"countermeasure" actually does — that's entirely red-team/'s and
blue-team's job. It's plumbing, not policy.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import requests
import uvicorn
from fastapi import FastAPI, Request

logger = logging.getLogger("referee.action_executor")


class ActionExecutor:
    def __init__(
        self,
        red_endpoint: str,
        blue_endpoint: str,
        ingest_host: str = "0.0.0.0",
        ingest_port: int = 9600,
        request_timeout: float = 2.0,
    ):
        self.red_endpoint = red_endpoint.rstrip("/")
        self.blue_endpoint = blue_endpoint.rstrip("/")
        self.request_timeout = request_timeout

        self._lock = threading.Lock()
        self._latest_raw: Optional[dict] = None
        self._latest_field_names: Optional[list[str]] = None
        self._latest_at: float = 0.0

        self._app = FastAPI(title="Panopticon Referee Ingest")

        @self._app.post("/ingest")
        async def ingest(request: Request):
            payload = await request.json()
            with self._lock:
                self._latest_field_names = payload.get("field_names")
                self._latest_raw = dict(zip(self._latest_field_names, payload.get("state", [])))
                self._latest_at = payload.get("timestamp", time.time())
            return {"received": True}

        self._server_thread: Optional[threading.Thread] = None
        self._ingest_host = ingest_host
        self._ingest_port = ingest_port

    # --- ingest server lifecycle -------------------------------------------

    def start_ingest_server(self):
        config = uvicorn.Config(self._app, host=self._ingest_host, port=self._ingest_port, log_level="warning")
        server = uvicorn.Server(config)

        def run():
            server.run()

        self._server_thread = threading.Thread(target=run, daemon=True)
        self._server_thread.start()
        logger.info("ingest server listening on %s:%s", self._ingest_host, self._ingest_port)

    # --- reading the latest published state --------------------------------

    def latest_observation(self) -> dict:
        with self._lock:
            if self._latest_raw is None:
                return {}
            return dict(self._latest_raw)

    def latest_snapshot(self) -> tuple[dict, list[str], float]:
        """Return the latest normalized Observer state with its source time."""
        with self._lock:
            return (
                dict(self._latest_raw or {}),
                list(self._latest_field_names or []),
                self._latest_at,
            )

    def staleness_seconds(self) -> float:
        with self._lock:
            return time.time() - self._latest_at if self._latest_at else float("inf")

    def estimate_pressure(self, normalized_fields: dict) -> float:
        """A rough, Blue-reward-only proxy for "how bad is it really," built
        from the same normalized fields the policy sees (these are already
        in [0, 1] thanks to state_encoder's normalization upstream — note
        this method expects the *decoded* dict from observation_builder's
        encoder, not raw counts)."""
        keys = ["network.total_connections", "network.close_wait", "memory.rss_delta", "http.error_rate"]
        values = [normalized_fields.get(k, 0.0) for k in keys if k in normalized_fields]
        return sum(values) / len(values) if values else 0.0

    # --- sending actions to Red / Blue --------------------------------------

    def apply_red(self, action: str) -> dict:
        try:
            resp = requests.post(f"{self.red_endpoint}/act", json={"action": action}, timeout=self.request_timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.warning("red laptop unreachable (%s); treating action as a no-op this tick", exc)
            return {"ok": False, "error": str(exc)}

    def apply_blue(self, action: str) -> dict:
        try:
            resp = requests.post(f"{self.blue_endpoint}/act", json={"action": action}, timeout=self.request_timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.warning("blue laptop unreachable (%s); treating action as a no-op this tick", exc)
            return {"ok": False, "error": str(exc)}
