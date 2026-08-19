/** target_picker.js — Device cards for #target-grid + selection logic. */
const TargetPicker = (function () {
  const ICONS = {
    server: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="6" rx="2"/><rect x="2" y="10" width="20" height="6" rx="2"/><rect x="2" y="18" width="20" height="4" rx="2"/><circle cx="18" cy="5" r="1" fill="currentColor" stroke="none"/><circle cx="18" cy="13" r="1" fill="currentColor" stroke="none"/></svg>`,
    router: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="14" width="22" height="8" rx="2"/><path d="M5 14C5 9 8.5 5.5 12 4c3.5 1.5 7 5 7 10"/><path d="M8 14c0-3 1.8-5.5 4-6.5C14.2 8.5 16 11 16 14"/><circle cx="12" cy="18" r="1.5" fill="currentColor" stroke="none"/></svg>`,
    camera: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>`,
    phone: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="2" width="14" height="20" rx="2"/><line x1="5" y1="7" x2="19" y2="7"/><line x1="5" y1="17" x2="19" y2="17"/><circle cx="12" cy="20" r="0.5" fill="currentColor"/></svg>`,
    'laptop-windows': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M0 21h24"/><path d="M9 21h6"/><line x1="11" y1="8" x2="11" y2="13"/><line x1="8" y1="10.5" x2="14" y2="10.5"/></svg>`,
    'laptop-linux': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M0 21h24"/><path d="M9 21h6"/><path d="M8.5 8v5M8.5 8h3M8.5 10.5h2.5" stroke-linecap="round"/></svg>`,
    'laptop-mac': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M0 21h24"/><path d="M9 21h6"/><path d="M12 6c0 0 2-0.5 2.5 1.5C16 9 14.5 10 13 10.5L12.5 13M13 15h.01" stroke-linecap="round"/></svg>`,
  };
  const ICON_MAP = { go_app:"server", wifi_router:"router", webcam:"camera", android_phone:"phone", windows_laptop:"laptop-windows", linux_laptop:"laptop-linux", mac_laptop:"laptop-mac" };
  const TYPE_LABELS = { go_app:"Go App", wifi_router:"WiFi Router", webcam:"IP Webcam", android_phone:"Android Phone", windows_laptop:"Windows", linux_laptop:"Linux", mac_laptop:"macOS" };
  const ATTACK_SHORT = { connection_pressure:"conn", cpu_pressure:"cpu", memory_pressure:"mem", parsing_pressure:"parse", credential_stuffing:"cred", firmware_exploit:"fw", stream_hijack:"stream", adb_exploit:"adb", smb_relay:"smb", privilege_escalation:"privesc", dns_poisoning:"dns", arp_spoof:"arp", deauth_flood:"deauth", lateral_movement:"lateral", llm_generated:"llm" };

  let _currentTargets = [];
  let _selectedId = null;

  function _healthClass(h) { return h > 0.7 ? "" : (h > 0.4 ? "degraded" : "critical"); }

  function _buildCard(t) {
    const iconSvg = ICONS[ICON_MAP[t.device_type] || "server"] || ICONS.server;
    const typeLabel = TYPE_LABELS[t.device_type] || t.device_type;
    const healthPct = Math.round((t.health || 1.0) * 100);
    const online = t.online !== false;
    const selected = t.selected || (t.id === _selectedId);
    const validAttacks = (t.valid_attacks || []).filter(a => a !== "noop" && a !== "llm_generated").slice(0, 5);
    const attackTagsHtml = validAttacks.map(a => `<span class="attack-tag">${ATTACK_SHORT[a] || a}</span>`).join("");

    return `<div class="device-card${selected?' selected':''}${!online?' offline':''}"
     data-type="${t.device_type}" data-id="${t.id}"
     onclick="TargetPicker.select('${t.id}')" title="${t.name} @ ${t.ip}">
  <div class="device-card__head">
    <div class="device-card__icon">${iconSvg}</div>
    <div class="device-card__info">
      <div class="device-card__name">${t.name}</div>
      <div class="device-card__type">${typeLabel}</div>
      <div class="device-card__ip">${t.ip}</div>
    </div>
  </div>
  <div class="device-card__health-row">
    <div class="health-bar"><div class="health-bar__fill ${_healthClass(t.health||1)}" style="width:${healthPct}%"></div></div>
    <div class="device-card__health-pct">${healthPct}%</div>
  </div>
  <div class="device-card__foot">
    <span class="status-dot ${online?'online':'offline'}"></span>
    <span class="status-text">${online?'online':'offline'}</span>
  </div>
  <div class="attack-tags">${attackTagsHtml}</div>
</div>`;
  }

  function render(targets) {
    _currentTargets = targets;
    const grid = document.getElementById("target-grid");
    if (!grid) return;
    if (!targets || targets.length === 0) {
      grid.innerHTML = '<div class="target-grid__loading">No targets configured — edit arena/targets/targets_config.yaml</div>';
      return;
    }
    grid.innerHTML = targets.map(_buildCard).join("");
  }

  function select(deviceId) {
    if (_selectedId === deviceId) return;
    _selectedId = deviceId;
    document.querySelectorAll(".device-card").forEach(el => el.classList.toggle("selected", el.dataset.id === deviceId));
    const t = _currentTargets.find(t => t.id === deviceId);
    if (t) {
      const lbl = document.getElementById("active-target-label");
      if (lbl) lbl.textContent = `${t.name} (${TYPE_LABELS[t.device_type] || t.device_type})`;
    }
    NetworkMap.setActive(deviceId);
    fetch("/targets/select", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({device_id: deviceId}),
    }).catch(e => console.warn("select failed:", e));
  }

  function update(targets) {
    const serverSelected = targets.find(t => t.selected);
    if (serverSelected) _selectedId = serverSelected.id;
    render(targets);
    NetworkMap.updateTargets(targets);
    if (serverSelected) {
      const lbl = document.getElementById("active-target-label");
      if (lbl) lbl.textContent = `${serverSelected.name} (${TYPE_LABELS[serverSelected.device_type] || serverSelected.device_type})`;
    }
  }

  function init() {
    NetworkMap.init("network-map");
    fetch("/targets").then(r => r.json()).then(update).catch(() => {});
  }

  return { init, render, select, update };
})();
