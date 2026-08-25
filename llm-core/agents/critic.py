"""Critic/Reviewer node — Qwen3 7B Q4_K_M in the real deployment.

Reviews whichever of research_findings / code+code_output was just
produced (determined by state["next_step_type"], which the Planner set
before dispatching to Researcher or Coder) against the step instruction.

Routing on the verdict:
  - approved            -> back to Planner for the next step
  - rejected, iterations remain -> back to the SAME node (Researcher or
    Coder) with feedback, for one more attempt at this step
  - rejected, iterations exhausted -> forced through to Planner anyway,
    so a stubborn step can never loop forever
"""
from __future__ import annotations

from graph.state import AgentState


def make_critic_node(agent):
    def critic_node(state: AgentState) -> dict:
        step_type = state.get("next_step_type", "research")
        instruction = state.get("step_instruction") or state["task"]

        if step_type == "code":
            result_summary = f"Code:\n{state.get('code', '')}\n\nExecution output:\n{state.get('code_output', '')}"
        else:
            result_summary = f"Findings:\n{state.get('research_findings', '')}\n(confidence: {state.get('research_confidence', 0.0)})"

        prompt = f"Step instruction: {instruction}\n\n{result_summary}"
        response = agent.call(prompt)
        parsed = response.parsed or {}

        approved = bool(parsed.get("approved", True))
        feedback = parsed.get("feedback", "")

        turn = {"agent": "critic", "model": response.model, "text": response.text,
                "mocked": response.mocked, "latency_s": response.latency_s}
        history = state.get("history", []) + [turn]

        iteration = state.get("iteration", 0) + 1
        max_iterations = state.get("max_iterations", 4)

        update: dict = {
            "history": history,
            "critic_approved": approved,
            "critic_feedback": feedback,
            "iteration": iteration,
            "status": "reviewing",
        }

        if approved:
            update["critic_feedback"] = ""   # clear so a future step doesn't see stale feedback
            update["next"] = "planner"
        elif iteration >= max_iterations:
            update["critic_feedback"] = f"[iteration cap reached, forcing forward] {feedback}"
            update["next"] = "planner"
        else:
            update["next"] = "researcher" if step_type == "research" else "coder"

        return update

    return critic_node
