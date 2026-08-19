/** dashboard.js — WS wiring for telemetry charts, stat cards, timeline. Delegates target UI to TargetPicker + NetworkMap. */
(function () {
  const MAX_POINTS = 120;
  const buffer = [];

  const els = {
    status: document.getElementById("conn-status"),
    health: document.getElementById("stat-health"),
    pressure: document.getElementById("stat-pressure"),
    detection: document.getElementById("stat-detection"),
    step: document.getElementById("stat-step"),
    redAction: document.getElementById("stat-red-action"),
    blueAction: document.getElementById("stat-blue-action"),
    chartMain: document.getElementById("chart-main"),
    chartNet: document.getElementById("chart-network"),
    timeline: document.getElementById("timeline"),
    chartTitle: document.getElementById("chart-main-title"),
  };

  function setStatus(state, text) {
    if (!els.status) return;
    els.status.className = "conn-status conn-status--" + state;
    els.status.textContent = text;
  }

  function updateStats(latest) {
    if (!latest) return;
    const set = (el, v) => { if (el) el.textContent = v; };
    set(els.health, (latest.service_health*100).toFixed(0)+"%");
    set(els.pressure, (latest.combined_pressure*100).toFixed(0)+"%");
    set(els.detection, ((latest.detection_confidence||0)*100).toFixed(0)+"%");
    set(els.step, latest.step);
    set(els.redAction, latest.red_action||"—");
    set(els.blueAction, latest.blue_action||"—");
    if (els.chartTitle && latest.target_name) els.chartTitle.textContent = `Health & Pressure — ${latest.target_name}`;
  }

  function renderCharts() {
    if (!buffer.length) return;
    drawLineChart(els.chartMain, [
      {label:"health", color:"#36C7C0", values: buffer.map(e=>e.service_health)},
      {label:"pressure", color:"#E0495C", values: buffer.map(e=>e.combined_pressure)},
      {label:"detection", color:"#E8B94B", values: buffer.map(e=>e.detection_confidence||0)},
    ], {yMin:0, yMax:1});
    drawLineChart(els.chartNet, [
      {label:"total connections", color:"#3E84F0", values: buffer.map(e=>(e.decoded_fields||{})["network.total_connections"]||0)},
      {label:"close_wait", color:"#E0495C", values: buffer.map(e=>(e.decoded_fields||{})["network.close_wait"]||0)},
    ]);
  }

  function renderTimeline() {
    const rows = buffer.slice(-30).reverse().map(e => {
      const t = new Date((e.timestamp||0)*1000).toLocaleTimeString();
      const h = e.service_health||0;
      const hStyle = h>0.7 ? "" : (h>0.4 ? "style='color:var(--c-orient)'" : "style='color:var(--c-red)'");
      return `<div class="timeline__row">
        <span class="t-time">${t}</span>
        <span class="t-target">${e.target_name||"—"}</span>
        <span class="t-red">${e.red_action||"—"}</span>
        <span class="t-blue">${e.blue_action||"—"}</span>
        <span class="t-num">${((e.combined_pressure||0)*100).toFixed(0)}%</span>
        <span class="t-health" ${hStyle}>${((e.service_health||0)*100).toFixed(0)}%</span>
      </div>`;
    });
    if (els.timeline) els.timeline.innerHTML = rows.join("");
  }

  function pushEvents(events) {
    events.forEach(e => { buffer.push(e); if (buffer.length > MAX_POINTS) buffer.shift(); });
    updateStats(buffer[buffer.length-1]);
    renderCharts();
    renderTimeline();
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/live`);
    ws.onopen = () => setStatus("open", "live");
    ws.onclose = () => { setStatus("closed", "disconnected — retrying…"); setTimeout(connect, 2000); };
    ws.onerror = () => ws.close();
    ws.onmessage = (msg) => {
      const payload = JSON.parse(msg.data);
      if (payload.type === "backlog" || payload.type === "update") pushEvents(payload.events);
      else if (payload.type === "targets_update") TargetPicker.update(payload.targets);
    };
  }

  setStatus("connecting", "connecting…");
  TargetPicker.init();
  ControlPanel.init();
  connect();
})();
