"""Asks the local LLM (via llm-core's API gateway) to propose a new or
mutated strategy, using llm-core/prompts/red_prompts.txt as the framing.

Consistent with everything else in red-team/attacks/, what comes back is a
STRATEGY PROPOSAL — which abstract pressure variable to lean into, and how
hard — not a generated exploit payload. The LLM is reasoning about the
simulation's action space, not writing code that touches a real target.

Falls back to a random proposal if llm-core is unreachable, so red_attacker
keeps working (just less cleverly) without a live model.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Optional

import numpy as np
import requests

_CACHE_PATH = os.path.join(os.path.dirname(__file__), "payload_cache.json")
_PRESSURE_VARS = ["connection", "cpu", "memory", "parsing"]


def _context_key(context: dict) -> str:
    blob = json.dumps(context, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


class LLMPayloadGenerator:
    def __init__(self, llm_gateway_url: Optional[str] = None, cache_path: str = _CACHE_PATH, timeout: float = 3.0):
        # Deployment config names the LLM service root.  Older callers
        # supplied the legacy /generate endpoint directly, so support both.
        base_url = (llm_gateway_url or os.environ.get("LLM_GATEWAY_URL", "http://llm-laptop:8090")).rstrip("/")
        self.llm_gateway_url = base_url if base_url.endswith("/generate") else f"{base_url}/generate"
        self.cache_path = cache_path
        self.timeout = timeout

    def propose(self, context: dict, rng: np.random.Generator) -> dict:
        """context is whatever red_attacker.py currently knows about the
        episode (recent rewards, which pressure variables it's already
        leaned on). Returns {"connection"|"cpu"|"memory"|"parsing": magnitude}.
        """
        cached = self._cache_lookup(context)
        if cached is not None:
            return cached

        proposal = self._query_llm(context) or self._random_fallback(rng)
        self._cache_store(context, proposal)
        return proposal

    def _query_llm(self, context: dict) -> Optional[dict]:
        prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "llm-core", "prompts", "red_prompts.txt")
        try:
            with open(prompt_path) as fh:
                template = fh.read()
        except FileNotFoundError:
            template = "Given the current state {context}, propose a strategy as JSON {{pressure: ..., intensity: ...}}."

        prompt = template.format(context=json.dumps(context))
        try:
            resp = requests.post(self.llm_gateway_url, json={"prompt": prompt, "max_tokens": 128}, timeout=self.timeout)
            resp.raise_for_status()
            text = resp.json().get("text", "")
            parsed = json.loads(text)
            pressure = parsed["pressure"]
            intensity = float(parsed["intensity"])
            if pressure not in _PRESSURE_VARS:
                return None
            return {pressure: max(0.0, min(1.0, intensity)) * 0.4}  # scaled into the same range as the hand-written modules
        except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError):
            return None

    def _random_fallback(self, rng: np.random.Generator) -> dict:
        pressure = rng.choice(_PRESSURE_VARS)
        magnitude = float(rng.uniform(0.20, 0.40))
        return {pressure: magnitude}

    def _cache_lookup(self, context: dict) -> Optional[dict]:
        cache = self._read_cache()
        entry = cache.get(_context_key(context))
        return entry["proposal"] if entry else None

    def _cache_store(self, context: dict, proposal: dict):
        cache = self._read_cache()
        cache[_context_key(context)] = {"proposal": proposal, "cached_at": time.time()}
        # Keep the cache from growing without bound across a long run.
        if len(cache) > 500:
            oldest = sorted(cache.items(), key=lambda kv: kv[1]["cached_at"])[:100]
            for k, _ in oldest:
                cache.pop(k, None)
        with open(self.cache_path, "w") as fh:
            json.dump(cache, fh, indent=2)

    def _read_cache(self) -> dict:
        if not os.path.exists(self.cache_path):
            return {}
        try:
            with open(self.cache_path) as fh:
                return json.load(fh)
        except json.JSONDecodeError:
            return {}
