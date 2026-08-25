#!/usr/bin/env bash
# Returns the Arena to a clean state between training episodes WITHOUT
# tearing down the cluster: restarts target-app (clears any in-process
# state), truncates mutable tables, and resets the honeypot.
set -euo pipefail

NAMESPACE="${PANOPTICON_NAMESPACE:-panopticon-arena}"

echo "==> Restarting target-app and honeypot..."
kubectl -n "${NAMESPACE}" rollout restart deployment/target-app
kubectl -n "${NAMESPACE}" rollout restart deployment/honeypot
kubectl -n "${NAMESPACE}" rollout status deployment/target-app --timeout=60s
kubectl -n "${NAMESPACE}" rollout status deployment/honeypot --timeout=60s

echo "==> Truncating mutable tables in postgres..."
PG_POD="$(kubectl -n "${NAMESPACE}" get pod -l app=postgres -o jsonpath='{.items[0].metadata.name}')"
kubectl -n "${NAMESPACE}" exec "${PG_POD}" -- \
  psql -U panopticon -d arena -c "TRUNCATE orders; DELETE FROM users WHERE id > 3;" || \
  echo "    (table truncate skipped — schema may not exist yet on first run)"

echo "==> Episode reset complete."
