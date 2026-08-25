from arena.targets.base_target import BaseTarget, ProbeResult
class WifiRouterTarget(BaseTarget):
    device_type="wifi_router"; label="WiFi Router"; icon="router"; default_ports=[22,23,80,443,53]
    def probe(self):
        ok, lat = self._ping()
        ports = {p: self._tcp_connect(p,1.0)[0] for p in [22,23,80,443]}
        http = (self._http_head("/",443,"https") or self._http_head("/",80)) if ok else None
        extra = {}
        if ok:
            snmp = self._snmp_sysdescr()
            if snmp: extra["snmp_sysdescr"] = snmp
        return ProbeResult(ok, lat, ports, http, extra)
    def _snmp_sysdescr(self):
        import subprocess, re
        community = self.extra_config.get("snmp_community","public")
        try:
            r = subprocess.run(["snmpget","-v1","-c",community,self.ip,"1.3.6.1.2.1.1.1.0"],
                               capture_output=True,text=True,timeout=2)
            m = re.search(r'STRING:\s*"?(.+?)"?\s*$', r.stdout, re.M)
            return m.group(1) if m else None
        except Exception: return None
