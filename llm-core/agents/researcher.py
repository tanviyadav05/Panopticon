"""Researcher node — Dolphin-Llama3 8B in the real deployment.

Optionally calls the web_browser tool first (if one was passed in and is
available) and folds any results into the prompt as extra context, then
asks the model to summarize findings for the current plan step.
"""
from __future__ import annotations

from graph.state import AgentState


def make_researcher_node(agent, web_browser=None, max_results: int = 5):
    def researcher_node(state: AgentState) -> dict:
        instruction = state.get("step_instruction") or state["task"]

        browsed_context = ""
        if web_browser is not None and web_browser.available:
            results = web_browser.search_and_summarize_links(instruction, max_results=max_results)
            if results:
                browsed_context = "Web search results:\n" + "\n".join(
                    f"- {r.get('title', '')}: {r.get('snippet', '')}" for r in results
                )

        prompt = f"Current step: {instruction}\nTask context: {state['task']}"
        response = agent.call(prompt, context=browsed_context)
        parsed = response.parsed or {}

        turn = {"agent": "researcher", "model": response.model, "text": response.text,
                "mocked": response.mocked, "latency_s": response.latency_s}
        history = state.get("history", []) + [turn]

        return {
            "history": history,
            "research_findings": parsed.get("findings", response.text),
            "research_confidence": float(parsed.get("confidence", 0.5)),
            "status": "researching",
            "next": "critic",
        }

    return researcher_node
