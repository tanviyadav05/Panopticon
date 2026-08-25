#!/usr/bin/env bash
# Verify the service(s) belonging to this laptop's role.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
set -a
. ./.env
set +a

case "${PANOPTICON_ROLE:-}" in
  llm) curl -fsS http://127.0.0.1:8090/health ;;
  red) curl -fsS http://127.0.0.1:8081/health ;;
  blue) curl -fsS http://127.0.0.1:8082/health ;;
  arena)
    export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
    kubectl -n "${PANOPTICON_NAMESPACE:-panopticon-arena}" get pods
    curl -fsS http://127.0.0.1:30080/health
    ;;
  command)
    curl -fsS http://127.0.0.1:8000/control/status
    curl -fsS http://127.0.0.1:9090/-/healthy
    ;;
  *) echo "PANOPTICON_ROLE is not configured"; exit 1 ;;
esac
echo
