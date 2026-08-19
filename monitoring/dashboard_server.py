"""Command laptop (05) process:
    python3 dashboard_server.py                  # waits for real /telemetry POSTs
    PANOPTICON_DEMO=1 python3 dashboard_server.py # synthetic feed, cycles through targets
"""
from __future__ import annotations
import os, sys, threading, time
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)
from telemetry_api import router as telemetry_router, store, TelemetryEvent, _get_registry
from websocket_server import router as ws_router
from control_api import router as control_router, ensure_live_ingest

sys.path.insert(0, os.path.normpath(os.path.join(_THIS_DIR, "..", "common")))
from metrics import mount_metrics

RED_ACTIONS_LIST = ["noop","connection_pressure","cpu_pressure","memory_pressure",
                     "parsing_pressure","credential_stuffing","firmware_exploit",
                     "stream_hijack","adb_exploit","smb_relay","privilege_escalation",
                     "dns_poisoning","arp_spoof","deauth_flood","lateral_movement","llm_generated"]
BLUE_ACTIONS_LIST = ["noop","rate_limit","isolate_pod","honeypot_redirect","raise_alert_threshold"]


def _demo_feed():
    repo_root = os.path.dirname(_THIS_DIR)
    sys.path.insert(0, os.path.join(repo_root, "referee"))
    sys.path.insert(0, os.path.join(repo_root, "common"))
    sys.path.insert(0, os.path.join(repo_root, "red-team"))
    from env.panopticon_env import PanopticonEnv
    import numpy as np

    registry = _get_registry()
    rng = np.random.default_rng()
    step = 0
    device_ids = list(registry._targets.keys()) or ["go_app:target-app"]
    device_idx = 0

    env = PanopticonEnv(mode="sim", max_steps=100_000, seed=int(time.time()), target_device_type="go_app")
    obs, _ = env.reset()

    while True:
        if not env.agents:
            device_idx = (device_idx + 1) % len(device_ids)
            next_id = device_ids[device_idx]
            next_type = next_id.split(":")[0]
            registry.select(next_id)
            env = PanopticonEnv(mode="sim", max_steps=100_000, seed=int(time.time()), target_device_type=next_type)
            obs, _ = env.reset()

        actions = {"red": int(rng.integers(0, len(RED_ACTIONS_LIST))),
                   "blue": int(rng.integers(0, len(BLUE_ACTIONS_LIST)))}
        obs, rewards, terms, truncs, infos = env.step(actions)
        info = infos[next(iter(infos))]

        active = registry.active
        target_id   = active.to_dict()["id"] if active else "go_app:target-app"
        target_type = active.device_type if active else "go_app"
        target_name = active.name if active else "target-app"

        decoded = env.builder.encoder.decode(env.builder.encoder.encode(
            env._sim.to_raw_telemetry(info["combined_pressure"], info["service_health"])
        ))
        store.add(TelemetryEvent(
            step=step, combined_pressure=info["combined_pressure"], service_health=info["service_health"],
            detection_confidence=info.get("detection_confidence") or 0.0,
            red_action=RED_ACTIONS_LIST[actions["red"]], blue_action=BLUE_ACTIONS_LIST[actions["blue"]],
            red_reward=rewards["red"], blue_reward=rewards["blue"], decoded_fields=decoded,
            target_id=target_id, target_device_type=target_type, target_name=target_name,
        ))
        step += 1
        time.sleep(0.4)


def build_app() -> FastAPI:
    app = FastAPI(title="Panopticon Monitoring Dashboard")
    app.include_router(telemetry_router)
    app.include_router(ws_router)
    app.include_router(control_router)
    mount_metrics(app)   # must come before the catch-all StaticFiles "/" mount below

    frontend_dir = os.path.join(_THIS_DIR, "frontend")
    if os.path.isdir(frontend_dir):
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    try:
        _get_registry().start_poller()
    except Exception as e:
        print(f"[dashboard] target registry poller failed to start: {e}")

    if os.environ.get("PANOPTICON_DEMO") == "1":
        threading.Thread(target=_demo_feed, daemon=True).start()

    return app


app = build_app()

if __name__ == "__main__":
    if ensure_live_ingest():
        print("dashboard: Observer telemetry ingest enabled on :9600")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
