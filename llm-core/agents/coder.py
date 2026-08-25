"""Coder/Executor node — Qwen3 7B Q4_K_M in the real deployment.

Asks the model for code + an execute-or-not flag, then, if execution was
requested and the code_sandbox tool is available, actually runs it in a
real Docker container and folds the real output back into state.
"""
from __future__ import annotations

from graph.state import AgentState


def make_coder_node(agent, code_sandbox=None):
    def coder_node(state: AgentState) -> dict:
        instruction = state.get("step_instruction") or state["task"]
        prior_feedback = state.get("critic_feedback", "")
        prompt = f"Current step: {instruction}\nTask context: {state['task']}"
        if prior_feedback:
            prompt += f"\nPrevious attempt's critic feedback (fix this): {prior_feedback}"

        response = agent.call(prompt)
        parsed = response.parsed or {}

        code = parsed.get("code", response.text)
        needs_execution = bool(parsed.get("needs_execution", False))

        code_output = ""
        executed = False
        if needs_execution and code_sandbox is not None and code_sandbox.available:
            result = code_sandbox.run_python(code)
            executed = True
            code_output = result.get("output", "") if result.get("ok") else f"[sandbox error] {result.get('error', 'unknown')}"
        elif needs_execution:
            code_output = "[not executed: code_sandbox unavailable — Docker daemon not reachable]"
        else:
            code_output = parsed.get("explanation", "(no execution requested)")

        turn = {"agent": "coder", "model": response.model, "text": response.text,
                "mocked": response.mocked, "latency_s": response.latency_s}
        history = state.get("history", []) + [turn]

        return {
            "history": history,
            "code": code,
            "code_output": code_output,
            "code_executed": executed,
            "status": "coding",
            "next": "critic",
        }

    return coder_node
