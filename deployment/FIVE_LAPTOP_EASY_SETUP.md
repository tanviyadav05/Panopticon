# Panopticon five-laptop easy setup

Use this guide for the revised bundle. It has one role configuration per
laptop, fixed published ports, and one final Command-laptop test. Keep the
five laptops on the dedicated switch only; do not connect that switch to a
router, campus network, or the internet after the prerequisites are cached.

## The fixed layout

| Laptop | Windows name | Wired IP | Role | Main port |
|---|---|---:|---|---:|
| 01 | `llm-laptop` | `192.168.50.11` | Ollama + LLM gateway | 8090 |
| 02 | `red-laptop` | `192.168.50.12` | Red agent | 8081 |
| 03 | `blue-laptop` | `192.168.50.13` | Blue agent | 8082 |
| 04 | `arena-laptop` | `192.168.50.14` | K3s, Go target, Observer | 30080 |
| 05 | `command-laptop` | `192.168.50.15` | Dashboard, ingest, Prometheus, Grafana | 8000 |

## A. Do once on all five laptops

Do the downloads while temporarily online. Do not disconnect the internet
until every laptop has completed its Python bootstrap, Node Exporter install,
and any Docker/Ollama/K3s downloads needed for its role.

1. Install Ubuntu WSL2 from **Administrator PowerShell**:

   ```powershell
   wsl --install -d Ubuntu-24.04
   wsl --set-default-version 2
   Restart-Computer
   ```

2. Open Ubuntu once, make the Linux user, then run:

   ```bash
   sudo tee /etc/wsl.conf >/dev/null <<'EOF'
   [boot]
   systemd=true
   EOF
   exit
   ```

3. Back in PowerShell:

   ```powershell
   wsl --shutdown
   ```

4. Reopen Ubuntu and install the common tools:

   ```bash
   sudo apt update
   sudo apt install -y python3.12 python3.12-venv python3-pip curl jq unzip rsync ca-certificates build-essential kubernetes-client
   ```

5. Copy the revised zip to `C:\Panopticon` on every laptop, then in
   PowerShell:

   ```powershell
   New-Item -ItemType Directory -Force C:\Panopticon | Out-Null
   Expand-Archive C:\Panopticon\project-panopticon-five-laptop-fixed.zip -DestinationPath C:\Panopticon -Force
   ```

6. In Ubuntu on every laptop, copy the source into the fast Linux filesystem:

   ```bash
   sudo mkdir -p /opt/panopticon
   sudo rsync -a --delete /mnt/c/Panopticon/project-panopticon/ /opt/panopticon/
   sudo chown -R "$USER:$USER" /opt/panopticon
   cd /opt/panopticon
   ```

7. Cache Python dependencies and Node Exporter on all five laptops while
   internet is still available. First copy the matching role file from
   section C, then run:

   ```bash
   bash deployment/scripts/bootstrap-role.sh
   cd observability/node_exporter
   sudo ./install_node_exporter.sh
   ```

8. Before isolating the switch, also finish the role-specific downloads:

   - Laptop 01: Ollama and all three model pulls in its section below.
   - Laptop 04: Docker Desktop, K3s, and the first Arena build.
   - Laptop 05: Docker Desktop, then `cd /opt/panopticon/observability && docker compose pull`.

   Once these are complete, disconnect Wi-Fi and any LAN/WAN cables. Connect
   only the five wired Ethernet ports to the dedicated switch.

## B. Configure the closed wired network

On each laptop, first set the Windows computer name in elevated PowerShell,
then restart when prompted:

```powershell
# Run the one line matching this laptop
Rename-Computer -NewName llm-laptop -Restart
Rename-Computer -NewName red-laptop -Restart
Rename-Computer -NewName blue-laptop -Restart
Rename-Computer -NewName arena-laptop -Restart
Rename-Computer -NewName command-laptop -Restart
```

After its restart, use the included PowerShell script in an elevated window.
Replace `Ethernet` only if `Get-NetAdapter` shows a different wired name.

```powershell
cd C:\Panopticon\project-panopticon
# Run the one line matching this laptop
.\deployment\windows\Set-PanopticonNetwork.ps1 -Role llm -AdapterName Ethernet -DisableWiFi
.\deployment\windows\Set-PanopticonNetwork.ps1 -Role red -AdapterName Ethernet -DisableWiFi
.\deployment\windows\Set-PanopticonNetwork.ps1 -Role blue -AdapterName Ethernet -DisableWiFi
.\deployment\windows\Set-PanopticonNetwork.ps1 -Role arena -AdapterName Ethernet -DisableWiFi
.\deployment\windows\Set-PanopticonNetwork.ps1 -Role command -AdapterName Ethernet -DisableWiFi
```

On every Ubuntu instance, add these hostnames once:

```bash
sudo tee -a /etc/hosts >/dev/null <<'EOF'
192.168.50.11 llm-laptop
192.168.50.12 red-laptop
192.168.50.13 blue-laptop
192.168.50.14 arena-laptop
192.168.50.15 command-laptop
EOF
```

From each Windows laptop, all five `ping` commands must succeed before
starting services.

## C. Configure each laptop role

On the stated laptop, open Ubuntu and run the matching block. Do not copy a
different role's `.env` file.

### Laptop 01 — LLM

```bash
cd /opt/panopticon
cp deployment/env/llm.env .env
bash deployment/scripts/bootstrap-role.sh
```

Install Ollama and its models while internet is available:

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull hermes3:8b
ollama pull dolphin-llama3:8b
ollama pull qwen3:8b-q4_K_M
```

Start it in a dedicated Ubuntu terminal:

```bash
cd /opt/panopticon
bash deployment/scripts/start-role.sh
```

In elevated Windows PowerShell, publish it through Windows:

```powershell
cd C:\Panopticon\project-panopticon
.\deployment\windows\Publish-PanopticonPorts.ps1 -Role llm
```

### Laptop 04 — Arena first

Install Docker Desktop for Windows, open it once, enable the WSL2 engine and
Ubuntu integration. Then in Ubuntu install K3s:

```bash
curl -sfL https://get.k3s.io | sh -s - server --tls-san arena-laptop --tls-san 192.168.50.14
sudo systemctl enable --now k3s
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown "$USER:$USER" ~/.kube/config
sed -i 's/127.0.0.1/arena-laptop/g' ~/.kube/config
```

Configure and start the Arena:

```bash
cd /opt/panopticon
cp deployment/env/arena.env .env
bash deployment/scripts/bootstrap-role.sh
bash deployment/scripts/start-role.sh
```

Then in elevated Windows PowerShell:

```powershell
cd C:\Panopticon\project-panopticon
.\deployment\windows\Publish-PanopticonPorts.ps1 -Role arena
```

### Laptop 03 — Blue

First copy `~/.kube/config` from Laptop 04 to `C:\Panopticon\panopticon-blue.kubeconfig`
on Laptop 03 using an approved removable drive. On Laptop 04, create the
least-privilege config as described in `FIVE_LAPTOP_INSTALL.md`, section 8.

Then on Laptop 03 in Ubuntu:

```bash
cd /opt/panopticon
cp deployment/env/blue.env .env
mkdir -p ~/.kube
cp /mnt/c/Panopticon/panopticon-blue.kubeconfig ~/.kube/config
chmod 600 ~/.kube/config
bash deployment/scripts/bootstrap-role.sh
bash deployment/scripts/start-role.sh
```

Then in elevated Windows PowerShell:

```powershell
cd C:\Panopticon\project-panopticon
.\deployment\windows\Publish-PanopticonPorts.ps1 -Role blue
```

### Laptop 02 — Red

```bash
cd /opt/panopticon
cp deployment/env/red.env .env
bash deployment/scripts/bootstrap-role.sh
bash deployment/scripts/start-role.sh
```

Then in elevated Windows PowerShell:

```powershell
cd C:\Panopticon\project-panopticon
.\deployment\windows\Publish-PanopticonPorts.ps1 -Role red
```

### Laptop 05 — Command, dashboard, Prometheus, Grafana

Install Docker Desktop for Windows, enable the WSL2 engine and Ubuntu
integration. Then in Ubuntu:

```bash
cd /opt/panopticon
cp deployment/env/command.env .env
bash deployment/scripts/bootstrap-role.sh
bash deployment/scripts/start-role.sh
```

This single command starts Prometheus and Grafana in the background, starts
the dashboard on port 8000, and starts the Observer telemetry ingest service
on port 9600.

Then in elevated Windows PowerShell:

```powershell
cd C:\Panopticon\project-panopticon
.\deployment\windows\Publish-PanopticonPorts.ps1 -Role command
.\deployment\windows\Test-PanopticonFabric.ps1
```

If the test reports an Arena failure, go to Laptop 04, confirm
`kubectl -n panopticon-arena get pods` is healthy, run the Arena publish
script again, and repeat the Command test.

## D. Open the interfaces from Laptop 05

- Dashboard: `http://command-laptop:8000`
- Grafana: `http://command-laptop:3000` (`admin` / `panopticon`; change it)
- Prometheus targets: `http://command-laptop:9090/targets`

In Prometheus, every service should be **UP** except `referee-training`,
which is UP only while the trainer is running. The Arena target is scraped
at `arena-laptop:30080`; it is no longer scraped at the unreachable private
container port.

## E. Optional live bounded CPU/memory loop

Complete the standard five-laptop checks first. Then follow
`deployment/LIVE_RESOURCE_LOOP.md`. The ordinary dashboard remains safe and
simulation-first; the live option is separately armed on the target, Red,
Blue, and Command laptops and automatically expires after 15 seconds.
