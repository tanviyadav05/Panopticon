# Panopticon: five Windows laptop installation

> For the revised bundle's role-specific setup and troubleshooting flow, use
> [`FIVE_LAPTOP_EASY_SETUP.md`](FIVE_LAPTOP_EASY_SETUP.md) first. This longer
> document remains as the detailed reference for K3s RBAC and fallback cases.

This is the Windows deployment runbook for Project Panopticon. It assumes
five Windows laptops, one isolated switch, and only systems or devices you
own or are explicitly authorized to use.

Important design choice: this is a Windows-hosted deployment, not a pure
Windows-native rewrite. Panopticon uses K3s, Linux containers, Kubernetes
network policies, and Linux process/metrics tooling. Those pieces run inside
Ubuntu on WSL2. The laptops, browser GUI, Windows networking, firewall, file
copying, and operator workflow are all Windows.

## 0. Read this first

- Use Windows 11 22H2 or newer if possible. Windows 10 can work, but you
  will almost certainly need the port-proxy fallback in section 5.
- Enable virtualization in BIOS/UEFI on all five laptops.
- Do the downloads while temporarily online. After that, move the laptops to
  the isolated switch with no internet uplink.
- Red actions are simulated effects only. Red does not run live exploits.
- Blue can make real Kubernetes changes in the Arena namespace, but live
  Blue containment is disarmed by default at both the Blue service and the
  command dashboard.
- Laptop 01 should have 32 GB RAM if you want the Hermes, Dolphin, and Qwen
  models to stay warm. More is better. The other laptops can usually run with
  8 GB RAM. Laptop 04 needs at least 20 GB free disk for K3s images.

## 1. Laptop roles and addresses

Use these names and IP addresses throughout the setup.

| Laptop | Windows computer name | IPv4 address | Runs |
|---|---|---:|---|
| 01 | `llm-laptop` | `192.168.50.11` | Ollama, `llm-core` |
| 02 | `red-laptop` | `192.168.50.12` | Red automated agent |
| 03 | `blue-laptop` | `192.168.50.13` | Blue automated agent |
| 04 | `arena-laptop` | `192.168.50.14` | K3s, target app, honeypot, observer |
| 05 | `command-laptop` | `192.168.50.15` | GUI dashboard, referee, training, Grafana |

Ports used on the isolated network:

| Port | Laptop | Purpose |
|---:|---|---|
| 8090 | 01 | LLM gateway |
| 8081 | 02 | Red agent API |
| 8082 | 03 | Blue agent API |
| 6443 | 04 | K3s Kubernetes API |
| 30080 | 04 | Published Arena target app for Windows deployment |
| 8000 | 05 | Panopticon GUI dashboard |
| 9600 | 05 | Referee live telemetry ingest |
| 9500 | 05 | Referee training metrics |
| 9090 | 05 | Prometheus |
| 3000 | 05 | Grafana |
| 9100 | all | Linux node exporter inside WSL, optional |

## 2. Install Windows prerequisites on all five laptops

Run this in Windows PowerShell as Administrator on each laptop.

```powershell
winget --version
wsl --list --online
wsl --install -d Ubuntu-24.04
wsl --set-default-version 2
wsl --update
Restart-Computer
```

If `Ubuntu-24.04` is not listed, install `Ubuntu` instead and replace
`Ubuntu-24.04` with your actual distro name in every later `wsl -d ...`
command.

After the restart, open Ubuntu from the Start menu once and create the Linux
username/password when prompted. Then run this in Windows PowerShell:

```powershell
wsl -l -v
```

The Ubuntu distribution must show version `2`. If it does not:

```powershell
wsl --set-version Ubuntu-24.04 2
```

Inside Ubuntu WSL on every laptop, enable systemd and install the common
Linux tools:

```bash
sudo tee /etc/wsl.conf >/dev/null <<'EOF'
[boot]
systemd=true
EOF
exit
```

Back in Windows PowerShell:

```powershell
wsl --shutdown
```

Open Ubuntu again and run:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y python3.12 python3.12-venv python3-pip git curl jq unzip \
  ca-certificates build-essential pkg-config kubernetes-client rsync \
  iproute2 iputils-ping net-tools
systemctl is-system-running
```

`systemctl is-system-running` may print `running` or `degraded`; either is
fine as long as `systemctl status` works.

## 3. Copy the project onto each laptop

Put `project-panopticon-local-control.zip` on each Windows laptop, for
example in `C:\Panopticon`.

Run this in Windows PowerShell on each laptop:

```powershell
New-Item -ItemType Directory -Force C:\Panopticon | Out-Null
Expand-Archive C:\Panopticon\project-panopticon-local-control.zip -DestinationPath C:\Panopticon -Force
Get-ChildItem C:\Panopticon
```

Now copy the project into WSL's Linux filesystem. Do not run the project
directly from `/mnt/c`; WSL file I/O is much slower there.

Run this inside Ubuntu WSL on each laptop:

```bash
sudo mkdir -p /opt/panopticon
sudo rsync -a --delete /mnt/c/Panopticon/project-panopticon/ /opt/panopticon/
sudo chown -R "$USER:$USER" /opt/panopticon
cd /opt/panopticon
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip wheel
.venv/bin/pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

If the extracted folder name is different, check it with:

```bash
ls /mnt/c/Panopticon
```

Then adjust the `rsync` source path.

## 4. Configure the isolated Windows network

Do this after downloads are complete. Plug only the five laptops into the
dedicated switch. Do not connect the switch to your home router, campus
network, or the internet.

On each laptop, run Windows PowerShell as Administrator and set the computer
name. Use the correct name from the table in section 1.

```powershell
Rename-Computer -NewName llm-laptop -Restart
```

After the restart, set the static IPv4 address for the wired Ethernet
adapter. First find the adapter name:

```powershell
Get-NetAdapter
```

Use the real interface alias in the next commands. This example is for
Laptop 01.

```powershell
$iface = "Ethernet"
Set-NetIPInterface -InterfaceAlias $iface -Dhcp Disabled
Remove-NetIPAddress -InterfaceAlias $iface -AddressFamily IPv4 -Confirm:$false -ErrorAction SilentlyContinue
New-NetIPAddress -InterfaceAlias $iface -IPAddress 192.168.50.11 -PrefixLength 24
Set-DnsClientServerAddress -InterfaceAlias $iface -ResetServerAddresses
```

Use these IPs on the other laptops:

```text
Laptop 02 red-laptop      192.168.50.12
Laptop 03 blue-laptop     192.168.50.13
Laptop 04 arena-laptop    192.168.50.14
Laptop 05 command-laptop  192.168.50.15
```

Turn off Wi-Fi while running the live lab:

```powershell
Disable-NetAdapter -Name "Wi-Fi" -Confirm:$false
```

Add hostnames on Windows. Run Notepad as Administrator:

```powershell
notepad C:\Windows\System32\drivers\etc\hosts
```

Append:

```text
192.168.50.11 llm-laptop
192.168.50.12 red-laptop
192.168.50.13 blue-laptop
192.168.50.14 arena-laptop
192.168.50.15 command-laptop
```

Add the same hostnames inside Ubuntu WSL on every laptop:

```bash
sudo tee -a /etc/hosts >/dev/null <<'EOF'
192.168.50.11 llm-laptop
192.168.50.12 red-laptop
192.168.50.13 blue-laptop
192.168.50.14 arena-laptop
192.168.50.15 command-laptop
EOF
```

From Windows PowerShell on every laptop:

```powershell
ping llm-laptop
ping red-laptop
ping blue-laptop
ping arena-laptop
ping command-laptop
```

Do not continue until all five names resolve and ping.

## 5. Make WSL services reachable from the other laptops

Preferred path for Windows 11 22H2 or newer: WSL mirrored networking.

Run this in Windows PowerShell as Administrator on every laptop:

```powershell
@"
[wsl2]
networkingMode=mirrored
dnsTunneling=true
autoProxy=false
"@ | Set-Content "$env:USERPROFILE\.wslconfig" -Encoding ascii

wsl --shutdown
Set-NetFirewallHyperVVMSetting -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -DefaultInboundAction Allow
```

If `Set-NetFirewallHyperVVMSetting` is not available on your Windows build,
continue with the port-proxy fallback below.

Reopen Ubuntu. After the Panopticon services are running, test from another
laptop with:

```powershell
Test-NetConnection llm-laptop -Port 8090
```

If mirrored networking does not work on your Windows build, use this
port-proxy fallback. Run it in Windows PowerShell as Administrator on the
laptop that owns the ports.

Laptop 01:

```powershell
$ports = @(8090,9100)
$wslIp = (wsl -d Ubuntu-24.04 hostname -I).Trim().Split()[0]
foreach ($p in $ports) {
  netsh interface portproxy delete v4tov4 listenport=$p listenaddress=0.0.0.0 2>$null
  netsh interface portproxy add v4tov4 listenport=$p listenaddress=0.0.0.0 connectport=$p connectaddress=$wslIp
  New-NetFirewallRule -DisplayName "Panopticon TCP $p" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $p -ErrorAction SilentlyContinue
}
```

Laptop 02:

```powershell
$ports = @(8081,9100)
$wslIp = (wsl -d Ubuntu-24.04 hostname -I).Trim().Split()[0]
foreach ($p in $ports) {
  netsh interface portproxy delete v4tov4 listenport=$p listenaddress=0.0.0.0 2>$null
  netsh interface portproxy add v4tov4 listenport=$p listenaddress=0.0.0.0 connectport=$p connectaddress=$wslIp
  New-NetFirewallRule -DisplayName "Panopticon TCP $p" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $p -ErrorAction SilentlyContinue
}
```

Laptop 03:

```powershell
$ports = @(8082,9100)
$wslIp = (wsl -d Ubuntu-24.04 hostname -I).Trim().Split()[0]
foreach ($p in $ports) {
  netsh interface portproxy delete v4tov4 listenport=$p listenaddress=0.0.0.0 2>$null
  netsh interface portproxy add v4tov4 listenport=$p listenaddress=0.0.0.0 connectport=$p connectaddress=$wslIp
  New-NetFirewallRule -DisplayName "Panopticon TCP $p" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $p -ErrorAction SilentlyContinue
}
```

Laptop 04:

```powershell
$ports = @(6443,30080,9100)
$wslIp = (wsl -d Ubuntu-24.04 hostname -I).Trim().Split()[0]
foreach ($p in $ports) {
  netsh interface portproxy delete v4tov4 listenport=$p listenaddress=0.0.0.0 2>$null
  netsh interface portproxy add v4tov4 listenport=$p listenaddress=0.0.0.0 connectport=$p connectaddress=$wslIp
  New-NetFirewallRule -DisplayName "Panopticon TCP $p" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $p -ErrorAction SilentlyContinue
}
```

Laptop 05:

```powershell
$ports = @(8000,9600,9500,9090,3000,9100)
$wslIp = (wsl -d Ubuntu-24.04 hostname -I).Trim().Split()[0]
foreach ($p in $ports) {
  netsh interface portproxy delete v4tov4 listenport=$p listenaddress=0.0.0.0 2>$null
  netsh interface portproxy add v4tov4 listenport=$p listenaddress=0.0.0.0 connectport=$p connectaddress=$wslIp
  New-NetFirewallRule -DisplayName "Panopticon TCP $p" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $p -ErrorAction SilentlyContinue
}
```

With NAT-mode WSL, the WSL IP can change after reboot. Re-run the matching
port-proxy block after every `wsl --shutdown` or Windows restart.

## 6. Laptop 01: local LLM

Run inside Ubuntu WSL on Laptop 01:

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull hermes3:8b
ollama pull dolphin-llama3:8b
ollama pull qwen3:8b-q4_K_M
ollama list
curl http://127.0.0.1:11434/api/generate \
  -d '{"model":"hermes3:8b","prompt":"Reply with LOCAL_OK","stream":false}'
```

The research note names Qwen3 7B Q4_K_M for the Coder and Critic. This
guide uses the pullable `qwen3:8b-q4_K_M` tag by default. If you import an
exact 7B Q4_K_M GGUF into Ollama, edit
`/opt/panopticon/llm-core/config/agents_config.yaml` and replace both
Qwen tags with your imported tag.

Edit `/opt/panopticon/.env` on Laptop 01:

```bash
cd /opt/panopticon
nano .env
```

Set:

```text
OLLAMA_HOST=http://127.0.0.1:11434
LLM_BACKEND=ollama
LLM_OLLAMA_URL=http://127.0.0.1:11434/api/generate
LLM_OLLAMA_MODEL=hermes3:8b
PORT=8090
```

Start the LLM gateway:

```bash
cd /opt/panopticon
set -a; . ./.env; set +a
.venv/bin/python llm-core/server/llm_server.py
```

Leave that terminal open. In a second Ubuntu terminal on Laptop 01:

```bash
curl -s http://127.0.0.1:8090/health | jq .
curl -s http://127.0.0.1:8090/agents | jq .
curl -s -X POST http://127.0.0.1:8090/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Reply with LOCAL_OK only.","max_tokens":8,"temperature":0}' | jq .
```

From Laptop 05 Windows PowerShell:

```powershell
Test-NetConnection llm-laptop -Port 8090
```

## 7. Laptop 04: Arena with K3s

Install Docker Desktop for Windows on Laptop 04 while temporarily online:

```powershell
winget install --id Docker.DockerDesktop -e
```

Open Docker Desktop once, enable the WSL 2 engine, and enable integration
for `Ubuntu-24.04` under Settings, Resources, WSL Integration.

Install K3s inside Ubuntu WSL on Laptop 04. The `--tls-san` values matter
because the Blue laptop will reach the Kubernetes API through
`https://arena-laptop:6443`.

```bash
curl -sfL https://get.k3s.io | sh -s - server \
  --tls-san arena-laptop \
  --tls-san 192.168.50.14
sudo systemctl enable --now k3s
sudo k3s kubectl get nodes
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown "$USER:$USER" ~/.kube/config
sed -i 's/127.0.0.1/arena-laptop/g' ~/.kube/config
export KUBECONFIG="$HOME/.kube/config"
```

Build the local images and import them into K3s:

```bash
cd /opt/panopticon
docker version
docker build -t panopticon/target-app:latest arena/target-app
docker build -t panopticon/observer:latest -f observer/Dockerfile .
docker save panopticon/target-app:latest | sudo k3s ctr images import -
docker save panopticon/observer:latest | sudo k3s ctr images import -
sudo k3s ctr images list | grep panopticon
```

Start the Arena:

```bash
cd /opt/panopticon/arena
export KUBECONFIG="$HOME/.kube/config"
./scripts/setup.sh
kubectl -n panopticon-arena get pods -o wide
kubectl -n panopticon-arena get svc
```

Publish the target app on a stable Windows-friendly port:

```bash
kubectl -n panopticon-arena patch svc target-app --type merge \
  -p '{"spec":{"type":"NodePort","ports":[{"port":80,"targetPort":8080,"nodePort":30080,"protocol":"TCP"}]}}'
curl -s http://127.0.0.1:30080/health
```

If `curl` does not reach the app, check:

```bash
kubectl -n panopticon-arena get svc target-app -o wide
kubectl -n panopticon-arena get pods
sudo systemctl status k3s --no-pager
```

## 8. Create the least-privilege Blue kubeconfig

Run inside Ubuntu WSL on Laptop 04:

```bash
cd /opt/panopticon
kubectl apply -f arena/k8s/06-blue-rbac.yaml
BLUE_TOKEN="$(kubectl -n panopticon-arena create token panopticon-blue)"
CA_DATA="$(awk '/certificate-authority-data:/ {print $2}' "$HOME/.kube/config")"
cat > /tmp/panopticon-blue.kubeconfig <<EOF
apiVersion: v1
kind: Config
clusters:
- name: panopticon-arena
  cluster:
    certificate-authority-data: ${CA_DATA}
    server: https://arena-laptop:6443
contexts:
- name: panopticon-blue@panopticon-arena
  context:
    cluster: panopticon-arena
    namespace: panopticon-arena
    user: panopticon-blue
current-context: panopticon-blue@panopticon-arena
users:
- name: panopticon-blue
  user:
    token: ${BLUE_TOKEN}
EOF
cp /tmp/panopticon-blue.kubeconfig /mnt/c/Panopticon/panopticon-blue.kubeconfig
```

Move `C:\Panopticon\panopticon-blue.kubeconfig` to Laptop 03, placing it in
`C:\Panopticon` there. Then run inside Ubuntu WSL on Laptop 03:

```bash
mkdir -p "$HOME/.kube"
cp /mnt/c/Panopticon/panopticon-blue.kubeconfig "$HOME/.kube/config"
chmod 600 "$HOME/.kube/config"
export KUBECONFIG="$HOME/.kube/config"
kubectl auth can-i patch services -n panopticon-arena
kubectl auth can-i create networkpolicies -n panopticon-arena
kubectl auth can-i delete pods -n panopticon-arena
```

The first two checks should be `yes`. The pod delete check should be `no`.

## 9. Laptop 03: Blue automated agent

Edit `/opt/panopticon/.env` on Laptop 03:

```bash
cd /opt/panopticon
nano .env
```

Set:

```text
KUBECONFIG=/home/<your-wsl-username>/.kube/config
LLM_GATEWAY_URL=http://llm-laptop:8090
BLUE_CHECKPOINT_PATH=
BLUE_LIVE_ACTIONS_ARMED=0
BLUE_AUTONOMY_APPLY=0
PORT=8082
```

Replace `<your-wsl-username>` with the output of:

```bash
whoami
```

Start Blue:

```bash
cd /opt/panopticon
set -a; . ./.env; set +a
.venv/bin/python blue-team/countermeasures/blue_controller.py
```

Verify from Laptop 03:

```bash
curl -s http://127.0.0.1:8082/health | jq .
```

Verify from Laptop 05 Windows PowerShell:

```powershell
Test-NetConnection blue-laptop -Port 8082
```

## 10. Laptop 02: Red automated agent

Edit `/opt/panopticon/.env` on Laptop 02:

```bash
cd /opt/panopticon
nano .env
```

Set:

```text
LLM_GATEWAY_URL=http://llm-laptop:8090
RED_CHECKPOINT_PATH=
PORT=8081
```

Start Red:

```bash
cd /opt/panopticon
set -a; . ./.env; set +a
.venv/bin/python red-team/attacks/red_attacker.py
```

Verify from Laptop 02:

```bash
curl -s http://127.0.0.1:8081/health | jq .
curl -s http://127.0.0.1:8081/attacks | jq .
```

Verify from Laptop 05 Windows PowerShell:

```powershell
Test-NetConnection red-laptop -Port 8081
```

## 11. Laptop 05: GUI dashboard and referee

Edit `/opt/panopticon/.env` on Laptop 05:

```bash
cd /opt/panopticon
nano .env
```

Set:

```text
PANOPTICON_DEMO=0
PANOPTICON_RED_URL=http://red-laptop:8081
PANOPTICON_BLUE_URL=http://blue-laptop:8082
LLM_GATEWAY_URL=http://llm-laptop:8090
PANOPTICON_BLUE_LIVE_ARMED=0
PANOPTICON_CONTROL_TOKEN=
PORT=8000
```

Optional but recommended even on the closed switch:

```bash
openssl rand -hex 32
```

Put that value in `PANOPTICON_CONTROL_TOKEN`. You will type it into the GUI
control-token field when sending write commands.

Because the Windows deployment publishes the target app on `arena-laptop:30080`,
adjust Prometheus before starting it:

```bash
cd /opt/panopticon
sed -i 's/arena-laptop:80/arena-laptop:30080/g' observability/prometheus/prometheus.yml
```

Start the GUI dashboard:

```bash
cd /opt/panopticon
set -a; . ./.env; set +a
.venv/bin/python monitoring/dashboard_server.py
```

Open this in a Windows browser:

```text
http://command-laptop:8000
```

The Command Console section controls:

- Red manual/simulated actions.
- Blue manual defense actions.
- Referee reset/step/policy-step actions.
- Local LLM analysis through Laptop 01.

## 12. Observability on Windows laptops

The included node exporter script runs inside WSL and reports the Linux
service layer. It does not replace Windows-native host telemetry.

Run inside Ubuntu WSL on every laptop:

```bash
cd /opt/panopticon/observability/node_exporter
sudo ./install_node_exporter.sh
systemctl status node_exporter --no-pager
```

On Laptop 05, install Docker Desktop for Windows if it is not already
installed:

```powershell
winget install --id Docker.DockerDesktop -e
```

Enable Docker Desktop WSL integration for `Ubuntu-24.04`, then run inside
Ubuntu WSL on Laptop 05:

```bash
cd /opt/panopticon/observability
docker compose up -d
docker compose ps
```

Open:

```text
http://command-laptop:3000
http://command-laptop:9090
```

Grafana default login is:

```text
admin / panopticon
```

Change it after first login.

## 13. End-to-end validation

Run these from Laptop 05.

Windows PowerShell network checks:

```powershell
Test-NetConnection llm-laptop -Port 8090
Test-NetConnection red-laptop -Port 8081
Test-NetConnection blue-laptop -Port 8082
Test-NetConnection arena-laptop -Port 6443
Test-NetConnection arena-laptop -Port 30080
Test-NetConnection command-laptop -Port 8000
```

Ubuntu WSL API checks:

```bash
curl -s http://llm-laptop:8090/health | jq .
curl -s http://red-laptop:8081/health | jq .
curl -s http://blue-laptop:8082/health | jq .
curl -s http://arena-laptop:30080/health
curl -s http://command-laptop:8000/control/status | jq .
```

Red automated dry run:

```bash
curl -s -X POST http://red-laptop:8081/autonomy/tick \
  -H 'Content-Type: application/json' \
  -d '{"observation":[0.1,0.2,0.1,0.2,0.1,0.0,0.0],"target_device_type":"webapp"}' | jq .
```

Blue automated dry run:

```bash
curl -s -X POST http://blue-laptop:8082/autonomy/tick \
  -H 'Content-Type: application/json' \
  -d '{"observation":[0.1,0.2,0.1,0.2,0.1,0.0,0.0,0.1,0.2,0.1,0.2,0.1,0.0,0.0],"use_llm":true,"apply":false}' | jq .
```

Referee local simulation step:

```bash
curl -s -X POST http://command-laptop:8000/control/referee/reset | jq .
curl -s -X POST http://command-laptop:8000/control/referee/step \
  -H 'Content-Type: application/json' \
  -d '{"red_action":0,"blue_action":0}' | jq .
```

The GUI should now show live service status, command results, and telemetry
updates.

## 14. Turning on live Blue containment

Keep Blue live actions off until all validation checks pass.

To allow manual live Blue containment:

1. On Laptop 03, edit `/opt/panopticon/.env`.
2. Change `BLUE_LIVE_ACTIONS_ARMED=0` to `BLUE_LIVE_ACTIONS_ARMED=1`.
3. Restart the Blue service terminal.
4. On Laptop 05, edit `/opt/panopticon/.env`.
5. Change `PANOPTICON_BLUE_LIVE_ARMED=0` to `PANOPTICON_BLUE_LIVE_ARMED=1`.
6. Restart the dashboard service terminal.
7. In the GUI, tick the live-action confirmation checkbox for each live Blue
   action.

To allow automated Blue decisions to apply live:

```text
BLUE_AUTONOMY_APPLY=1
```

Set that only on Laptop 03, and only after you are comfortable with the
policy behavior. Red remains simulated either way.

## 15. Optional training

Run inside Ubuntu WSL on Laptop 05:

```bash
cd /opt/panopticon
set -a; . ./.env; set +a
.venv/bin/python referee/training/train.py
```

Training is simulation-first. Use simulation to train policies, then validate
carefully with live Blue containment.

## 16. Shutdown

Stop Python services with `Ctrl+C` in their terminal windows.

On Laptop 04:

```bash
cd /opt/panopticon/arena
./scripts/cleanup.sh
sudo systemctl stop k3s
```

On Laptop 05:

```bash
cd /opt/panopticon/observability
docker compose down
```

On Windows, if you used portproxy and want to remove it:

```powershell
netsh interface portproxy reset
```

## 17. Troubleshooting

If another laptop cannot reach a service:

```powershell
Test-NetConnection red-laptop -Port 8081
```

Then on the service laptop:

```bash
ss -lntp | grep 8081
```

If the service listens in WSL but not from another laptop, fix section 5:
enable mirrored networking or re-run the port-proxy block after checking the
current WSL IP:

```powershell
wsl -d Ubuntu-24.04 hostname -I
netsh interface portproxy show all
```

If Blue cannot connect to Kubernetes:

```bash
kubectl --kubeconfig "$HOME/.kube/config" get svc -n panopticon-arena
```

If you see a TLS hostname error, reinstall K3s on Laptop 04 with the
`--tls-san arena-laptop --tls-san 192.168.50.14` flags from section 7, then
recreate the Blue kubeconfig.

If Ollama is reachable but `/agents` shows failed model calls:

```bash
ollama list
curl http://127.0.0.1:11434/api/generate \
  -d '{"model":"hermes3:8b","prompt":"Say OK","stream":false}'
```

The model names in `llm-core/config/agents_config.yaml` must exactly match
the tags shown by `ollama list`.

If Docker commands fail inside WSL:

1. Start Docker Desktop on Windows.
2. Open Docker Desktop settings.
3. Enable WSL integration for `Ubuntu-24.04`.
4. Reopen Ubuntu WSL.
5. Run `docker version`.

If the GUI loads but buttons fail:

```bash
curl -s http://command-laptop:8000/control/status | jq .
```

Check the configured URLs in Laptop 05's `.env`, then restart the dashboard.
