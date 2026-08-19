"""Syscall-level telemetry for the process Observer is watching.

Two backends:

* **eBPF (preferred, Linux + bcc installed)** — attaches to the
  `raw_syscalls:sys_enter` tracepoint and counts syscalls issued by the
  target PID. This is real kernel-level tracing, not a simulation — it's
  also purely observational (it counts events, it never modifies anything),
  so there's nothing sensitive about shipping it.
* **/proc fallback (anywhere else)** — reads voluntary/involuntary context
  switch counters from /proc/<pid>/status. It's a coarser proxy for "how
  much is this process interacting with the kernel," but it needs no
  special privileges or kernel headers, which matters for local dev and for
  this very repository's own test suite.

Either way, sample() returns the same shape, so nothing downstream needs to
know which backend is active.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

try:
    from bcc import BPF  # type: ignore

    _BCC_AVAILABLE = True
except Exception:  # pragma: no cover - depends on host kernel/tooling
    _BCC_AVAILABLE = False


_BPF_PROGRAM = r"""
#include <uapi/linux/ptrace.h>

BPF_HASH(syscall_count, u32, u64);

TRACEPOINT_PROBE(raw_syscalls, sys_enter) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    u64 zero = 0, *count;
    count = syscall_count.lookup_or_try_init(&pid, &zero);
    if (count) {
        (*count)++;
    }
    return 0;
}
"""


@dataclass
class SyscallSample:
    pid: int
    backend: str
    syscalls_per_interval: int
    voluntary_ctxt_switches: Optional[int] = None
    nonvoluntary_ctxt_switches: Optional[int] = None
    timestamp: float = field(default_factory=time.time)


class SyscallProbe:
    """Tracks syscall-ish activity for a single PID across successive calls
    to sample(); each call returns the delta since the previous one."""

    def __init__(self, pid: int):
        self.pid = pid
        self.backend = "ebpf" if _BCC_AVAILABLE else "procfs"
        self._bpf = BPF(text=_BPF_PROGRAM) if _BCC_AVAILABLE else None
        self._last_total = 0
        self._last_vctx = 0
        self._last_nvctx = 0

    def sample(self) -> SyscallSample:
        if self.backend == "ebpf":
            return self._sample_ebpf()
        return self._sample_procfs()

    def _sample_ebpf(self) -> SyscallSample:
        table = self._bpf["syscall_count"]
        total = 0
        for k, v in table.items():
            if k.value == self.pid:
                total = v.value
                break
        delta = max(0, total - self._last_total)
        self._last_total = total
        return SyscallSample(pid=self.pid, backend="ebpf", syscalls_per_interval=delta)

    def _sample_procfs(self) -> SyscallSample:
        vctx, nvctx = self._read_proc_status()
        dv = max(0, vctx - self._last_vctx)
        dn = max(0, nvctx - self._last_nvctx)
        self._last_vctx, self._last_nvctx = vctx, nvctx
        return SyscallSample(
            pid=self.pid,
            backend="procfs",
            syscalls_per_interval=dv + dn,  # coarse proxy; see module docstring
            voluntary_ctxt_switches=vctx,
            nonvoluntary_ctxt_switches=nvctx,
        )

    def _read_proc_status(self) -> tuple[int, int]:
        vctx, nvctx = 0, 0
        try:
            with open(f"/proc/{self.pid}/status", "r") as fh:
                for line in fh:
                    if line.startswith("voluntary_ctxt_switches:"):
                        vctx = int(line.split(":")[1].strip())
                    elif line.startswith("nonvoluntary_ctxt_switches:"):
                        nvctx = int(line.split(":")[1].strip())
        except FileNotFoundError:
            pass  # process exited between probes; process_probe.py owns noticing this
        return vctx, nvctx

    def close(self):
        if self._bpf is not None:
            try:
                self._bpf.cleanup()
            except Exception:
                pass
