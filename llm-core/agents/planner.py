"""Planner/Manager node — Hermes 3 8B in the real deployment.

Two modes, distinguished by whether `state["plan"]` is already populated:
  - New task (empty plan): asks the model for a plan + first step type.
  - In-progress task: shows the model what's happened so far (last
    research/code result, critic feedback if any) and asks what to do next
    — research, code, or done.

Two separate safety bounds, deliberately not conflated:
  - `iteration` / `max_iterations` — how many revision attempts a single
    step gets (reset to 0 here every time a NEW step is dispatched; the
    critic increments it while retrying the SAME step).
  - `total_steps` / `max_total_steps` — how many steps the Planner is
    allowed to dispatch across the whole task, ever. This is the real
    termination guarantee: even if the model (or its mock stand-in) never
    says "done", the task is forced to finish once this cap is hit. Unlike
    `max_iterations`, this counter is never reset.
"""
from __future__ import annotations

from graph.state import AgentState


def make_planner_node(agent, max_plan_steps: int = 6):
    def planner_node(state: AgentState) -> dict:
        is_new_task = not state.get("plan")
        total_steps = state.get("total_steps", 0)
        max_total_steps = state.get("max_total_steps", 12)

        if is_new_task:
            prompt = (
                f"Task: {state['task']}\n"
                f"Context: {state.get('target_context') or 'none'}\n\n"
                f"Propose a plan of at most {max_plan_steps} steps."
            )
        else:
            last_result = state.get("code_output") or state.get("research_findings") or "(no result yet)"
            feedback = state.get("critic_feedback") or "(no feedback yet)"
            prompt = (
                f"Task: {state['task']}\n"
                f"Plan so far: {state.get('plan')}\n"
                f"Most recent step result: {last_result}\n"
                f"Critic feedback on that result: {feedback}\n"
                f"Steps taken: {total_steps}/{max_total_steps}\n\n"
                f"This is an IN-PROGRESS task. What should happen next?"
            )

        response = agent.call(prompt)
        parsed = response.parsed or {}

        turn = {"agent": "planner", "model": response.model, "text": response.text,
                "mocked": response.mocked, "latency_s": response.latency_s}
        history = state.get("history", []) + [turn]

        next_step_type = parsed.get("next_step_type", "research")
        if next_step_type not in ("research", "code", "done"):
            next_step_type = "research"

        update: dict = {
            "history": history,
            "next_step_type": next_step_type,
            "step_instruction": parsed.get("step_instruction", state.get("task", "")),
            "status": "planning",
        }
        if is_new_task:
            plan = parsed.get("plan") or [state["task"]]
            update["plan"] = plan[:max_plan_steps]

        # Global termination guarantee — checked before trusting the model's
        # own "done" judgment, so a model/mock that never says done can't
        # keep the graph running forever.
        if total_steps >= max_total_steps:
            update["status"] = "done"
            update["next"] = "END"
            update["final_answer"] = (
                (state.get("code_output") or state.get("research_findings") or "(no result produced)")
                + f" [forced completion: reached max_total_steps={max_total_steps}]"
            )
            return update

        if next_step_type == "done":
            update["status"] = "done"
            update["next"] = "END"
            update["final_answer"] = state.get("code_output") or state.get("research_findings") or "(no result produced)"
            return update

        # Dispatching a new step: reset the per-step revision counter and
        # count this dispatch against the global step cap.
        update["iteration"] = 0
        update["total_steps"] = total_steps + 1
        update["next"] = "researcher" if next_step_type == "research" else "coder"
        return update

    return planner_node
