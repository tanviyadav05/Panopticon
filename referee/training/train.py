"""Main PPO training entrypoint.

    python3 train.py --config ../configs/ppo_config.yaml --iterations 20

Trains red and blue as independent PPO agents (each sees the environment,
including the other agent's effect on it, as part of "the environment" —
this is the standard, simple MARL baseline known as Independent PPO/IPPO).
Defaults to a short run; pass --iterations for a longer one. Runs entirely
in sim mode unless the config says otherwise, so this needs nothing else
running anywhere.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))         # -> referee/training
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # -> referee/
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "common")))
from checkpoint_manager import CheckpointManager
from policy import ActorCritic
from env.panopticon_env import PanopticonEnv
from metrics import gauge

TRAIN_ITERATION = gauge("panopticon_train_iteration", "Current training iteration")
TRAIN_RED_RETURN = gauge("panopticon_train_red_return", "Mean Red return over the last 10 completed episodes")
TRAIN_BLUE_RETURN = gauge("panopticon_train_blue_return", "Mean Blue return over the last 10 completed episodes")
TRAIN_RED_POLICY_LOSS = gauge("panopticon_train_red_policy_loss", "Red PPO policy loss, most recent update")
TRAIN_BLUE_POLICY_LOSS = gauge("panopticon_train_blue_policy_loss", "Blue PPO policy loss, most recent update")


def _maybe_start_metrics_server(cfg: dict):
    """Starts a bare prometheus_client HTTP server (train.py is a script,
    not a FastAPI app, so there's no app to mount /metrics onto) unless
    disabled in config. Logs and continues rather than crashing training
    if the port is already taken — a second concurrent run on the same
    machine shouldn't lose its training progress just because Prometheus
    scraping couldn't also start."""
    obs_cfg = cfg.get("observability", {})
    if not obs_cfg.get("metrics_enabled", True):
        return
    try:
        from prometheus_client import start_http_server
        start_http_server(obs_cfg.get("metrics_port", 9500))
        print(f"[train] metrics server listening on :{obs_cfg.get('metrics_port', 9500)}/metrics")
    except OSError as exc:
        print(f"[train] metrics server failed to start ({exc}); continuing without it")


class RolloutBuffer:
    """Fixed-length per-agent rollout storage for one PPO update."""

    def __init__(self, length: int, obs_dim: int):
        self.length = length
        self.obs = np.zeros((length, obs_dim), dtype=np.float32)
        self.actions = np.zeros(length, dtype=np.int64)
        self.log_probs = np.zeros(length, dtype=np.float32)
        self.values = np.zeros(length, dtype=np.float32)
        self.rewards = np.zeros(length, dtype=np.float32)
        self.dones = np.zeros(length, dtype=np.float32)
        self._ptr = 0

    def add(self, obs, action, log_prob, value, reward, done):
        i = self._ptr
        self.obs[i] = obs
        self.actions[i] = action
        self.log_probs[i] = log_prob
        self.values[i] = value
        self.rewards[i] = reward
        self.dones[i] = done
        self._ptr += 1

    def full(self) -> bool:
        return self._ptr >= self.length

    def reset(self):
        self._ptr = 0

    def compute_gae(self, last_value: float, gamma: float, lam: float):
        advantages = np.zeros(self.length, dtype=np.float32)
        last_adv = 0.0
        for t in reversed(range(self.length)):
            next_value = last_value if t == self.length - 1 else self.values[t + 1]
            next_nonterminal = 1.0 - self.dones[t]
            delta = self.rewards[t] + gamma * next_value * next_nonterminal - self.values[t]
            last_adv = delta + gamma * lam * next_nonterminal * last_adv
            advantages[t] = last_adv
        returns = advantages + self.values
        return advantages, returns


def ppo_update(model, optimizer, buffer: RolloutBuffer, advantages, returns, cfg: dict):
    obs = torch.as_tensor(buffer.obs)
    actions = torch.as_tensor(buffer.actions)
    old_log_probs = torch.as_tensor(buffer.log_probs)
    advantages_t = torch.as_tensor(advantages)
    returns_t = torch.as_tensor(returns)
    advantages_t = (advantages_t - advantages_t.mean()) / (advantages_t.std() + 1e-8)

    n = buffer.length
    indices = np.arange(n)
    clip = cfg["clip_range"]

    last_stats = {}
    for _ in range(cfg["epochs_per_update"]):
        np.random.shuffle(indices)
        for start in range(0, n, cfg["minibatch_size"]):
            mb = indices[start:start + cfg["minibatch_size"]]
            mb_obs, mb_actions = obs[mb], actions[mb]
            mb_old_log_probs, mb_adv, mb_ret = old_log_probs[mb], advantages_t[mb], returns_t[mb]

            new_log_probs, values, entropy = model.evaluate_actions(mb_obs, mb_actions)
            ratio = torch.exp(new_log_probs - mb_old_log_probs)

            surr1 = ratio * mb_adv
            surr2 = torch.clamp(ratio, 1 - clip, 1 + clip) * mb_adv
            policy_loss = -torch.min(surr1, surr2).mean()
            value_loss = nn.functional.mse_loss(values, mb_ret)
            entropy_bonus = entropy.mean()

            loss = policy_loss + cfg["value_loss_coef"] * value_loss - cfg["entropy_coef"] * entropy_bonus

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), cfg["max_grad_norm"])
            optimizer.step()

            last_stats = {
                "policy_loss": policy_loss.item(),
                "value_loss": value_loss.item(),
                "entropy": entropy_bonus.item(),
            }
    return last_stats


def train(config_path: str, iterations: int | None, run_id: str | None):
    with open(config_path) as fh:
        cfg = yaml.safe_load(fh)

    _maybe_start_metrics_server(cfg)

    env = PanopticonEnv(mode=cfg["env"]["mode"], max_steps=cfg["env"]["max_steps"], seed=cfg["env"]["seed"])
    obs, _ = env.reset(seed=cfg["env"]["seed"])

    obs_dims = {a: env.observation_space(a).shape[0] for a in env.possible_agents}
    n_actions = {a: env.action_space(a).n for a in env.possible_agents}
    hidden = cfg["network"]["hidden_size"]

    models = {a: ActorCritic(obs_dims[a], n_actions[a], hidden) for a in env.possible_agents}
    optimizers = {a: torch.optim.Adam(models[a].parameters(), lr=cfg["ppo"]["learning_rate"]) for a in env.possible_agents}

    run_id = run_id or time.strftime("run_%Y%m%d_%H%M%S")
    ckpt_dir = os.path.join(os.path.dirname(__file__), cfg["checkpointing"]["checkpoint_dir"], run_id)
    ckpt_mgr = CheckpointManager(ckpt_dir, keep_last_n=cfg["checkpointing"]["keep_last_n"])

    steps_per_iter = cfg["rollout"]["steps_per_iteration"]
    n_iterations = iterations or max(1, cfg["rollout"]["total_timesteps"] // steps_per_iter)

    episode_returns = {a: 0.0 for a in env.possible_agents}
    completed_returns = {a: [] for a in env.possible_agents}

    print(f"[train] run_id={run_id} iterations={n_iterations} steps/iter={steps_per_iter} mode={cfg['env']['mode']}")

    for iteration in range(1, n_iterations + 1):
        buffers = {a: RolloutBuffer(steps_per_iter, obs_dims[a]) for a in env.possible_agents}

        for _ in range(steps_per_iter):
            if not env.agents:
                obs, _ = env.reset()

            actions, log_probs, values = {}, {}, {}
            for a in env.possible_agents:
                obs_t = torch.as_tensor(obs[a]).unsqueeze(0)
                with torch.no_grad():
                    action_t, log_prob_t, value_t, _ = models[a].act(obs_t)
                actions[a] = int(action_t.item())
                log_probs[a] = float(log_prob_t.item())
                values[a] = float(value_t.item())

            next_obs, rewards, terminations, truncations, infos = env.step(actions)
            done_flag = 1.0 if not env.agents else 0.0

            for a in env.possible_agents:
                buffers[a].add(obs[a], actions[a], log_probs[a], values[a], rewards[a], done_flag)
                episode_returns[a] += rewards[a]

            if done_flag:
                for a in env.possible_agents:
                    completed_returns[a].append(episode_returns[a])
                    episode_returns[a] = 0.0
                obs, _ = env.reset()
            else:
                obs = next_obs

        stats = {}
        for a in env.possible_agents:
            with torch.no_grad():
                _, last_value = models[a].forward(torch.as_tensor(obs[a]).unsqueeze(0))
            advantages, returns = buffers[a].compute_gae(float(last_value.item()), cfg["ppo"]["gamma"], cfg["ppo"]["gae_lambda"])
            stats[a] = ppo_update(models[a], optimizers[a], buffers[a], advantages, returns, cfg["ppo"])

        if iteration % cfg["logging"]["log_every_iterations"] == 0:
            mean_returns = {a: (np.mean(completed_returns[a][-10:]) if completed_returns[a] else float("nan"))
                            for a in env.possible_agents}
            print(f"[train] iter {iteration}/{n_iterations} "
                  f"red_return={mean_returns['red']:.3f} blue_return={mean_returns['blue']:.3f} "
                  f"red_loss={stats['red']['policy_loss']:.4f} blue_loss={stats['blue']['policy_loss']:.4f}")

            TRAIN_ITERATION.set(iteration)
            if not np.isnan(mean_returns["red"]):
                TRAIN_RED_RETURN.set(mean_returns["red"])
            if not np.isnan(mean_returns["blue"]):
                TRAIN_BLUE_RETURN.set(mean_returns["blue"])
            TRAIN_RED_POLICY_LOSS.set(stats["red"]["policy_loss"])
            TRAIN_BLUE_POLICY_LOSS.set(stats["blue"]["policy_loss"])

        if iteration % cfg["checkpointing"]["save_every_iterations"] == 0 or iteration == n_iterations:
            path = ckpt_mgr.save(iteration, {
                a: {"model": models[a].state_dict(), "obs_dim": obs_dims[a], "n_actions": n_actions[a], "hidden_size": hidden}
                for a in env.possible_agents
            })
            print(f"[train] checkpoint saved -> {path}")

    return run_id, ckpt_dir


def main():
    parser = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    parser.add_argument("--config", default=os.path.join(here, "..", "configs", "ppo_config.yaml"))
    parser.add_argument("--iterations", type=int, default=None, help="Override total iterations for a quick run")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    train(args.config, args.iterations, args.run_id)


if __name__ == "__main__":
    main()
