import socket
from arena.targets.base_target import BaseTarget, ProbeResult
class LinuxLaptopTarget(BaseTarget):
    device_type="linux_laptop"; label="Linux Laptop"; icon="laptop-linux"; default_ports=[22,80,8080,443]
    def probe(self):
        ok, lat = self._ping()
        ports = {p: False for p in self.default_ports}
        extra = {}
        if ok:
            for p in self.default_ports: ports[p] = self._tcp_connect(p,1.0)[0]
            if ports.get(22,False):
                try:
                    with socket.create_connection((self.ip,22),timeout=1.5*self._timeout_multiplier) as s:
                        extra["ssh_banner"] = s.recv(256).decode(errors="ignore").strip()
                except OSError: pass
        http = self._http_head("/",port=self.extra_config.get("http_port",80)) if ok else None
        return ProbeResult(ok, lat, ports, http, extra)
