/**
 * Colorea el diagrama P&ID (SVG) según el estado de los 6 relés.
 * estados = {rele1: bool, rele2: bool, ..., rele6: bool}
 * Mapeo (igual que monitoreoV2.py):
 *   rele1 = Calefacción, rele2 = Bomba pH(NaOH), rele3 = Bomba IPTG,
 *   rele4 = Bomba Cosecha, rele5 = Agitador, rele6 = Aireación
 */
function updatePID(estados) {
  const ON = "#2ECC71";
  const OFF = "#555555";

  const fills = {
    "pid-rele1": estados.rele1,
    "pid-rele2": estados.rele2,
    "pid-rele3": estados.rele3,
    "pid-rele4": estados.rele4,
    "pid-rele5": estados.rele5,
    "pid-rele6": estados.rele6,
  };
  for (const [id, on] of Object.entries(fills)) {
    const el = document.getElementById(id);
    if (el) el.setAttribute("fill", on ? ON : OFF);
  }

  const strokes = {
    "pid-eje-rele5": estados.rele5,
    "pid-line-rele2": estados.rele2,
    "pid-line-rele3": estados.rele3,
    "pid-line-rele6": estados.rele6,
    "pid-line-rele4a": estados.rele4,
    "pid-line-rele4b": estados.rele4,
  };
  for (const [id, on] of Object.entries(strokes)) {
    const el = document.getElementById(id);
    if (el) el.setAttribute("stroke", on ? ON : OFF);
  }

  const bottle = document.getElementById("pid-bottle");
  if (bottle) bottle.setAttribute("fill", estados.rele4 ? "#4a90d9" : "#2c3e50");
}

window.updatePID = updatePID;
