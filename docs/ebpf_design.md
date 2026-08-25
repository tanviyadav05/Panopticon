# eBPF design

## Why eBPF instead of polling /proc

Polling `/proc/<pid>/*` (which `observer/probes/*.py` also do, as a
fallback) is cheap and portable but coarse — you see aggregate counters,
not individual events, and you pay a fixed polling-interval delay before
noticing anything. eBPF tracepoints let `syscall_probe.py` count syscalls
as they happen, with negligible overhead, directly from the kernel.

## Why it can't run on its own laptop

eBPF programs attach to *this machine's* kernel. They can't observe a
process running on a different machine. Since `target-app` runs inside the
Arena's Kubernetes cluster (laptop 04), the Observer — specifically
`syscall_probe.py`'s eBPF backend — has to run there too, deployed as a
DaemonSet (`arena/k8s/05-observer-daemonset.yaml`) so a copy runs on every
node in case the cluster ever grows past one node. This is the single most
important constraint on the whole 5-laptop layout; see
`deployment/laptop_roles.md`'s entry for laptop 04 and the callout in
`referee/env/panopticon_env.py`'s docstring.

## Backend selection

`observer/probes/syscall_probe.py` tries `from bcc import BPF` first. If
that import fails (no bcc installed — true for local dev, and true unless
you've specifically installed `bpfcc-tools`/`python3-bpfcc` on the Arena
laptop), it falls back to reading `voluntary_ctxt_switches` /
`nonvoluntary_ctxt_switches` from `/proc/<pid>/status` as a coarser proxy.
Both backends expose the same `sample()` shape, so nothing downstream
needs to know which one is active — see `observer/requirements.txt` for
install instructions for the real backend.

## The actual BPF program

```c
TRACEPOINT_PROBE(raw_syscalls, sys_enter) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    u64 zero = 0, *count;
    count = syscall_count.lookup_or_try_init(&pid, &zero);
    if (count) { (*count)++; }
    return 0;
}
```

This is purely observational — it counts events in a BPF hash map and
never writes to, blocks, or modifies anything the traced process does.
That's why it's safe to ship as-is: there's no "what could this be used
for" question the way there would be with a probe that could also act.
