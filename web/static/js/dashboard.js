// ---- Rangos y colores (mismos valores que monitoreoV2.py) ----
const COLOR_TEMP = "#E63946";
const COLOR_PH = "#2A9D8F";
const COLOR_OD = "#9B59B6";
const COLOR_ON = "#2ECC71";
const COLOR_ALERTA = "#E74C3C";
const COLOR_ADVERTENCIA = "#F4B400";

const RANGO_TEMP = [20.0, 45.0];
const RANGO_TEMP_SEGURO = [36.5, 37.5];
const RANGO_PH = [0.0, 14.0];
const RANGO_PH_SEGURO = [6.8, 7.2];
const RANGO_OD = [0.0, 3.5];
const OD_INDUCCION = 0.7;
const OD_COSECHA = 2.0;

const ZONAS_TEMP = [
  [RANGO_TEMP[0], RANGO_TEMP_SEGURO[0], COLOR_ALERTA],
  [RANGO_TEMP_SEGURO[0], RANGO_TEMP_SEGURO[1], COLOR_ON],
  [RANGO_TEMP_SEGURO[1], RANGO_TEMP[1], COLOR_ALERTA],
];
const ZONAS_PH = [
  [RANGO_PH[0], RANGO_PH_SEGURO[0], COLOR_ALERTA],
  [RANGO_PH_SEGURO[0], RANGO_PH_SEGURO[1], COLOR_ON],
  [RANGO_PH_SEGURO[1], RANGO_PH[1], COLOR_ALERTA],
];
const ZONAS_OD = [
  [RANGO_OD[0], OD_INDUCCION, "#3498DB"],
  [OD_INDUCCION, OD_COSECHA, COLOR_ADVERTENCIA],
  [OD_COSECHA, RANGO_OD[1], COLOR_ON],
];

// ---- Estado inicial de gauges/PID (sin datos) ----
function dibujarGaugesVacios() {
  drawGauge("gauge-temp", RANGO_TEMP[0], ...RANGO_TEMP, ZONAS_TEMP, "TEMPERATURA", "-- °C");
  drawGauge("gauge-ph", RANGO_PH[0], ...RANGO_PH, ZONAS_PH, "pH", "--");
  drawGauge("gauge-od", RANGO_OD[0], ...RANGO_OD, ZONAS_OD, "OD600", "--");
  updatePID({ rele1: false, rele2: false, rele3: false, rele4: false, rele5: false, rele6: false });
}
dibujarGaugesVacios();

// ---- Chart.js: históricos ----
function crearChart(canvasId, label, color) {
  const ctx = document.getElementById(canvasId).getContext("2d");
  return new Chart(ctx, {
    type: "line",
    data: { labels: [], datasets: [{ label, data: [], borderColor: color, backgroundColor: "transparent", tension: 0.25, pointRadius: 2 }] },
    options: {
      responsive: true,
      animation: false,
      scales: {
        x: { ticks: { color: "#ccc", maxRotation: 45 }, grid: { color: "#274870" } },
        y: { ticks: { color: "#ccc" }, grid: { color: "#274870" } },
      },
      plugins: { legend: { labels: { color: "#fff" } } },
    },
  });
}

const chartTemp = crearChart("chart-temp", "Temp (°C)", COLOR_TEMP);
const chartPh = crearChart("chart-ph", "pH", COLOR_PH);
const chartOd = crearChart("chart-od", "OD600", COLOR_OD);

function actualizarCharts(rows) {
  const labels = rows.map((r) => {
    if (!r.fecha_hora) return "";
    const d = new Date(r.fecha_hora);
    return d.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
  });
  chartTemp.data.labels = labels;
  chartTemp.data.datasets[0].data = rows.map((r) => r.temperatura ?? 0);
  chartTemp.update();

  chartPh.data.labels = labels;
  chartPh.data.datasets[0].data = rows.map((r) => r.ph ?? 0);
  chartPh.update();

  chartOd.data.labels = labels;
  chartOd.data.datasets[0].data = rows.map((r) => r.od600 ?? 0);
  chartOd.update();
}

// ---- Estado / status dot ----
const statusDot = document.getElementById("status-dot");
function actualizarStatus(status) {
  const textos = {
    ONLINE: "● ONLINE",
    OFFLINE: "● OFFLINE",
    EMERGENCIA: "● EMERGENCIA",
    SIN_DATOS: "● SIN DATOS",
    ERROR_BD: "● ERROR BD",
  };
  statusDot.textContent = textos[status] || `● ${status}`;
  statusDot.className = "status " + status.toLowerCase();
}

// ---- Tabla de eventos ----
const eventsBody = document.querySelector("#events-table tbody");
function actualizarEventos(eventos) {
  eventsBody.innerHTML = "";
  eventos.forEach((ev) => {
    const tr = document.createElement("tr");
    const hora = ev.hora ? new Date(ev.hora).toLocaleTimeString("es-MX") : "";
    tr.innerHTML = `<td>${hora}</td><td>${ev.descripcion}</td>`;
    eventsBody.appendChild(tr);
  });
}

// ---- WebSocket en vivo ----
function conectarWS() {
  const protocolo = location.protocol === "https:" ? "wss://" : "ws://";
  const ws = new WebSocket(protocolo + location.host + "/ws/dashboard");

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    const estado = data.estado;
    actualizarStatus(estado.status);
    actualizarEventos(data.eventos || []);

    if (estado.rows && estado.rows.length > 0) {
      const u = estado.rows[estado.rows.length - 1];
      if (estado.status === "ONLINE" || estado.status === "EMERGENCIA") {
        drawGauge("gauge-temp", u.temperatura ?? RANGO_TEMP[0], ...RANGO_TEMP, ZONAS_TEMP, "TEMPERATURA", `${(u.temperatura ?? 0).toFixed(1)} °C`);
        drawGauge("gauge-ph", u.ph ?? RANGO_PH[0], ...RANGO_PH, ZONAS_PH, "pH", `${(u.ph ?? 0).toFixed(2)}`);
        drawGauge("gauge-od", u.od600 ?? RANGO_OD[0], ...RANGO_OD, ZONAS_OD, "OD600", `${(u.od600 ?? 0).toFixed(3)}`);
        updatePID({
          rele1: !!u.rele1, rele2: !!u.rele2, rele3: !!u.rele3,
          rele4: !!u.rele4, rele5: !!u.rele5, rele6: !!u.rele6,
        });
        actualizarCharts(estado.rows);
      } else {
        dibujarGaugesVacios();
      }
    } else {
      dibujarGaugesVacios();
    }
  };

  ws.onclose = () => {
    actualizarStatus("OFFLINE");
    setTimeout(conectarWS, 3000); // reintentar
  };

  ws.onerror = () => ws.close();
}
conectarWS();

// ---- Botones Paro / Reanudar ----
document.getElementById("btn-paro").addEventListener("click", async () => {
  if (!confirm("¿Activar PARO DE EMERGENCIA físico?")) return;
  const res = await fetch("/api/paro", { method: "POST" });
  const data = await res.json();
  alert(data.ok ? "Paro de emergencia activado en el sistema" : "No se pudo activar el paro");
});

document.getElementById("btn-reanudar").addEventListener("click", async () => {
  if (!confirm("¿Reanudar el sistema después del paro de emergencia?")) return;
  const res = await fetch("/api/reanudar", { method: "POST" });
  const data = await res.json();
  alert(data.ok ? "Comando de reanudación enviado. El PC de control lo ejecutará." : "No se pudo reanudar");
});
