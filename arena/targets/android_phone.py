from arena.targets.base_target import BaseTarget, ProbeResult
class AndroidPhoneTarget(BaseTarget):
    device_type="android_phone"; label="Android Phone"; icon="phone"; default_ports=[5555,8080]
    def probe(self):
        ok, lat = self._ping()
        adb_port = self.extra_config.get("adb_port",5555)
        adb_open = False; adb_lat = 0.0
        if ok: adb_open, adb_lat = self._tcp_connect(adb_port,1.0)
        extra = {"adb_tcp_open": adb_open, "adb_latency_ms": round(adb_lat,2)} if ok else {}
        return ProbeResult(ok, lat, {adb_port: adb_open}, None, extra)
