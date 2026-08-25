from arena.targets.base_target import BaseTarget, ProbeResult
class GoAppTarget(BaseTarget):
    device_type="go_app"; label="Vulnerable Go App"; icon="server"; default_ports=[30080]
    def probe(self):
        # ICMP is commonly blocked by the Windows firewall even when the
        # NodePort is healthy. Treat the published TCP/HTTP endpoint as the
        # source of truth for this service, not ping alone.
        ping_ok, lat = self._ping()
        port_results = {p: self._tcp_connect(p,1.0) for p in self.default_ports}
        ports = {p: result[0] for p, result in port_results.items()}
        if not lat:
            lat = next((result[1] for result in port_results.values() if result[0]), 0.0)
        http = self._http_head(self.extra_config.get("probe_http_path","/health"),
                               port=self.extra_config.get("http_port",30080))
        reachable = ping_ok or any(ports.values()) or http is not None
        return ProbeResult(reachable, lat, ports, http, {"service":"go-http"})
