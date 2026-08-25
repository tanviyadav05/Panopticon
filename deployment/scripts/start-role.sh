#!/usr/bin/env bash
# Start the one role configured in .env. Run this inside a dedicated terminal.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env. Copy one file from deployment/env/ first."
  exit 1
fi
set -a
. ./.env
set +a

case "${PANOPTICON_ROLE:-}" in
  llm)
    exec .venv/bin/python llm-core/server/llm_server.py
    ;;
  red)
    exec .venv/bin/python red-team/attacks/red_attacker.py
    ;;
  blue)
    exec .venv/bin/python blue-team/countermeasures/blue_controller.py
    ;;
  arena)
    export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
    sudo systemctl enable --now k3s
    docker build -t panopticon/target-app:latest arena/target-app
    docker build -t panopticon/observer:latest -f observer/Dockerfile .
    docker save panopticon/target-app:latest | sudo k3s ctr images import -
    docker save panopticon/observer:latest | sudo k3s ctr images import -
    ./arena/scripts/setup.sh
    kubectl -n "${PANOPTICON_NAMESPACE:-panopticon-arena}" get pods -o wide
    ;;
  command)
    (cd observability && docker compose up -d)
    exec .venv/bin/python monitoring/dashboard_server.py
    ;;
  *)
    echo "PANOPTICON_ROLE must be llm, red, blue, arena, or command."
    exit 1
    ;;
esac
