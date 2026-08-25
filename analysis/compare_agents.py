"""Head-to-head comparison between two evaluate.py JSON logs.

    python3 compare_agents.py --log-a untrained_blue.json --log-b trained_blue.json \
        --label-a "untrained" --label-b "trained" --out comparison.png
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics


def load_episodes(path: str) -> list[dict]:
    with open(path) as fh:
        return json.load(fh)["episodes"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-a", required=True)
    parser.add_argument("--log-b", required=True)
    parser.add_argument("--label-a", default="A")
    parser.add_argument("--label-b", default="B")
    parser.add_argument("--out", default="comparison.png")
    args = parser.parse_args()

    episodes_a = load_episodes(args.log_a)
    episodes_b = load_episodes(args.log_b)
    summary_a = metrics.summarize(episodes_a)
    summary_b = metrics.summarize(episodes_b)

    print(f"=== {args.label_a} ===")
    for k, v in summary_a.items():
        print(f"  {k}: {v}")
    print(f"=== {args.label_b} ===")
    for k, v in summary_b.items():
        print(f"  {k}: {v}")

    keys = ["blue_win_rate", "mean_service_health", "mean_time_to_detect", "mean_time_to_exploit"]
    x = np.arange(len(keys))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(x - width / 2, [summary_a[k] for k in keys], width, label=args.label_a, color="#6B7686")
    ax.bar(x + width / 2, [summary_b[k] for k in keys], width, label=args.label_b, color="#36C7C0")
    ax.set_xticks(x)
    ax.set_xticklabels(keys, rotation=20, ha="right")
    ax.set_title(f"{args.label_a} vs {args.label_b}")
    ax.legend()
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    fig.savefig(args.out, dpi=150)
    plt.close(fig)
    print(f"[compare_agents] wrote {args.out}")


if __name__ == "__main__":
    main()
