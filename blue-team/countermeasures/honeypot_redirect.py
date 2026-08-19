"""Reroutes traffic from the real target-app Service to the honeypot
Deployment (arena/k8s/03-honeypot.yaml) by patching the Service's selector
— real calls against the Kubernetes API. This is a blunt instrument (it
redirects *all* traffic, not just the suspicious slice) which is exactly
why blue_controller.py treats it as a fairly drastic action, not a default
response.
"""
from __future__ import annotations

import os
NAMESPACE = os.environ.get("PANOPTICON_NAMESPACE", "panopticon-arena")
SERVICE_NAME = "target-app"
REAL_SELECTOR = {"app": "target-app"}
HONEYPOT_SELECTOR = {"app": "honeypot"}


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
    return client.CoreV1Api(), client


class HoneypotRedirect:
    def __init__(self, namespace: str = NAMESPACE, service_name: str = SERVICE_NAME):
        self.namespace = namespace
        self.service_name = service_name
        self.core_api, self._client_module = _k8s_clients()
        self._active = False

    @property
    def available(self) -> bool:
        return self.core_api is not None

    @property
    def active(self) -> bool:
        return self._active

    def enable(self) -> dict:
        result = self._patch_selector(HONEYPOT_SELECTOR)
        if result["ok"]:
            self._active = True
        return result

    def disable(self) -> dict:
        result = self._patch_selector(REAL_SELECTOR)
        if result["ok"]:
            self._active = False
        return result

    def _patch_selector(self, selector: dict) -> dict:
        if not self.available:
            return {"ok": False, "reason": "kubernetes client/cluster unavailable"}
        try:
            patch = {"spec": {"selector": selector}}
            self.core_api.patch_namespaced_service(self.service_name, self.namespace, patch)
            return {"ok": True, "selector": selector}
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}
