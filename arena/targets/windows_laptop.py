import socket
from arena.targets.base_target import BaseTarget, ProbeResult
class WindowsLaptopTarget(BaseTarget):
    device_type="windows_laptop"; label="Windows Laptop"; icon="laptop-windows"; default_ports=[445,3389,5985,22,80]
    def probe(self):
        ok, lat = self._ping()
        ports = {p: False for p in self.default_ports}
        extra = {}
        if ok:
            for p in self.default_ports:
                ports[p] = self._tcp_connect(p,1.0)[0]
            extra = {"smb_open": ports.get(445,False), "rdp_open": ports.get(3389,False)}
            if ports.get(22,False):
                try:
                    with socket.create_connection((self.ip,22),timeout=1.5*self._timeout_multiplier) as s:
                        extra["ssh_banner"] = s.recv(256).decode(errors="ignore").strip()
                except OSError: pass
        return ProbeResult(ok, lat, ports, None, extra)
