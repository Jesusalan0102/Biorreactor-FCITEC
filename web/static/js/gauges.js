/**
 * Dibuja un gauge tipo velocímetro (semicírculo) en un <canvas>.
 * Réplica del dibujar_gauge() de monitoreoV2.py (matplotlib) pero en Canvas2D.
 *
 * zones: [[zmin, zmax, colorCSS], ...]
 */
function drawGauge(canvasId, value, min, max, zones, title, valueText) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const cx = w / 2;
  const cy = h * 0.75;
  const radius = Math.min(w / 2, h * 0.95) - 22;
  const lineWidth = 16;

  function valToAngle(v) {
    const c = Math.max(min, Math.min(max, v));
    const frac = max > min ? (c - min) / (max - min) : 0;
    return Math.PI + frac * Math.PI; // PI (izq) -> 2*PI (der), pasando por arriba
  }

  // Arco de fondo por zonas de color
  zones.forEach(([zmin, zmax, color]) => {
    const a1 = valToAngle(Math.max(min, zmin));
    const a2 = valToAngle(Math.min(max, zmax));
    if (a2 <= a1) return;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, a1, a2, false);
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
  });

  // Aguja
  const ang = valToAngle(value);
  const nx = cx + radius * 0.85 * Math.cos(ang);
  const ny = cy + radius * 0.85 * Math.sin(ang);
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(nx, ny);
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 3;
  ctx.lineCap = "round";
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(cx, cy, 5, 0, Math.PI * 2);
  ctx.fillStyle = "#ffffff";
  ctx.fill();

  // Textos
  ctx.fillStyle = "#ffffff";
  ctx.textAlign = "center";
  ctx.font = "bold 14px Segoe UI, Arial, sans-serif";
  ctx.fillText(valueText, cx, cy + 24);
  ctx.font = "bold 11px Segoe UI, Arial, sans-serif";
  ctx.fillText(title, cx, 14);
}

window.drawGauge = drawGauge;
