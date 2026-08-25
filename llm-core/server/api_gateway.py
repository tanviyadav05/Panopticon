"""The façade other laptops' code imports rather than calling llm_server.py
over HTTP directly. Two things it adds on top of a raw request: it tags
and persists every call into memory/attack_history.json or
defense_history.json depending on the caller's role, and it fails soft
(returns None instead of raising) so a flaky LLM laptop degrades the
calling agent's cleverness, not its ability to run at all.
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

import requests

_MEMORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory")
_HISTORY_FILES = {"red": "attack_history.json", "blue": "defense_history.json"}


class LLMGateway:
    def __init__(self, base_url: Optional[str] = None, role: str = "red", timeout: float = 5.0):
        if role not in _HISTORY_FILES:
            raise ValueError("role must be 'red' or 'blue'")
        self.base_url = (base_url or os.environ.get("LLM_GATEWAY_URL", "http://llm-laptop:8090")).rstrip("/")
        self.role = role
        self.timeout = timeout
        self.history_path = os.path.join(_MEMORY_DIR, _HISTORY_FILES[role])

    def generate(self, prompt: str, max_tokens: int = 128, temperature: float = 0.7) -> Optional[str]:
        try:
            resp = requests.post(
                f"{self.base_url}/generate",
                json={"prompt": prompt, "max_tokens": max_tokens, "temperature": temperature},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            text = resp.json().get("text", "")
        except requests.RequestException:
            return None

        self._append_history(prompt, text)
        return text

    def _append_history(self, prompt: str, response: str):
        os.makedirs(_MEMORY_DIR, exist_ok=True)
        history = []
        if os.path.exists(self.history_path):
            try:
                with open(self.history_path) as fh:
                    history = json.load(fh)
            except json.JSONDecodeError:
                history = []

        history.append({"timestamp": time.time(), "prompt": prompt, "response": response})
        history = history[-500:]  # keep the file bounded

        with open(self.history_path, "w") as fh:
            json.dump(history, fh, indent=2)
