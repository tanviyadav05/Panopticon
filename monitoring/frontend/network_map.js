/** network_map.js — Live SVG topology: 5 Panopticon laptops + switch + target devices. */
const NetworkMap = (function () {
  const NS = "http://www.w3.org/2000/svg";
  const W = 380, H = 340, SW = 190;
  const colors = { healthy:"#3ECF8E", degraded:"#E8B94B", critical:"#E0495C", offline:"#6B7686", attacking:"#E0495C", panopticon:"#3E84F0" };
  const PANOPTICON_NODES = [
    {id:"lp-01",label:"01 LLM",x:30,y:40},{id:"lp-02",label:"02 Red",x:30,y:100},
    {id:"lp-03",label:"03 Blue",x:30,y:160},{id:"lp-04",label:"04 Arena",x:30,y:220},
    {id:"lp-05",label:"05 Cmd",x:30,y:280},
  ];
  let _svg = null;

  function _makeNode(parent, x, y, label, color, small) {
    const r = small ? 7 : 9;
    const g = document.createElementNS(NS, "g");
    const c = document.createElementNS(NS, "circle");
    c.setAttribute("cx",x); c.setAttribute("cy",y); c.setAttribute("r",r);
    c.setAttribute("fill",color); c.setAttribute("stroke","rgba(255,255,255,0.15)"); c.setAttribute("stroke-width","1.5");
    c.style.transition = "fill .4s";
    g.appendChild(c);
    const t = document.createElementNS(NS, "text");
    t.setAttribute("x", x + (small?13:15)); t.setAttribute("y", y+4);
    t.setAttribute("fill","#8A94A6"); t.setAttribute("font-family","ui-monospace, monospace"); t.setAttribute("font-size","10");
    t.textContent = label; g.appendChild(t);
    parent.appendChild(g); return c;
  }
  function _makeLine(parent, x1,y1,x2,y2,dashed) {
    const l = document.createElementNS(NS, "line");
    l.setAttribute("x1",x1); l.setAttribute("y1",y1); l.setAttribute("x2",x2); l.setAttribute("y2",y2);
    l.setAttribute("stroke","#1E2C3E"); l.setAttribute("stroke-width","1.5");
    if (dashed) l.setAttribute("stroke-dasharray","4 3");
    parent.appendChild(l); return l;
  }
  function _makeSwitch(parent) {
    const g = document.createElementNS(NS, "g");
    const rx = document.createElementNS(NS, "rect");
    rx.setAttribute("x", SW-28); rx.setAttribute("y", H/2-24); rx.setAttribute("width",56); rx.setAttribute("height",48);
    rx.setAttribute("rx","6"); rx.setAttribute("fill","#151B25"); rx.setAttribute("stroke","#2A3C52"); rx.setAttribute("stroke-width","1.5");
    g.appendChild(rx);
    for (let i=0;i<4;i++) {
      const d = document.createElementNS(NS,"circle");
      d.setAttribute("cx", SW-14+i*10); d.setAttribute("cy", H/2+8); d.setAttribute("r",2.5); d.setAttribute("fill","#3E84F0");
      g.appendChild(d);
    }
    const lbl = document.createElementNS(NS,"text");
    lbl.setAttribute("x",SW); lbl.setAttribute("y",H/2-4); lbl.setAttribute("text-anchor","middle");
    lbl.setAttribute("fill","#8A94A6"); lbl.setAttribute("font-family","ui-monospace, monospace"); lbl.setAttribute("font-size","9"); lbl.setAttribute("letter-spacing","1");
    lbl.textContent = "SWITCH"; g.appendChild(lbl);
    parent.appendChild(g);
  }

  function init(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    _svg = document.createElementNS(NS, "svg");
    _svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    _svg.setAttribute("role","img"); _svg.setAttribute("aria-label","Panopticon network topology");
    container.appendChild(_svg);
    PANOPTICON_NODES.forEach(n => { _makeLine(_svg, n.x+9, n.y, SW-28, H/2, false); _makeNode(_svg, n.x, n.y, n.label, colors.panopticon, true); });
    _makeSwitch(_svg);
  }

  function updateTargets(targets) {
    if (!_svg) return;
    _svg.querySelectorAll("[data-target-node]").forEach(el => el.remove());
    const count = targets.length;
    const startY = Math.max(25, (H - (count*42)) / 2);

    targets.forEach((t, i) => {
      const y = startY + i*42, x = W-34, id = t.id;
      const health = t.health || 1.0, online = t.online, selected = t.selected;
      let color = online ? (health>0.7?colors.healthy:health>0.4?colors.degraded:colors.critical) : colors.offline;
      if (selected) color = colors.attacking;

      const line = _makeLine(_svg, SW+28, H/2, x-9, y, true);
      line.dataset.targetNode = id;
      line.setAttribute("stroke", selected ? "rgba(224,73,92,0.4)" : "#1E2C3E");

      const g = document.createElementNS(NS, "g");
      g.dataset.targetNode = id; g.style.cursor = "pointer";
      g.addEventListener("click", () => TargetPicker.select(id));

      const circle = document.createElementNS(NS, "circle");
      circle.setAttribute("cx",x); circle.setAttribute("cy",y); circle.setAttribute("r", selected?11:8);
      circle.setAttribute("fill",color); circle.setAttribute("stroke", selected?"rgba(224,73,92,0.6)":"rgba(255,255,255,0.1)");
      circle.setAttribute("stroke-width", selected?"2":"1.5"); circle.style.transition="all .4s";
      g.appendChild(circle);

      if (selected) {
        const pulse = document.createElementNS(NS, "circle");
        pulse.setAttribute("cx",x); pulse.setAttribute("cy",y); pulse.setAttribute("r",16);
        pulse.setAttribute("fill","none"); pulse.setAttribute("stroke","rgba(224,73,92,0.3)"); pulse.setAttribute("stroke-width","1.5");
        g.insertBefore(pulse, circle);
      }

      const shortName = t.name.length > 12 ? t.name.slice(0,10) + "…" : t.name;
      const text = document.createElementNS(NS, "text");
      text.setAttribute("x", x-16); text.setAttribute("y", y+4); text.setAttribute("text-anchor","end");
      text.setAttribute("fill", selected?"#E0495C":"#8A94A6");
      text.setAttribute("font-family","ui-monospace, monospace"); text.setAttribute("font-size","10");
      text.textContent = shortName; g.appendChild(text);

      _svg.appendChild(g);
    });
  }

  function setActive(deviceId) { /* handled via updateTargets on next tick */ }
  return { init, updateTargets, setActive };
})();
