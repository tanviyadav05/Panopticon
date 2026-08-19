#!/usr/bin/env bash
# observability/node_exporter/install_node_exporter.sh
#
# Run this on EACH of the 5 laptops (node_exporter must run natively on
# every machine to see that machine's own system metrics — see
# docs/observability.md for why this can't be centralized in one
# container the way Prometheus/Grafana are).
#
#   sudo ./install_node_exporter.sh
#
# Installs node_exporter as a systemd service listening on :9100 (the
# universal Prometheus convention — deployment/inventory.yaml reserves
# this port for exactly this on every laptop). The version below was
# downloaded and smoke-tested (binary runs, serves real
# node_cpu_seconds_total / node_memory_MemAvailable_bytes / etc.) as part
# of building this repo; override NODE_EXPORTER_VERSION for a newer
# release if you want one.
set -euo pipefail

NODE_EXPORTER_VERSION="${NODE_EXPORTER_VERSION:-1.8.2}"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64)  NE_ARCH="amd64" ;;
  aarch64) NE_ARCH="arm64" ;;
  *) echo "Unsupported architecture: $ARCH (node_exporter publishes amd64/arm64/armv7/etc — check https://github.com/prometheus/node_exporter/releases and set NE_ARCH manually if needed)"; exit 1 ;;
esac

TARBALL="node_exporter-${NODE_EXPORTER_VERSION}.linux-${NE_ARCH}.tar.gz"
URL="https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/${TARBALL}"

echo "==> Downloading node_exporter ${NODE_EXPORTER_VERSION} (${NE_ARCH})..."
curl -sL -H "User-Agent: panopticon-setup" "$URL" -o "/tmp/${TARBALL}"

echo "==> Extracting..."
tar xzf "/tmp/${TARBALL}" -C /tmp
BINARY_DIR="/tmp/node_exporter-${NODE_EXPORTER_VERSION}.linux-${NE_ARCH}"

echo "==> Installing to /usr/local/bin/node_exporter..."
sudo install -m 0755 "${BINARY_DIR}/node_exporter" /usr/local/bin/node_exporter
rm -rf "/tmp/${TARBALL}" "${BINARY_DIR}"

echo "==> Creating dedicated system user..."
if ! id -u node_exporter >/dev/null 2>&1; then
  sudo useradd --no-create-home --shell /usr/sbin/nologin node_exporter
fi

echo "==> Writing systemd unit..."
sudo tee /etc/systemd/system/node_exporter.service > /dev/null << 'EOF'
[Unit]
Description=Prometheus Node Exporter
After=network-online.target
Wants=network-online.target

[Service]
User=node_exporter
Group=node_exporter
Type=simple
ExecStart=/usr/local/bin/node_exporter --web.listen-address=:9100
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

echo "==> Starting node_exporter..."
sudo systemctl daemon-reload
sudo systemctl enable --now node_exporter

sleep 1
echo "==> Verifying..."
if curl -s "http://localhost:9100/metrics" | grep -q "^node_exporter_build_info"; then
  echo "node_exporter is up and serving real metrics on :9100"
else
  echo "node_exporter did not respond as expected — check: sudo systemctl status node_exporter"
  exit 1
fi
