"""Wraps whichever model runtime is actually available behind one
generate() call. Backend is chosen by LLM_BACKEND:

  "mock"          — deterministic-ish, no model needed. The default, and
                     what makes this repo runnable without a GPU or any
                     downloaded weights.
  "ollama"        — calls a local Ollama server (LLM_OLLAMA_URL,
                     LLM_OLLAMA_MODEL). Good fit for laptop 01 if you'd
                     rather not deal with raw transformers + GPU plumbing.
  "transformers"  — loads a local HF-format model directly (LLM_MODEL_PATH,
                     defaults to llm-core/models/hermes3-8b/). This is
                     what you'd point at local HF-format weights.

All three implement the same generate(prompt, max_tokens) -> str contract,
so llm_server.py doesn't need to know which one is active.
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional


class InferenceEngine:
    def __init__(self, backend: Optional[str] = None):
        self.backend_name = backend or os.environ.get("LLM_BACKEND", "mock")
        self._impl = self._build_backend(self.backend_name)

    def generate(self, prompt: str, max_tokens: int = 128, temperature: float = 0.7) -> str:
        return self._impl(prompt, max_tokens, temperature)

    def _build_backend(self, name: str):
        if name == "mock":
            return self._mock_backend
        if name == "ollama":
            return self._ollama_backend
        if name == "transformers":
            return self._transformers_backend()
        raise ValueError(f"unknown LLM_BACKEND '{name}'")

    # --- mock --------------------------------------------------------------

    def _mock_backend(self, prompt: str, max_tokens: int, temperature: float) -> str:
        """No model, no network — just enough structure to exercise the
        rest of the pipeline (llm_payload_generator.py expects JSON like
        {"pressure": ..., "intensity": ...} back from red_prompts.txt-style
        prompts). Picks a pseudo-random-but-prompt-dependent choice so
        repeated calls with the same prompt are stable within a process."""
        import hashlib

        pressures = ["connection", "cpu", "memory", "parsing"]
        h = int(hashlib.sha256(prompt.encode()).hexdigest(), 16)
        pressure = pressures[h % len(pressures)]
        intensity = round(0.3 + (h % 1000) / 1000 * 0.6, 3)
        return json.dumps({
            "pressure": pressure,
            "intensity": intensity,
            "rationale": f"[mock backend] no live model; deterministic pick from prompt hash for '{pressure}'",
        })

    # --- ollama --------------------------------------------------------------

    def _ollama_backend(self, prompt: str, max_tokens: int, temperature: float) -> str:
        import requests

        url = os.environ.get("LLM_OLLAMA_URL", "http://localhost:11434/api/generate")
        model = os.environ.get("LLM_OLLAMA_MODEL", "hermes3:8b")
        resp = requests.post(url, json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature},
        }, timeout=30)
        resp.raise_for_status()
        return resp.json().get("response", "")

    # --- transformers --------------------------------------------------------

    def _transformers_backend(self):
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        model_path = os.environ.get(
            "LLM_MODEL_PATH",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "hermes3-8b"),
        )
        tokenizer = AutoTokenizer.from_pretrained(model_path)
        model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype="auto", device_map="auto")

        def run(prompt: str, max_tokens: int, temperature: float) -> str:
            inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
            with torch.no_grad():
                output_ids = model.generate(
                    **inputs, max_new_tokens=max_tokens, temperature=temperature, do_sample=temperature > 0,
                )
            text = tokenizer.decode(output_ids[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
            return text

        return run


def extract_json(text: str) -> Optional[dict]:
    """Models don't always return clean JSON even when asked to — this
    pulls the first {...} block out of whatever text came back."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
