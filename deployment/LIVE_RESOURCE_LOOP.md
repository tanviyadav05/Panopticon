# Live bounded CPU/memory demonstration

This optional feature is for the five-laptop switch-only lab. It converts
only Red's `cpu_pressure` and `memory_pressure` commands into a fixed,
token-protected workload inside the K3s `target-app` pod. It is not a network
flood, it does not take a user-supplied target, and it expires automatically.

The target permits one CPU worker, at most 48 MiB of held memory, and a
15-second duration. Kubernetes further constrains the Pod to 250m CPU and
256Mi memory.

## 1. Rebuild the target (Laptop 04)

The standard `start-role.sh` builds and deploys the updated image. After it
has finished, create a token only for this isolated lab and inject it as a
Kubernetes Secret:

```bash
export LAB_TOKEN="replace-with-a-long-random-value"
kubectl -n panopticon-arena create secret generic panopticon-lab-control \
  --from-literal=PANOPTICON_LAB_CONTROL_TOKEN="$LAB_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n panopticon-arena set env deployment/target-app PANOPTICON_LAB_WORKLOADS_ARMED=1
kubectl -n panopticon-arena rollout restart deployment/target-app
kubectl -n panopticon-arena rollout status deployment/target-app
```

## 2. Enable only the required integrations

On Laptop 02, add these three lines to its role `.env`, then restart Red:

```text
RED_LIVE_WORKLOADS_ARMED=1
PANOPTICON_LAB_TARGET_URL=http://arena-laptop:30080
PANOPTICON_LAB_CONTROL_TOKEN=<LAB_TOKEN>
```

On Laptop 03, add these three lines to its role `.env`, then restart Blue:

```text
BLUE_LIVE_WORKLOAD_RELIEF_ARMED=1
PANOPTICON_LAB_TARGET_URL=http://arena-laptop:30080
PANOPTICON_LAB_CONTROL_TOKEN=<LAB_TOKEN>
```

On Laptop 05, change only this line in its role `.env`, then restart the
dashboard:

```text
PANOPTICON_LIVE_CYCLE_ARMED=1
```

`PANOPTICON_LIVE_REFEREE_INGEST=1` is already enabled in the Command role;
the dashboard therefore receives actual Observer state on port 9600. Leave
`BLUE_LIVE_ACTIONS_ARMED=0`: this feature does not require pod isolation or
honeypot redirection.

## 3. Run and verify

On Laptop 05, open the dashboard, wait for **Live Observer: receiving**,
select the Go App, choose `cpu_pressure` or `memory_pressure`, check the
confirmation box, and press **Run selected CPU/memory cycle**.

The Command service starts the bounded Red workload, waits for a newer real
Observer sample, records and scores the incident, asks Blue to stop the
workload via `rate_limit`, waits for a recovery sample, and records/scores
the recovery. The target's `/metrics` also exposes live workload gauges.

## Stop / disarm

The workload expires after 15 seconds even if the network fails. To disarm
after the demo, change the three arm flags back to `0`, restart Red, Blue,
and Command, and on Laptop 04 run:

```bash
kubectl -n panopticon-arena set env deployment/target-app PANOPTICON_LAB_WORKLOADS_ARMED=0
```
