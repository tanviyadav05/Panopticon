"""Runs a frozen checkpoint against the environment for N episodes, with no
further learning, and reports the shared metrics from analysis/metrics.py.

    python3 evaluate.py --checkpoint ../../experiments/checkpoints/<run_id>/checkpoint_00000010.pt --episodes 20

Also writes a JSON log of per-episode series to --out, which
analysis/plot_results.py and analysis/compare_agents.py both know how to
read.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from checkpoint_manager import CheckpointManager
from policy import ActorCritic
from env.panopticon_env import PanopticonEnv

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "analysis")))
import metrics  # noqa: E402


def load_models(checkpoint: dict) -> dict:
    models = {}
    for agent, payload in checkpoint.items():
        if agent in ("iteration", "saved_at"):
            continue
        model = ActorCritic(payload["obs_dim"], payload["n_actions"], payload["hidden_size"])
        model.load_state_dict(payload["model"])
        model.eval()
        models[agent] = model
    return models


def run_episode(env: PanopticonEnv, models: dict, deterministic: bool = True) -> dict:
    obs, _ = env.reset()
    log = {"service_health": [], "combined_pressure": [], "detection_confidence": [], "red_return": 0.0, "blue_return": 0.0}

    while env.agents:
        actions = {}
        for a in env.possible_agents:
            obs_t = torch.as_tensor(obs[a]).unsqueeze(0)
            with torch.no_grad():
                logits, _ = models[a].forward(obs_t)
                actions[a] = int(torch.argmax(logits, dim=-1).item()) if deterministic else int(
                    torch.distributions.Categorical(logits=logits).sample().item()
                )
        obs, rewards, terms, truncs, infos = env.step(actions)
        log["red_return"] += rewards.get("red", 0.0)
        log["blue_return"] += rewards.get("blue", 0.0)
        any_agent = next(iter(infos)) if infos else None
        if any_agent:
            log["service_health"].append(infos[any_agent]["service_health"])
            log["combined_pressure"].append(infos[any_agent]["combined_pressure"])
            log["detection_confidence"].append(infos[any_agent]["detection_confidence"])

    return log


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", help="Path to a specific checkpoint .pt file; defaults to latest in --checkpoint-dir")
    parser.add_argument("--checkpoint-dir", default=os.path.join(here, "..", "..", "experiments", "checkpoints", "smoketest"))
    parser.add_argument("--episodes", type=int, default=10)
    parser.add_argument("--stochastic", action="store_true", help="Sample actions instead of taking argmax")
    parser.add_argument("--out", default=None, help="Optional path to write a JSON episode log")
    args = parser.parse_args()

    if args.checkpoint:
        checkpoint = CheckpointManager(os.path.dirname(args.checkpoint)).load(args.checkpoint)
    else:
        checkpoint = CheckpointManager(args.checkpoint_dir).load_latest()
        if checkpoint is None:
            raise SystemExit(f"No checkpoints found in {args.checkpoint_dir}")

    models = load_models(checkpoint)
    env = PanopticonEnv(mode="sim", max_steps=200)

    episode_logs = [run_episode(env, models, deterministic=not args.stochastic) for _ in range(args.episodes)]
    summary = metrics.summarize(episode_logs)

    print(f"[evaluate] checkpoint iteration={checkpoint.get('iteration')} episodes={args.episodes}")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    if args.out:
        with open(args.out, "w") as fh:
            json.dump({"summary": summary, "episodes": episode_logs}, fh, indent=2)
        print(f"[evaluate] wrote episode log -> {args.out}")


if __name__ == "__main__":
    main()
