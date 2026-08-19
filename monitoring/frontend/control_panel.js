/** Safe command-console controls.  State-changing calls carry an optional
 * session-only token and the server independently validates every action. */
const ControlPanel = (function () {
  const els = {
    token: document.getElementById("control-token"), result: document.getElementById("control-result"),
    services: document.getElementById("service-row"), red: document.getElementById("red-action"),
    blue: document.getElementById("blue-action"), blueConfirm: document.getElementById("blue-confirm"),
    redAct: document.getElementById("red-act"), blueAct: document.getElementById("blue-act"),
    reset: document.getElementById("referee-reset"), step: document.getElementById("referee-step"),
    policy: document.getElementById("referee-policy"), llm: document.getElementById("llm-analysis"),
    liveConfirm: document.getElementById("live-confirm"), liveCycle: document.getElementById("live-cycle"),
  };
  let status = null;

  function authHeaders() {
    const headers = {"Content-Type": "application/json"};
    if (els.token && els.token.value) headers["X-Panopticon-Token"] = els.token.value;
    return headers;
  }

  function setResult(value, isError) {
    if (!els.result) return;
    const summary = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    els.result.classList.toggle("control-result--error", Boolean(isError));
    els.result.textContent = summary;
  }

  async function request(path, body) {
    const response = await fetch(path, {method: "POST", headers: authHeaders(), body: JSON.stringify(body || {})});
    const data = await response.json().catch(() => ({detail: "The service returned a non-JSON response."}));
    if (!response.ok) throw new Error(data.detail || data.error || `Request failed (${response.status})`);
    return data;
  }

  function populate(select, actions) {
    if (!select || select.options.length) return;
    select.innerHTML = actions.map(action => `<option value="${action}">${action}</option>`).join("");
  }

  function service(name, payload) {
    const ok = payload && payload.status === "ok";
    const suffix = ok ? (payload.backend ? ` (${payload.backend})` : " online") : " offline";
    return `<span class="service-pill ${ok ? "service-pill--ok" : "service-pill--bad"}">${name}: ${suffix}</span>`;
  }

  async function refresh() {
    try {
      status = await fetch("/control/status").then(r => r.json());
      populate(els.red, status.actions.red); populate(els.blue, status.actions.blue);
      if (els.services) {
        els.services.innerHTML = [
          service("Arena", status.services.arena), service("Red", status.services.red), service("Blue", status.services.blue), service("Local LLM", status.services.llm),
          `<span class="service-pill service-pill--ok">Referee: ${status.referee.ready ? `sim step ${status.referee.step}` : "idle"}</span>`,
          status.live_referee && status.live_referee.observing ? '<span class="service-pill service-pill--ok">Live Observer: receiving</span>' : '<span class="service-pill service-pill--warn">Live Observer: not receiving</span>',
          status.services.blue.live_actions_armed ? '<span class="service-pill service-pill--warn">Blue laptop armed</span>' : '',
          status.blue_live_armed ? '<span class="service-pill service-pill--warn">Command live control armed</span>' : ''
        ].join("");
      }
    } catch (error) { setResult(`Cannot reach the command API: ${error.message}`, true); }
  }

  function bind(button, callback) {
    if (!button) return;
    button.addEventListener("click", async () => {
      button.disabled = true;
      try { setResult(await callback()); await refresh(); }
      catch (error) { setResult(error.message, true); }
      finally { button.disabled = false; }
    });
  }

  function init() {
    bind(els.redAct, () => request("/control/red/act", {action: els.red.value}));
    bind(els.blueAct, () => request("/control/blue/act", {action: els.blue.value, confirm_live: Boolean(els.blueConfirm.checked)}));
    bind(els.reset, () => request("/control/referee/reset"));
    bind(els.step, () => request("/control/referee/step", {red_action: els.red.value, blue_action: els.blue.value}));
    bind(els.policy, () => request("/control/referee/policy-step"));
    bind(els.llm, () => request("/control/referee/local-llm-analysis", {max_iterations: 2}));
    bind(els.liveCycle, () => request("/control/live/cycle", {red_action: els.red.value, confirm_live: Boolean(els.liveConfirm.checked)}));
    refresh();
    setInterval(refresh, 5000);
  }
  return {init, refresh};
})();
