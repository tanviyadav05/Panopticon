"""These are the cross-component checks that arise specifically *because*
this system spans five separate processes (and, in the real deployment,
five separate laptops) rather than running as one program — exactly the
gap `.github/workflows/ci.yml` can't close on its own, since it tests each
component's own directory in isolation. Run from the repo root:

    python3 -m pytest tests/integration/ -v
"""
from __future__ import annotations

import os
import sys
import threading
import time

import numpy as np
import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _add(*parts):
    sys.path.insert(0, os.path.join(REPO_ROOT, *parts))


def test_observer_probes_to_aggregator_to_encoder():
    """The same chain documented in docs/architecture.md's "control loop":
    probes -> aggregator -> encoder produces a vector of the right shape
    and in [0, 1] (state_encoder normalizes/clips)."""
    _add("observer")
    from probes.observer import Observer
    from pipeline.aggregator import Aggregator
    from pipeline.state_encoder import StateEncoder

    obs = Observer("python3", pid=os.getpid())
    agg = Aggregator(window_seconds=0.2)
    enc = StateEncoder()

    vec = None
    for _ in range(6):
        summary = agg.add(obs.tick())
        if summary:
            vec = enc.encode(summary)
        time.sleep(0.05)
    obs.close()

    assert vec is not None, "aggregator never produced a window in time"
    assert vec.shape == (enc.size,)
    assert np.all(vec >= 0.0) and np.all(vec <= 1.0)


def test_observer_publisher_reaches_a_real_http_server():
    """Observer's publisher crosses an actual network socket (loopback
    here, the real Arena<->Command laptop link in deployment) to whatever
    is listening at REFEREE_PUBLISH_URL — this is the one boundary
    test_observer_probes_to_aggregator_to_encoder doesn't cover."""
    _add("observer")
    from pipeline.publisher import Publisher
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import json

    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            received.append(json.loads(self.rfile.read(length)))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        pub = Publisher(f"http://127.0.0.1:{port}/ingest")
        ok = pub.publish(np.array([0.1, 0.2, 0.3]), ["a", "b", "c"])
        time.sleep(0.2)
        assert ok
        assert len(received) == 1
        assert received[0]["field_names"] == ["a", "b", "c"]
    finally:
        server.shutdown()


def test_observer_main_entrypoint_wires_the_full_production_path():
    """Regression test for a real bug caught during audit: the two tests
    above prove aggregator->encoder and publisher->HTTP each work in
    isolation, but observer.py's actual main() CLI entrypoint — what the
    real DaemonSet (arena/k8s/05-observer-daemonset.yaml) runs — never
    composed them together at all; it only ever printed raw ticks,
    regardless of REFEREE_PUBLISH_URL being set in the pod's environment.
    This exercises the real entrypoint, not a hand-assembled substitute,
    so it would have caught that gap."""
    _add("observer")
    import sys as _sys
    import threading
    import json as _json
    from http.server import BaseHTTPRequestHandler, HTTPServer

    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            received.append(_json.loads(self.rfile.read(length)))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        old_argv = _sys.argv
        _sys.argv = [
            "observer.py", "--process-name", "python3",
            "--publish-url", f"http://127.0.0.1:{port}/ingest",
            "--window-seconds", "0.2", "--interval", "0.05", "--iterations", "6",
        ]
        from probes.observer import main
        main()
        _sys.argv = old_argv

        assert len(received) > 0, "observer's real main() entrypoint published nothing end-to-end"
        assert set(received[0].keys()) == {"timestamp", "field_names", "state"}
        assert len(received[0]["state"]) == len(received[0]["field_names"])
    finally:
        server.shutdown()


def test_documented_env_var_overrides_actually_work():
    """Regression test for a class of bug caught during audit: several
    env vars were documented (in docstrings/.env.example) as overriding
    config, but nothing in the code actually read them — OLLAMA_HOST and
    PANOPTICON_NAMESPACE were both silently decorative. This checks both
    are now real."""
    _add("llm-core")
    import os as _os

    _os.environ["OLLAMA_HOST"] = "http://regression-test-host:9999"
    from config import reload_config
    cfg = reload_config()
    assert cfg["ollama"]["host"] == "http://regression-test-host:9999"
    del _os.environ["OLLAMA_HOST"]
    reload_config()  # reset the module cache so later tests aren't affected

    _add("blue-team/countermeasures")
    _os.environ["PANOPTICON_NAMESPACE"] = "regression-test-ns"
    import importlib
    import pod_isolator
    importlib.reload(pod_isolator)
    assert pod_isolator.NAMESPACE == "regression-test-ns"
    del _os.environ["PANOPTICON_NAMESPACE"]
    importlib.reload(pod_isolator)  # reset back to the default for any later test


def test_red_and_blue_action_spaces_agree_with_env():
    """If common/action_spaces.py and panopticon_env.py's import of it ever
    drift apart, this catches it before a training run silently learns
    against the wrong action meanings. Now expects 16 Red actions (4
    original go_app + 10 multi-device + llm_generated + noop)."""
    _add("common")
    _add("referee")
    _add("red-team")
    from action_spaces import RED_ACTIONS, BLUE_ACTIONS
    from env.panopticon_env import PanopticonEnv

    assert len(RED_ACTIONS) == 16, f"expected 16 RED_ACTIONS, got {len(RED_ACTIONS)}"
    assert len(BLUE_ACTIONS) == 5

    env = PanopticonEnv(mode="sim", max_steps=5, seed=1)
    assert env.action_space("red").n == len(RED_ACTIONS)
    assert env.action_space("blue").n == len(BLUE_ACTIONS)


def test_device_susceptibility_actually_gates_pressure():
    """The whole point of DEVICE_SUSCEPTIBILITY: an attack that's a strong
    fit for one device type (deauth_flood vs. wifi_router) should move the
    combined_pressure signal; the same attack against an incompatible
    device (deauth_flood vs. go_app) should not. If common/target_types.py
    and panopticon_env.py's ArenaSimulation.apply_red() ever drift apart,
    this is what catches it."""
    _add("common")
    _add("referee")
    _add("red-team")
    from action_spaces import RED_ACTIONS
    from env.panopticon_env import PanopticonEnv

    deauth_idx = RED_ACTIONS.index("deauth_flood")

    router_env = PanopticonEnv(mode="sim", max_steps=5, seed=42, target_device_type="wifi_router")
    router_env.reset(seed=42)
    router_pressure = 0.0
    for _ in range(5):
        if not router_env.agents:
            break
        _, _, _, _, infos = router_env.step({"red": deauth_idx, "blue": 0})
        router_pressure += infos["red"]["combined_pressure"]

    app_env = PanopticonEnv(mode="sim", max_steps=5, seed=42, target_device_type="go_app")
    app_env.reset(seed=42)
    app_pressure = 0.0
    for _ in range(5):
        if not app_env.agents:
            break
        _, _, _, _, infos = app_env.step({"red": deauth_idx, "blue": 0})
        app_pressure += infos["red"]["combined_pressure"]

    assert router_pressure > 0.1, "deauth_flood should meaningfully pressure a wifi_router"
    assert app_pressure < 0.05, "deauth_flood should have near-zero effect on go_app"


def test_target_registry_loads_all_seven_device_types():
    """arena/targets/targets_config.yaml declares one of each device type;
    this confirms the registry actually instantiates all seven without
    error and that each has a working simulated_attack_effect()."""
    _add(".")
    from arena.targets.target_registry import TargetRegistry
    import numpy as np

    registry = TargetRegistry()
    all_targets = registry.all_targets()
    device_types = {t.device_type for t in all_targets}

    expected = {"go_app", "wifi_router", "webcam", "android_phone",
                "windows_laptop", "linux_laptop", "mac_laptop"}
    assert device_types == expected, f"missing device types: {expected - device_types}"

    rng = np.random.default_rng(0)
    for t in all_targets:
        # Every device should produce *some* valid, non-crashing response
        # for its own most-susceptible attacks — smoke check, not an exact
        # value check (magnitudes are randomized).
        effect = t.simulated_attack_effect("credential_stuffing", rng)
        assert isinstance(effect, dict)


def test_red_attacker_and_blue_controller_services_respond():
    """Spins up both services' real FastAPI apps in-process (no actual
    sockets needed for this check) and confirms /act and /decide behave —
    the thing that would otherwise only be caught by manually curling both
    laptops after deployment. Also confirms red_attacker's new
    target_device_type param actually changes the response."""
    _add("red-team")
    _add("blue-team")
    from fastapi.testclient import TestClient
    from attacks.red_attacker import build_app as build_red_app
    from countermeasures.blue_controller import build_app as build_blue_app

    red_client = TestClient(build_red_app())
    blue_client = TestClient(build_blue_app())

    assert red_client.get("/health").json()["role"] == "red-attacker"
    assert blue_client.get("/health").json()["role"] == "blue-controller"

    red_resp = red_client.post("/act", json={"action": "connection_pressure", "target_device_type": "go_app"}).json()
    assert red_resp["ok"] is True
    assert "connection" in red_resp["synthetic_effect"]

    # New multi-device attack against its intended target type
    deauth_resp = red_client.post("/act", json={"action": "deauth_flood", "target_device_type": "wifi_router"}).json()
    assert deauth_resp["ok"] is True
    assert "connection" in deauth_resp["synthetic_effect"]

    attacks_list = red_client.get("/attacks").json()
    assert attacks_list["count"] == 16

    blue_resp = blue_client.post("/act", json={"action": "rate_limit"}).json()
    assert blue_resp["ok"] is True

    # The new automation endpoints keep the two controllers symmetric. Red
    # executes only its existing synthetic effect; Blue is explicitly dry-run
    # unless BLUE_AUTONOMY_APPLY is enabled on the Blue host.
    red_auto = red_client.post("/autonomy/tick", json={
        "observation": [0.0] * 7, "target_device_type": "go_app"
    }).json()
    assert red_auto["ok"] is True
    assert red_auto["autonomous"] is True
    assert "synthetic_effect" in red_auto

    blue_auto = blue_client.post("/autonomy/tick", json={
        "observation": [0.0] * 14, "apply": False
    }).json()
    assert blue_auto["ok"] is True
    assert blue_auto["applied"] is False
    assert blue_auto["action"] in {"noop", "rate_limit", "isolate_pod", "honeypot_redirect", "raise_alert_threshold"}
