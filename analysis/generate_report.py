"""Rolls an evaluate.py JSON log into one shareable, self-contained HTML
report — plots embedded as base64 so there's exactly one file to send
someone, no separate PNGs to lose track of.

    python3 generate_report.py --log eval.json --out report.html
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics
from plot_results import plot_returns, plot_health_over_time

_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Panopticon Evaluation Report</title>
<style>
  body {{ background:#0B0E14; color:#E9EDF4; font-family: ui-monospace, monospace; padding: 32px; max-width: 900px; margin: 0 auto; }}
  h1 {{ font-size: 20px; letter-spacing: .04em; }}
  table {{ width: 100%; border-collapse: collapse; margin: 16px 0 32px; font-size: 13px; }}
  td, th {{ padding: 8px 10px; border-bottom: 1px solid #222C3D; text-align: left; }}
  th {{ color: #8A94A6; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; }}
  img {{ width: 100%; border-radius: 8px; border: 1px solid #222C3D; margin-bottom: 24px; }}
</style></head>
<body>
  <h1>PANOPTICON — Evaluation Report</h1>
  <p style="color:#8A94A6">Generated from {episode_count} episodes.</p>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    {rows}
  </table>
  <img src="data:image/png;base64,{returns_b64}" alt="returns" />
  <img src="data:image/png;base64,{health_b64}" alt="health over time" />
</body></html>
"""


def _fig_to_base64(plot_fn, episodes) -> str:
    buf = io.BytesIO()
    fig_path = "/tmp/_panopticon_report_tmp.png"
    plot_fn(episodes, fig_path)
    with open(fig_path, "rb") as fh:
        encoded = base64.b64encode(fh.read()).decode("ascii")
    os.remove(fig_path)
    return encoded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True)
    parser.add_argument("--out", default="report.html")
    args = parser.parse_args()

    with open(args.log) as fh:
        data = json.load(fh)
    episodes = data["episodes"]
    summary = data.get("summary") or metrics.summarize(episodes)

    rows = "\n".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in summary.items())
    returns_b64 = _fig_to_base64(plot_returns, episodes)
    health_b64 = _fig_to_base64(plot_health_over_time, episodes)

    html = _TEMPLATE.format(episode_count=len(episodes), rows=rows, returns_b64=returns_b64, health_b64=health_b64)
    with open(args.out, "w") as fh:
        fh.write(html)
    print(f"[generate_report] wrote {args.out}")


if __name__ == "__main__":
    main()
