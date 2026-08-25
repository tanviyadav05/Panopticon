"""Generates static plots from an evaluate.py --out JSON log.

    python3 plot_results.py --log /path/to/eval.json --out-dir ./plots
"""
from __future__ import annotations

import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")  # headless-safe; no X server assumed on any of the 5 laptops
import matplotlib.pyplot as plt
import numpy as np


def load_log(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


def plot_returns(episodes: list[dict], out_path: str):
    red_returns = [ep["red_return"] for ep in episodes]
    blue_returns = [ep["blue_return"] for ep in episodes]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(red_returns, label="Red return", color="#E0495C", linewidth=2)
    ax.plot(blue_returns, label="Blue return", color="#3E84F0", linewidth=2)
    ax.set_xlabel("Episode")
    ax.set_ylabel("Episode return")
    ax.set_title("Per-episode returns")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_health_over_time(episodes: list[dict], out_path: str, max_episodes_shown: int = 8):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for i, ep in enumerate(episodes[:max_episodes_shown]):
        ax.plot(ep["service_health"], alpha=0.7, linewidth=1.5, label=f"ep {i}")
    ax.set_xlabel("Step")
    ax.set_ylabel("Service health")
    ax.set_title(f"Service health over time (first {min(max_episodes_shown, len(episodes))} episodes)")
    ax.set_ylim(0, 1.05)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, help="Path to a JSON log written by referee/training/evaluate.py --out")
    parser.add_argument("--out-dir", default="./plots")
    args = parser.parse_args()

    data = load_log(args.log)
    episodes = data["episodes"]
    os.makedirs(args.out_dir, exist_ok=True)

    plot_returns(episodes, os.path.join(args.out_dir, "returns.png"))
    plot_health_over_time(episodes, os.path.join(args.out_dir, "health_over_time.png"))

    print(f"[plot_results] wrote {args.out_dir}/returns.png and {args.out_dir}/health_over_time.png")
    print(f"[plot_results] summary: {json.dumps(data.get('summary', {}), indent=2)}")


if __name__ == "__main__":
    main()
