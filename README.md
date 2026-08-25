# 🏛️ Project Panopticon

> A Multi-Agent Reinforcement Learning (MARL) Cybersecurity Simulator.
> Two AI agents — **Red (attacker)** and **Blue (defender)** — fight inside a live
> Kubernetes cluster, learning strategy through thousands of episodes.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     PROJECT PANOPTICON                                  │
│                                                                         │
│   ┌────────────┐  attacks   ┌──────────────────────────────────┐        │
│   │  OMNI-RED  │──────────▶ │       KUBERNETES CLUSTER         │       │
│   │  (RL Agent)│            │  ┌──────────────────────────────┐ │       │
│   └────────────┘            │  │  TARGET GO APP (Pod)         │ │       │
│         ▲                   │  │  /api/process  ← Recursive   │ │       │
│    reward│                  │  │  /api/sort     ← O(n²)       │ │       │
│   ┌──────┴──────┐           │  │  /api/matrix   ← O(n³)       │ │       │
│   │   REFEREE   │           │  └──────────┬───────────────────┘ │       │
│   │ (MARL Loop) │           │             │                     │       │
│   └──────┬──────┘           │  ┌──────────▼───────────────────┐ │       │
│    reward│                  │  │  POSTGRES (Pod)              │ │       │
│   ┌──────▼──────┐           │  └──────────────────────────────┘ │       │
│   │  OMNI-BLUE  │           └──────────────────────────────────┘        │
│   │  (RL Agent) │◀──── State JSON ──────────────────────────┐          │
│   └─────────────┘                                            │          │
│         │ K8s NetworkPolicy                         ┌────────┴──────┐   │
│         └─────────────────────────────────────────▶ │   OBSERVER   │   │
│                                                     │ (eBPF Probes) │   │
│                                                     └───────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Team Roles

| Member  | Component | Technology |
|---------|-----------|------------|
| Sneha Malhotra | Arena Architect, Omni-Red, Observer | Go, Kubernetes, Docker, eBPF, Python, BCC |
| Moksha Malhotra | Referee | Python asyncio, Scapy, LLM, Ray RLlib, PettingZoo, Python |
| Tanvi Yadav | Omni-Blue, Infra, Analysis | Kubernetes Network Policy, Python |


## Repository Layout

```
project-panopticon/
├── arena/
│   ├── target-app/
│   │   ├── main.go          ← Intentionally vulnerable Go HTTP server
│   │   ├── main_test.go     ← Tests proving the vulnerabilities scale as designed
│   │   ├── go.mod
│   │   └── Dockerfile
│   ├── k8s/
│   │   ├── 00-namespace.yaml
│   │   ├── 01-postgres.yaml
│   │   └── 02-target-app.yaml
│   └── scripts/
│       ├── setup.sh         ← First-time deploy (Minikube + Calico CNI)
│       └── reset.sh         ← Called between RL training episodes
├── observer/
│   └── probes/
│       └── observer.py      ← eBPF telemetry pipeline
├── referee/
│   ├── env/
│   │   └── panopticon_env.py ← PettingZoo/RLlib MARL environment
│   └── training/
│       └── train.py         ← Ray RLlib PPO training script
├── red-team/
│   ├── attacks/
│   │   └── red_attacker.py  ← Attack implementations
│   └── generators/
│       └── llm_payload_generator.py ← LLM-evolved attack payloads
├── blue-team/
│   └── countermeasures/
│       └── blue_controller.py ← Defensive actions + anomaly detection
├── monitoring/
│   └── dashboard_server.py  ← Live browser dashboard (localhost:9000)
├── analysis/
│   └── plot_results.py      ← Training curve plots for your report/slides
├── .github/
│   ├── workflows/ci.yml     ← CI: build, lint, validate on every push
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── ISSUE_TEMPLATE/
├── Makefile                 ← All commands live here
├── requirements.txt
├── .env.example             ← Copy to .env for your ANTHROPIC_API_KEY
├── MASTER_GUIDE.md          ← Full technical guide
├── DEEP_TECH_EXPLANATIONS.md ← Why we made every decision
├── TEAM_ASSIGNMENTS.md      ← Day-by-day plan per team member
├── TROUBLESHOOTING.md       ← Fixes for common errors
├── CONTRIBUTING.md          ← Git workflow for the team
└── LICENSE
```

---

## Attack Vectors (Red Team)

| Attack | Endpoint | Complexity | Observable Effect |
|--------|----------|-----------|-------------------|
| Recursive JSON | `/api/process` | O(depth × width) | CPU spike + call stack growth |
| Bubble Sort | `/api/sort` | O(n²) | CPU 100% for 30s+ |
| Matrix Multiply | `/api/matrix` | O(n³) | All cores pinned |
| Concurrent Burst | All vulnerable | × concurrency | Goroutine explosion |
| Slow Loris | TCP layer | N connections | FD exhaustion |

---

## Defensive Actions (Blue Team)

| Action | Mechanism | Kubernetes Primitive |
|--------|-----------|---------------------|
| Rate Limit Ingress | Allow only labeled pods | `NetworkPolicy` |
| Full Isolation | Drop all ingress | `NetworkPolicy` (empty ingress) |
| Scale Up | Add replicas to absorb load | `kubectl scale` |
| Strict Allowlist | Namespace + pod selector | `NetworkPolicy` |
| Emergency Restart | Clear stuck goroutines | `kubectl rollout restart` |

---

## State Space (What AI Agents Observe)

The eBPF Observer produces a 20-feature JSON every 500ms.
All features normalized to [0.0, 1.0]:

- CPU usage, thread count, file descriptors, memory
- Per-syscall rates: read, write, accept, close, epoll_wait
- TCP state counts: ESTABLISHED, SYN_RECV, CLOSE_WAIT, TIME_WAIT
- Derived: CPU trend, connection trend, attack intensity
- Pod health (binary), episode progress

---

## Training

```bash
# Full training (200 iterations, ~4-6 hours)
make train

# Quick validation run (20 iterations, ~30 min)
make train-quick

# Evaluate saved checkpoint
make eval
```

Results are saved in `./ray_results/`. View with TensorBoard:
```bash
tensorboard --logdir=./ray_results
```

---

## Contributing

- Branch from `develop`, not `main`
- Commit format: `feat(component): short description`
- Open PR to `develop`, tag the lead for review
- All PRs require: description of what changed + test command

---

## Documentation

**Engineering guides:**
- [`MASTER_GUIDE.md`](MASTER_GUIDE.md) — Full step-by-step setup + all code explained
- [`DEEP_TECH_EXPLANATIONS.md`](DEEP_TECH_EXPLANATIONS.md) — Why every technology was chosen
- [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — Fixes for common errors
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — Git workflow for the team

**Project documentation (`docs/`):**
- [`docs/architecture.md`](docs/architecture.md) — System design, data flow, module contracts
- [`docs/requirements.md`](docs/requirements.md) — Functional & non-functional requirements
- [`docs/sdlc-methodology.md`](docs/sdlc-methodology.md) — SDLC selection & justification
- [`docs/team-responsibilities.md`](docs/team-responsibilities.md) — Module ownership & milestones
- [`docs/coding-standards.md`](docs/coding-standards.md) — Naming conventions, commit style
- [`docs/setup-guide.md`](docs/setup-guide.md) — New-member onboarding
- [`docs/ebpf-primer.md`](docs/ebpf-primer.md) — eBPF basics for non-Observer members
- [`docs/marl-concepts.md`](docs/marl-concepts.md) — MARL basics for non-Referee members
- [`docs/CHANGELOG.md`](docs/CHANGELOG.md) — Change & decision log

**Sprint planning:**
- [`MID_EVAL_SPRINT_PLAN.md`](MID_EVAL_SPRINT_PLAN.md) — Current sprint plan and demo checklist
- [`TEAM_ASSIGNMENTS.md`](TEAM_ASSIGNMENTS.md) — Detailed day-by-day task breakdown

---

## Requirements

- **OS**: Linux (Ubuntu 20.04+) with kernel ≥ 4.9
- **RAM**: 8GB minimum (16GB recommended)
- **CPU**: 4 cores minimum
- **Disk**: 20GB free
- **Privileges**: `sudo` access (required for eBPF Observer)

## Red Team Responsibilities

Member of the Red Team is responsible for developing and executing controlled attack simulations within the Panopticon Kubernetes environment. My role focuses on generating realistic attack scenarios that stress-test the application's resilience and help evaluate the effectiveness of Blue Team defenses. I contribute to the development of attack scripts that create observable CPU, memory, and network anomalies, allowing the Observer and Referee components to measure system behavior under adversarial conditions.

I am responsible for implementing attack techniques such as hash flooding, nested JSON complexity attacks, TCP desynchronization, and Slowloris-style connection exhaustion. These attacks are designed to expose weaknesses in application logic, resource management, and network handling. I also work on integrating attack execution with the Referee through action mapping and developing LLM-assisted payload generation to create novel inputs that extend beyond predefined attack patterns.

A key objective of my role is to simulate realistic threats in a safe and isolated environment while ensuring that all attacks remain confined to the designated target application. Through these contributions, I support the evaluation, robustness, and continuous improvement of the Panopticon platform's security posture.

### Components

* hash_flood.py – Generates high volumes of crafted requests to create CPU-intensive processing.
* nested_json_bomb.py – Sends deeply nested JSON payloads to trigger parsing complexity and resource consumption.
* tcp_desync.py – Simulates malformed TCP communication to stress connection handling.
* slowloris.py – Maintains numerous slow HTTP connections to exhaust server resources.
* action_map.py – Maps Referee actions to specific attack implementations.
* payload_prompter.py – Uses an LLM to generate novel adversarial payloads.
* payload_cache.json – Stores previously generated payloads for reuse and efficiency.
* requirements.txt – Lists project dependencies required for attack execution.
----------------------------------------------------------------------------------------------

## Referee / Multi-Agent Reinforcement Learning (MARL) Orchestrator

Referee is responsible for the component of Project Panopticon. My role is to coordinate the Red Team (Attacker) and Blue Team (Defender), define reward mechanisms, manage environment interactions, and execute the reinforcement learning training process.

### Responsibilities

* Design and implement the PettingZoo multi-agent environment.
* Define observation spaces and action spaces for both agents.
* Develop the main training loop for agent interactions.
* Read telemetry data and convert it into RL-compatible observations.
* Execute actions received from Red and Blue agents.
* Implement reward functions for both attacker and defender agents.
* Coordinate episode resets and environment state management.
* Integrate RLlib PPO agents for training and evaluation.

### Components Owned

* marl-orchestrator/env.py
* marl-orchestrator/runner.py
* marl-orchestrator/state_reader.py
* marl-orchestrator/action_executor.py
* reward-functions/red_reward.py
* reward-functions/blue_reward.py
* reward-functions/README.md
* requirements.txt

----------------------------------------------------------------------------------------------

## Blue Team (Defense)

As a member of the Blue Team, I am responsible for designing and implementing defensive mechanisms within the Panopticon Kubernetes environment. My role focuses on detecting abnormal behavior from eBPF telemetry data and responding rapidly to potential threats before they impact the application. 

### Responsibilities

* I contribute to the development of anomaly detection logic that analyzes CPU, memory, and network connection patterns to identify suspicious activity.
* I am also responsible for implementing automated defensive actions such as rate limiting, pod recovery, honeypot traffic redirection, and dynamic network policy enforcement.
* These controls help protect the application from attacks while maintaining service availability.
* Additionally, I work on integrating Kubernetes-based security measures that can isolate compromised components and restrict malicious traffic.
* A key objective of my role is to minimize false positives while ensuring fast and effective threat mitigation.
* Through these contributions, I support the overall resilience, security, and reliability of the Panopticon platform.

### Components Owned

* anomaly_detector.py - Detects anomalies from eBPF telemetry data.
* action_map.py - Maps Referee actions to defensive responses.
* rate_limiter.py - Applies rate limiting to mitigate traffic floods.
* pod_restart.py - Restarts affected application pods for recovery.
* honeypot_redirect.py - Redirects suspicious traffic to a honeypot.
* isolate-db.yaml - NetworkPolicy to isolate database communication.
* block-external.yaml - NetworkPolicy to block untrusted external traffic.
* apply_policy.py - Applies Kubernetes NetworkPolicies programmatically.

---

Repository Ownership

```text
blue-team/
├── defense-scripts/
│   └── anomaly_detector.py
│   └── action_map.py
│   └── rate_limiter.py
│   └── pod_restart.py
│   └── honeypot_redirect.py
└── network-policies/
    └── isolate-db.yaml
    └── block-external.yaml
    └── apply_policy.py
    └── requirements.txt
```
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------


## Infrastructure & Arena Architect

 Overview

I am responsible for building and maintaining the foundational infrastructure for Project Panopticon.

The target application serves as the battlefield where Red Team attacks, Blue Team defenses, and Observer monitoring activities take place. My work enables all other teams to develop, test, and evaluate their components in a consistent environment.

Key Responsibilities

* Develop the intentionally vulnerable Go application
* Containerize services using Docker
* Deploy and manage workloads on Kubernetes
* Provision supporting infrastructure such as PostgreSQL and honeypots
* Create automated deployment and reset workflows
* Ensure CPU and memory usage are observable during attacks
* Maintain deployment documentation and environment setup guides

---

Repository Ownership

```text
target-app/
├── cmd/
│   └── main.go
├── internal/
│   └── handlers.go
├── go.mod
└── Dockerfile

kubernetes/
├── manifests/
│   ├── target-app.yaml
│   ├── database.yaml
│   └── honeypot.yaml
├── scripts/
│   ├── deploy.sh
│   └── reset.sh
└── README.md
```
Owned Components

* `target-app/` — Vulnerable Go application and containerization
* `kubernetes/manifests/` — Application, database, and honeypot deployments
* `kubernetes/scripts/` — Environment deployment and reset automation
* `kubernetes/README.md` — Infrastructure setup and operational documentation















