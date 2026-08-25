"""OllamaAgent wraps one role's real model call against a real Ollama
server (POST /api/chat). This is genuinely how a deployed agent talks to
Ollama — no LangChain ChatModel wrapper in between, just requests, which
keeps this consistent with the rest of the repo's style (see
observer/pipeline/publisher.py, red-team's LLMGateway, etc.) and avoids
pulling in langchain-community's heavier dependency chain for something
this simple.

If Ollama is unreachable (wrong host, model not pulled, daemon down —
exactly the situation in local dev or in any environment without a live
Ollama server), calls fall back to a deterministic mock response keyed off
the agent's role, so the LangGraph orchestration logic in graph/ can be
built, run, and tested end-to-end without a live model. This mirrors the
same mock-fallback pattern used by server/inference_engine.py's
LLM_BACKEND=mock. Real output quality obviously depends on the real
models actually being loaded in Ollama.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger("llm_core.base_agent")


@dataclass
class AgentResponse:
    agent_name: str
    model: str
    text: str
    parsed: Optional[dict]     # best-effort JSON parse of `text`, or None
    latency_s: float
    mocked: bool
    timestamp: float = field(default_factory=time.time)


class OllamaAgent:
    def __init__(
        self,
        name: str,
        model: str,
        system_prompt: str,
        host: str,
        temperature: float = 0.5,
        request_timeout_s: float = 90.0,
        connect_timeout_s: float = 3.0,
    ):
        self.name = name
        self.model = model
        self.system_prompt = system_prompt
        self.host = host.rstrip("/")
        self.temperature = temperature
        self.request_timeout_s = request_timeout_s
        self.connect_timeout_s = connect_timeout_s

    def call(self, user_prompt: str, context: str = "") -> AgentResponse:
        full_prompt = f"{context}\n\n{user_prompt}" if context else user_prompt
        start = time.monotonic()

        text = self._call_ollama(full_prompt)
        mocked = text is None
        if mocked:
            text = self._mock_response(full_prompt)

        latency = time.monotonic() - start
        parsed = _extract_json(text)

        return AgentResponse(
            agent_name=self.name, model=self.model, text=text,
            parsed=parsed, latency_s=latency, mocked=mocked,
        )

    def _call_ollama(self, prompt: str) -> Optional[str]:
        try:
            resp = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": self.temperature},
                },
                timeout=(self.connect_timeout_s, self.request_timeout_s),
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")
        except requests.RequestException as exc:
            logger.info("%s: Ollama unreachable (%s), using mock fallback", self.name, exc)
            return None
        except (ValueError, KeyError) as exc:
            logger.warning("%s: unexpected Ollama response shape (%s), using mock fallback", self.name, exc)
            return None

    def _mock_response(self, prompt: str) -> str:
        """A deterministic, role-shaped canned response so callers (and
        tests) get something schema-valid back even with no live model.
        Keyed off a hash of the prompt so the same input is stable across
        calls within a process, the same way inference_engine.py's mock
        backend behaves."""
        h = int(hashlib.sha256(prompt.encode()).hexdigest(), 16)

        if self.name == "planner":
            if '"next_step_type"' in self.system_prompt or "IN-PROGRESS" in prompt:
                choice = ["research", "code", "done"][h % 3]
                return json.dumps({
                    "next_step_type": choice,
                    "step_instruction": "" if choice == "done" else f"[mock] continue with {choice} on: {prompt[:60]}",
                    "reasoning": "[mock backend] no live Ollama connection; deterministic pick from prompt hash",
                })
            steps = [f"[mock] investigate: {prompt[:40]}", "[mock] produce a result", "[mock] verify the result"]
            return json.dumps({
                "plan": steps,
                "next_step_type": "research" if h % 2 == 0 else "code",
                "reasoning": "[mock backend] no live Ollama connection; deterministic plan from prompt hash",
            })

        if self.name == "researcher":
            return json.dumps({
                "findings": f"[mock backend] no live Ollama connection — would research: {prompt[:80]}",
                "sources_used": [],
                "confidence": round(0.3 + (h % 100) / 200, 2),
            })

        if self.name == "coder":
            return json.dumps({
                "code": f"# [mock backend] no live Ollama connection\nprint('mock output for: {prompt[:40]!r}')",
                "explanation": "[mock backend] deterministic placeholder — no live model",
                "needs_execution": True,
            })

        if self.name == "critic":
            approved = (h % 4) != 0  # mostly approves, occasionally rejects, so the loop path is exercised too
            return json.dumps({
                "approved": approved,
                "feedback": "[mock backend] no live Ollama connection" + ("" if approved else " — simulated rejection to exercise the revision loop"),
                "severity": "none" if approved else "minor",
            })

        return json.dumps({"text": f"[mock backend] {self.name}: {prompt[:80]}"})


def _extract_json(text: str) -> Optional[dict]:
    """Models — mocked or real — don't always return clean JSON even when
    asked to. Pulls the first {...} block out and parses it; returns None
    (not an exception) if nothing parseable is found, so callers can
    decide how to degrade."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
