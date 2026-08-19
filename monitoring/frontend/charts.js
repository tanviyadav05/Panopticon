// A small, dependency-free line chart renderer. Draws one or more series
// on a canvas with auto-scaled Y axis and a light gridline. This is
// intentionally not a general-purpose charting library — it does exactly
// what this dashboard needs and nothing else.

function drawLineChart(canvas, series, options) {
  options = options || {};
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  const padding = { top: 10, right: 10, bottom: 20, left: 36 };
  const plotW = w - padding.left - padding.right;
  const plotH = h - padding.top - padding.bottom;

  ctx.clearRect(0, 0, w, h);

  const allValues = series.flatMap(s => s.values).filter(v => Number.isFinite(v));
  const yMin = options.yMin !== undefined ? options.yMin : Math.min(0, ...allValues);
  const yMax = options.yMax !== undefined ? options.yMax : Math.max(1, ...allValues);
  const yRange = (yMax - yMin) || 1;

  // gridlines
  ctx.strokeStyle = "#222C3D";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#8A94A6";
  ctx.font = "10px ui-monospace, monospace";
  const gridLines = 4;
  for (let i = 0; i <= gridLines; i++) {
    const y = padding.top + (plotH * i) / gridLines;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(w - padding.right, y);
    ctx.stroke();
    const value = yMax - (yRange * i) / gridLines;
    ctx.fillText(value.toFixed(2), 2, y + 3);
  }

  const n = Math.max(...series.map(s => s.values.length), 1);

  series.forEach(s => {
    if (s.values.length < 2) return;
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    s.values.forEach((v, i) => {
      const x = padding.left + (plotW * i) / (n - 1 || 1);
      const yNorm = (v - yMin) / yRange;
      const y = padding.top + plotH * (1 - yNorm);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });

  // legend
  let lx = padding.left;
  series.forEach(s => {
    ctx.fillStyle = s.color;
    ctx.fillRect(lx, h - 12, 8, 8);
    ctx.fillStyle = "#E9EDF4";
    ctx.fillText(s.label, lx + 12, h - 4);
    lx += 14 + s.label.length * 6 + 14;
  });
}
