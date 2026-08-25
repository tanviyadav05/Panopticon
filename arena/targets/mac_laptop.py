import socket, struct
from arena.targets.base_target import BaseTarget, ProbeResult
class MacLaptopTarget(BaseTarget):
    device_type="mac_laptop"; label="macOS Laptop"; icon="laptop-mac"; default_ports=[22,548,80,443]
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
            extra["afp_open"] = ports.get(548,False)
            extra["mdns_reachable"] = self._mdns_ping()
        return ProbeResult(ok, lat, ports, None, extra)
    def _mdns_ping(self):
        try:
            hdr = struct.pack(">HHHHHH",0,0,1,0,0,0)
            msg = hdr + b"\x09_services\x07_dns-sd\x04_udp\x05local\x00" + struct.pack(">HH",12,1)
            s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            s.settimeout(1.0*self._timeout_multiplier); s.sendto(msg,(self.ip,5353)); s.recv(512); s.close(); return True
        except OSError: return False
