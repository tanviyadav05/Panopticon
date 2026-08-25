"""Central registry of all Arena target devices — background poller + selection authority."""
from __future__ import annotations
import logging, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
import yaml

logger = logging.getLogger("arena.target_registry")
_DEVICE_CLASSES: dict = {}
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "targets_config.yaml")


def _import_device_classes():
    global _DEVICE_CLASSES
    if _DEVICE_CLASSES: return
    _repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, _repo)
    from arena.targets.go_app_target    import GoAppTarget
    from arena.targets.wifi_router      import WifiRouterTarget
    from arena.targets.webcam           import WebcamTarget
    from arena.targets.android_phone    import AndroidPhoneTarget
    from arena.targets.windows_laptop   import WindowsLaptopTarget
    from arena.targets.linux_laptop     import LinuxLaptopTarget
    from arena.targets.mac_laptop       import MacLaptopTarget
    _DEVICE_CLASSES.update({"go_app": GoAppTarget, "wifi_router": WifiRouterTarget,
        "webcam": WebcamTarget, "android_phone": AndroidPhoneTarget,
        "windows_laptop": WindowsLaptopTarget, "linux_laptop": LinuxLaptopTarget,
        "mac_laptop": MacLaptopTarget})


class TargetRegistry:
    def __init__(self, config_path: str = _CONFIG_PATH):
        self._lock = threading.Lock()
        self._targets: dict = {}
        self._active_id: Optional[str] = None
        self._probe_interval: float = 10.0
        self._poller: Optional[threading.Thread] = None
        self._load_config(config_path)

    def _load_config(self, path: str):
        _import_device_classes()
        if not os.path.exists(path):
            logger.warning("targets_config.yaml not found at %s", path); return
        with open(path) as fh: cfg = yaml.safe_load(fh)
        self._probe_interval = cfg.get("probe", {}).get("interval_seconds", 10.0)
        for entry in cfg.get("targets", []):
            if not entry.get("enabled", True): continue
            dtype = entry["device_type"]; name = entry["name"]; ip = entry["ip"]
            kwargs = {k: v for k, v in entry.items() if k not in ("name","device_type","ip","enabled")}
            cls = _DEVICE_CLASSES.get(dtype)
            if not cls: logger.warning("unknown device_type '%s', skipping", dtype); continue
            target = cls(name=name, ip=ip, **kwargs)
            tid = f"{dtype}:{name}"
            self._targets[tid] = target
            logger.info("registered target %s @ %s", tid, ip)
        if self._targets and not self._active_id:
            first_id = next(iter(self._targets))
            self._active_id = first_id
            self._targets[first_id].selected = True

    def all_targets(self): 
        with self._lock: return list(self._targets.values())
    def get(self, device_id):
        with self._lock: return self._targets.get(device_id)
    @property
    def active(self):
        with self._lock: return self._targets.get(self._active_id)
    @property
    def active_id(self):
        with self._lock: return self._active_id

    def select(self, device_id: str) -> bool:
        with self._lock:
            if device_id not in self._targets: return False
            if self._active_id and self._active_id in self._targets:
                self._targets[self._active_id].selected = False
            self._active_id = device_id
            self._targets[device_id].selected = True
            logger.info("active target -> %s", device_id)
            return True

    def probe_all(self):
        with ThreadPoolExecutor(max_workers=min(8, len(self._targets) or 1)) as pool:
            futures = {pool.submit(t.update_health): tid for tid, t in list(self._targets.items())}
            for f in futures:
                try: f.result(timeout=5)
                except Exception as exc: logger.debug("probe error %s: %s", futures[f], exc)

    def probe_one(self, device_id: str):
        with self._lock: target = self._targets.get(device_id)
        if not target: return None
        health = target.update_health()
        return {"health": health, "probe": target.last_probe.to_dict() if target.last_probe else None}

    def as_list(self):
        with self._lock: return [t.to_dict() for t in self._targets.values()]

    def start_poller(self):
        if self._poller and self._poller.is_alive(): return
        self._poller = threading.Thread(target=self._poll_loop, daemon=True, name="target-registry-poller")
        self._poller.start()

    def _poll_loop(self):
        self.probe_all()
        while True:
            time.sleep(self._probe_interval)
            self.probe_all()


registry = TargetRegistry()
