---
name: Feature request
about: A new attack class, countermeasure, agent tool, or component
title: "[feature] "
labels: enhancement
---

**What's missing, and which component would it live in?**

**If this is a new Red action:** does it fit the simulated-effects pattern
in `red-team/attacks/README.md`? (New attack classes should land as effect
models, not live exploit code — see that README before opening this.)

**If this is a new Blue countermeasure:** does it need real cluster
access, or is it a policy/heuristic change?

**If this is a new agent/tool for llm-core:** see
`docs/multi_agent_llm.md` — does it need a real external capability
(like code_sandbox/web_browser), and if so, what's the failure-closed
behavior when that capability isn't available?

**Proposed approach:**
