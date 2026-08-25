from arena.targets.base_target import BaseTarget, ProbeResult
class WebcamTarget(BaseTarget):
    device_type="webcam"; label="IP Webcam"; icon="camera"; default_ports=[80,554,8080,8554]
    def probe(self):
        ok, lat = self._ping()
        ports = {p: self._tcp_connect(p,1.0)[0] for p in self.default_ports}
        http = self._http_head("/",port=self.extra_config.get("http_port",80)) if ok else None
        extra = {"rtsp_open": ports.get(self.extra_config.get("rtsp_port",554),False)} if ok else {}
        return ProbeResult(ok, lat, ports, http, extra)
