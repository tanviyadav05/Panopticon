"""Cordons/quarantines a pod by applying a deny-all NetworkPolicy scoped to
its labels — real calls against the Kubernetes API, not a simulation.
Degrades to a no-op (returning ok=False) if no cluster is reachable, e.g.
when running unit tests or developing away from the Arena laptop.
"""
from __future__ import annotations

import os
NAMESPACE = os.environ.get("PANOPTICON_NAMESPACE", "panopticon-arena")
QUARANTINE_PREFIX = "panopticon-quarantine-"


def _k8s_clients():
    try:
        from kubernetes import client, config
    except ImportError:
        return None, None
    try:
        config.load_incluster_config()
    except Exception:
        try:
            config.load_kube_config()
        except Exception:
            return None, None
    return client.NetworkingV1Api(), client


class PodIsolator:
    def __init__(self, namespace: str = NAMESPACE):
        self.namespace = namespace
        self.net_api, self._client_module = _k8s_clients()

    @property
    def available(self) -> bool:
        return self.net_api is not None

    def isolate(self, label_selector: dict, name_suffix: str) -> dict:
        """label_selector e.g. {"app": "target-app"}. Applies a NetworkPolicy
        that selects pods matching those labels and permits no ingress at
        all — a hard quarantine. Returns {"ok": bool, ...}."""
        if not self.available:
            return {"ok": False, "reason": "kubernetes client/cluster unavailable"}

        client = self._client_module
        policy_name = f"{QUARANTINE_PREFIX}{name_suffix}"
        policy = client.V1NetworkPolicy(
            metadata=client.V1ObjectMeta(name=policy_name, namespace=self.namespace),
            spec=client.V1NetworkPolicySpec(
                pod_selector=client.V1LabelSelector(match_labels=label_selector),
                policy_types=["Ingress", "Egress"],
                ingress=[],  # deny all ingress
                egress=[],   # deny all egress too — fully quarantined
            ),
        )
        try:
            self.net_api.create_namespaced_network_policy(self.namespace, policy)
            return {"ok": True, "policy_name": policy_name, "action": "isolated"}
        except Exception as exc:
            # Most common real-world case: the quarantine policy already
            # exists from a previous isolate() call. Treat that as success.
            if "AlreadyExists" in str(exc):
                return {"ok": True, "policy_name": policy_name, "action": "already_isolated"}
            return {"ok": False, "reason": str(exc)}

    def release(self, name_suffix: str) -> dict:
        if not self.available:
            return {"ok": False, "reason": "kubernetes client/cluster unavailable"}
        policy_name = f"{QUARANTINE_PREFIX}{name_suffix}"
        try:
            self.net_api.delete_namespaced_network_policy(policy_name, self.namespace)
            return {"ok": True, "policy_name": policy_name, "action": "released"}
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}
