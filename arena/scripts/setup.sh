#!/usr/bin/env bash
# Brings the Arena up from nothing: applies manifests in order, waits for
# readiness, seeds the database. Run from the Arena laptop (laptop 04).
set -euo pipefail

NAMESPACE="${PANOPTICON_NAMESPACE:-panopticon-arena}"
KDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../k8s" && pwd)"

echo "==> Applying manifests from ${KDIR}"
kubectl apply -f "${KDIR}/00-namespace.yaml"

for manifest in 01-postgres.yaml 02-target-app.yaml 03-honeypot.yaml 04-network-policies.yaml 05-observer-daemonset.yaml 06-blue-rbac.yaml; do
  echo "==> Applying ${manifest}"
  kubectl apply -f "${KDIR}/${manifest}"
done

echo "==> Waiting for postgres to be ready..."
kubectl -n "${NAMESPACE}" rollout status deployment/postgres --timeout=120s

echo "==> Waiting for target-app to be ready..."
kubectl -n "${NAMESPACE}" rollout status deployment/target-app --timeout=120s

echo "==> Waiting for honeypot to be ready..."
kubectl -n "${NAMESPACE}" rollout status deployment/honeypot --timeout=120s

echo "==> Arena is up. Service endpoints inside the cluster:"
kubectl -n "${NAMESPACE}" get svc
echo
echo "Done. Run scripts/reset.sh between training episodes, scripts/cleanup.sh to tear everything down."
