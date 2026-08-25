#!/usr/bin/env bash
# Full stop: deletes everything the Arena created, including the namespace.
set -euo pipefail

NAMESPACE="${PANOPTICON_NAMESPACE:-panopticon-arena}"
KDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../k8s" && pwd)"

read -r -p "This deletes the entire '${NAMESPACE}' namespace. Continue? [y/N] " confirm
if [[ "${confirm}" != "y" && "${confirm}" != "Y" ]]; then
  echo "Aborted."
  exit 1
fi

kubectl delete -f "${KDIR}" --ignore-not-found=true
echo "==> Arena torn down."
