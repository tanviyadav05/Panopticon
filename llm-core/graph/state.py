"""The shared state object every node in the LangGraph reads from and
writes to. TypedDict, not a dataclass, because that's what
langgraph.graph.StateGraph expects — each node returns a partial dict of
the fields it's updating, and LangGraph merges it into the running state
between node calls.
"""
from __future__ import annotations

from typing import TypedDict


class AgentTurn(TypedDict):
    agent: str
    model: str
    text: str
    mocked: bool
    latency_s: float


class AgentState(TypedDict):
    # the task as given to the graph
    task: str
    target_context: dict          # optional: e.g. {"device_type": "wifi_router", "name": "lab-router"} when called from red-team

    # planner output
    plan: list[str]
    next_step_type: str           # "research" | "code" | "done"
    step_instruction: str

    # working results for the current step
    research_findings: str
    research_confidence: float
    code: str
    code_output: str
    code_executed: bool

    # critic verdict for the current step
    critic_approved: bool
    critic_feedback: str

    # control flow
    iteration: int                # per-step revision attempts (reset to 0 whenever Planner dispatches a NEW step)
    max_iterations: int           # cap on revision attempts for a single step
    total_steps: int              # global count of Planner dispatches across the whole task (never reset)
    max_total_steps: int          # hard cap on total_steps — the real termination guarantee, independent of per-step revision bounding
    status: str                   # "planning" | "researching" | "coding" | "reviewing" | "done" | "failed"
    next: str                     # name of the next node, or "END" — read by the graph's router

    # full transcript, for debugging/tracing/the dashboard
    history: list[AgentTurn]

    # final rollup
    final_answer: str
