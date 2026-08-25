"""Docker-based code execution sandbox for the Coder agent.

Requires a running Docker daemon. When unavailable, `run_python()` returns
a clear error rather than silently falling back to running the code as a
bare subprocess on the host — a subprocess isn't a sandbox, and pretending
otherwise would be actively misleading given that Coder-generated code is,
by construction, not something you should trust unreviewed. `available`
lets callers (coder.py's node function) check ahead of time and skip
execution cleanly instead of hitting this error path on every call.

Containment, when Docker is available:
  - `network_disabled=True` — no network access from inside the container
  - `mem_limit` — hard memory cap
  - a wall-clock timeout on `container.wait()`
  - the container is always removed after (success, failure, or timeout)
"""
from __future__ import annotations

import logging
import uuid

logger = logging.getLogger("llm_core.tools.code_sandbox")


class CodeSandbox:
    def __init__(self, image: str = "python:3.12-slim", timeout_s: float = 15.0,
                mem_limit: str = "256m", network_disabled: bool = True):
        self.image = image
        self.timeout_s = timeout_s
        self.mem_limit = mem_limit
        self.network_disabled = network_disabled
        self._client = None
        self._available = False

        try:
            import docker
            client = docker.from_env()
            client.ping()
            self._client = client
            self._available = True
        except Exception as exc:
            logger.info("Docker daemon unavailable (%s) — code_sandbox will report unavailable rather than falling back to an unsandboxed subprocess", exc)

    @property
    def available(self) -> bool:
        return self._available

    def run_python(self, code: str) -> dict:
        if not self._available:
            return {"ok": False, "error": "Docker daemon unavailable — code_sandbox requires Docker for real containment; see module docstring for why there's no unsandboxed fallback"}

        container_name = f"panopticon-sandbox-{uuid.uuid4().hex[:12]}"
        try:
            container = self._client.containers.run(
                self.image,
                ["python3", "-c", code],
                name=container_name,
                network_disabled=self.network_disabled,
                mem_limit=self.mem_limit,
                detach=True,
                stdout=True,
                stderr=True,
            )
        except Exception as exc:
            return {"ok": False, "error": f"failed to start sandbox container: {exc}"}

        try:
            result = container.wait(timeout=self.timeout_s)
            logs = container.logs().decode(errors="ignore")
            exit_code = result.get("StatusCode", -1)
            return {"ok": exit_code == 0, "output": logs, "exit_code": exit_code}
        except Exception as exc:
            return {"ok": False, "error": f"sandbox execution failed or timed out: {exc}"}
        finally:
            try:
                container.remove(force=True)
            except Exception:
                pass   # container may already be gone; not worth failing the call over

    def ensure_image_pulled(self) -> bool:
        """Pulls self.image if it isn't already present locally. Called
        lazily rather than at __init__ time, since pulling requires
        network access to Docker Hub that isn't always available (or
        wanted) at startup."""
        if not self._available:
            return False
        try:
            self._client.images.get(self.image)
            return True
        except Exception:
            try:
                self._client.images.pull(self.image)
                return True
            except Exception as exc:
                logger.warning("could not pull sandbox image %s: %s", self.image, exc)
                return False
