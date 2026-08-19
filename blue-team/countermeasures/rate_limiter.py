"""A real token-bucket rate limiter. Two ways to use it:

* As a library, directly in front of anything you control (a reverse proxy,
  a sidecar) — TokenBucket.allow() is a genuine, working rate limiter, not
  a simulation of one.
* Via apply_to_arena(), which patches target-app's Kubernetes Service with
  an annotation an ingress controller would read (the exact annotation
  depends on which ingress controller you're running — see the comment
  inline) and/or tightens arena/k8s/04-network-policies.yaml's allowed
  ingress. That part needs a real cluster to do anything; the TokenBucket
  class itself doesn't.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict


class TokenBucket:
    def __init__(self, capacity: float = 20.0, refill_rate: float = 5.0):
        """capacity: max burst size. refill_rate: tokens added per second."""
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.monotonic()

    def allow(self, cost: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False


class PerKeyRateLimiter:
    """One TokenBucket per key (e.g. per source IP), so one noisy client
    doesn't exhaust everyone else's budget. Idle keys are cleaned up
    periodically so this doesn't leak memory under a real connection flood
    from many distinct sources."""

    def __init__(self, capacity: float = 20.0, refill_rate: float = 5.0, max_idle_seconds: float = 300.0):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.max_idle_seconds = max_idle_seconds
        self._buckets: dict[str, TokenBucket] = {}
        self._last_seen: dict[str, float] = {}

    def allow(self, key: str, cost: float = 1.0) -> bool:
        bucket = self._buckets.setdefault(key, TokenBucket(self.capacity, self.refill_rate))
        self._last_seen[key] = time.monotonic()
        return bucket.allow(cost)

    def sweep_idle(self):
        now = time.monotonic()
        stale = [k for k, last in self._last_seen.items() if now - last > self.max_idle_seconds]
        for k in stale:
            self._buckets.pop(k, None)
            self._last_seen.pop(k, None)
        return len(stale)

    def tighten(self, factor: float = 0.5):
        """Used when Blue decides things are bad enough to clamp down
        globally — scales every existing bucket's capacity and refill rate
        down by `factor`, and applies the same tighter limits to new keys."""
        self.capacity *= factor
        self.refill_rate *= factor
        for bucket in self._buckets.values():
            bucket.capacity = self.capacity
            bucket.refill_rate = self.refill_rate
            bucket.tokens = min(bucket.tokens, self.capacity)


def apply_to_arena(namespace: str | None = None, service_name: str = "target-app", requests_per_second: int = 50):
    """Tightens rate limiting at the cluster level by patching an
    ingress-controller-recognized annotation on the Service. The exact
    annotation key is controller-specific — this targets the common
    nginx-ingress convention; swap it for your controller's equivalent.
    Returns False (instead of raising) if the kubernetes client or cluster
    isn't available, so callers can degrade gracefully.
    """
    if namespace is None:
        namespace = os.environ.get("PANOPTICON_NAMESPACE", "panopticon-arena")

    try:
        from kubernetes import client, config
    except ImportError:
        return False

    try:
        config.load_incluster_config()
    except Exception:
        try:
            config.load_kube_config()
        except Exception:
            return False

    v1 = client.CoreV1Api()
    try:
        svc = v1.read_namespaced_service(service_name, namespace)
        annotations = svc.metadata.annotations or {}
        annotations["nginx.ingress.kubernetes.io/limit-rps"] = str(requests_per_second)
        svc.metadata.annotations = annotations
        v1.patch_namespaced_service(service_name, namespace, svc)
        return True
    except Exception:
        return False
