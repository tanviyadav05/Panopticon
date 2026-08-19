"""Local-LLM advisor for Blue's fixed, defensive action space.

This module is deliberately advisory.  It can return only one of Blue's
existing countermeasure names; it cannot create shell commands, policies, or
network actions.  ``blue_controller.py`` keeps execution behind its normal
controller API and its autonomous endpoint defaults to dry-run mode.
"""
from __future__ import annotations

import json
import os
from typing import Optional

import numpy as np
import requests

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))
_PROMPT_PATH = os.path.join(_REPO_ROOT, "llm-core", "prompts", "blue_prompts.txt")
_BLUE_ACTIONS = {"noop", "rate_limit", "isolate_pod", "honeypot_redirect", "raise_alert_threshold"}


def _generate_url(base_url: Optional[str] = None) -> str:
    """Accept either an LLM service root or its legacy ``/generate`` URL."""
    raw = (base_url or os.environ.get("LLM_GATEWAY_URL", "http://llm-laptop:8090")).rstrip("/")
    return raw if raw.endswith("/generate") else f"{raw}/generate"


class LLMDefenseAdvisor:
    """Ask the local LLM for a bounded defensive recommendation.

    The fallback is deterministic and conservative so a missing/unavailable
    LLM never turns into an unexpected live action.
    """

    def __init__(self, llm_gateway_url: Optional[str] = None, timeout: float = 4.0):
        self.llm_gateway_url = _generate_url(llm_gateway_url)
        self.timeout = timeout

    def propose(self, observation: np.ndarray | list[float]) -> dict:
        vector = np.asarray(observation, dtype=np.float32).reshape(-1)
        context = {
            "observation": [round(float(v), 4) for v in vector.tolist()],
            "note": "Values are normalized 0..1 telemetry features from a closed lab simulation.",
        }
        return self._query(context) or self._fallback(vector)

    def _query(self, context: dict) -> Optional[dict]:
        try:
            with open(_PROMPT_PATH, encoding="utf-8") as handle:
                template = handle.read()
            prompt = template.format(context=json.dumps(context, sort_keys=True))
            response = requests.post(
                self.llm_gateway_url,
                json={"prompt": prompt, "max_tokens": 128, "temperature": 0.1},
                timeout=self.timeout,
            )
            response.raise_for_status()
            proposal = json.loads(response.json().get("text", ""))
            action = proposal.get("action")
            confidence = float(proposal.get("confidence", 0.0))
            if action not in _BLUE_ACTIONS or not 0.0 <= confidence <= 1.0:
                return None
            return {
                "action": action,
                "confidence": confidence,
                "rationale": str(proposal.get("rationale", "Local LLM recommendation."))[:240],
                "source": "local_llm",
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError, requests.RequestException):
            return None

    @staticmethod
    def _fallback(vector: np.ndarray) -> dict:
        # The last feature is the normalized HTTP error rate.  This is a
        # defensive-only fallback; it never selects an intrusive action.
        error_rate = float(vector[-1]) if vector.size else 0.0
        action = "rate_limit" if error_rate >= 0.45 else "noop"
        return {
            "action": action,
            "confidence": 0.45 if action == "rate_limit" else 0.7,
            "rationale": "Conservative local fallback; the LLM service was unavailable.",
            "source": "fallback",
        }
