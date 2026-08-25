#!/usr/bin/env bash
# Fast stop: makes Red and Blue stop acting immediately, without tearing
# down the Arena (use arena/scripts/cleanup.sh for that). Safe to run from
# any of the 5 laptops if you have kubectl access to the others' clusters,
# or run the relevant half from each individual laptop if not.
set -euo pipefail

echo "==> Stopping local red_attacker.py / blue_controller.py processes (if running on this host)..."
pkill -f "red_attacker.py" 2>/dev/null && echo "    stopped red_attacker.py" || echo "    red_attacker.py not running here"
pkill -f "blue_controller.py" 2>/dev/null && echo "    stopped blue_controller.py" || echo "    blue_controller.py not running here"

echo "==> Stopping local training loop (if running on this host)..."
pkill -f "referee/training/train.py" 2>/dev/null && echo "    stopped train.py" || echo "    train.py not running here"

echo "==> If Red/Blue are deployed as Kubernetes workloads rather than bare processes,"
echo "    also run (from a host with the relevant kubeconfig):"
echo "      kubectl -n panopticon-arena scale deployment/red-attacker --replicas=0"
echo "      kubectl -n panopticon-arena scale deployment/blue-controller --replicas=0"
echo
echo "==> Kill switch complete. The Arena itself (target-app, postgres, honeypot) is still up;"
echo "    run arena/scripts/cleanup.sh if you want that gone too."
