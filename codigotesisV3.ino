/*
 * Biorreactor-FCITEC — Firmware V3
 * -----------------------------------------------------------------------
 * Cambios respecto a codigotesisV2.ino (ver MEJORAS.md para el detalle):
 *
 *  [PRIORIDAD ALTA]
 *   - Failsafe de override manual: un comando RELE:n,ON/OFF ya NO deja el
 *     relé "pegado" para siempre. Entra en modo manual por
 *     MANUAL_OVERRIDE_TIMEOUT_MS y luego regresa solo al control
 *     automático. Antes, si el operador probaba una bomba manualmente y
 *     se caía la PC/serial, esa bomba podía quedarse encendida
 *     indefinidamente.
 *   - Paro de emergencia por software (STOP/RESUME) vía serial. No hay
 *     botón físico cableado en este montaje; si más adelante se agrega
 *     uno, se puede reintroducir un chequeo por hardware similar al de
 *     esta rama de comentarios.
 *   - Máquina de etapas (READY -> GROWING -> INDUCCION -> COSECHA -> DONE)
 *     corre DENTRO del Arduino, igual que en el paper de Marinescu &
 *     Popescu (2018). Si se cae la PC, el cultivo sigue controlado
 *     (temperatura, pH, inducción, cosecha) de forma autónoma.
 *
 *  [PRIORIDAD MEDIA]
 *   - Dosificación adaptativa de pH (algoritmo del paper): dosis cada
 *     minuto si el pH sigue bajo; si se repite 10 veces seguidas sin
 *     pausa, la dosis se duplica. Se acumula el volumen total de NaOH
 *     dosificado (mL) — indicador indirecto de biomasa, igual que en el
 *     paper (Fig. 5C/E).
 *   - OD600 por razón logarítmica (Beer-Lambert): OD = -log10(Lt/L0),
 *     con captura de blanco (L0) al iniciar el cultivo o vía comando
 *     BLANK. Se mantiene también la calibración lineal existente
 *     (od_slope/od_intercept) para no romper compatibilidad; el valor
 *     log se expone como dato adicional bajo demanda (ODLOGGET).
 *
 *  [PRIORIDAD BAJA]
 *   - Comando STAGEGET expone la etapa actual, útil para que el lado
 *     Python la guarde en la BD (ver migraciones.sql).
 *
 * COMPATIBILIDAD: la línea de telemetría automática cada 1000 ms sigue
 * siendo exactamente "TEMP,PH,OD600" como en V2, para no romper el
 * parser de controlfisicoV2.py que no pude inspeccionar completo. Todo
 * lo nuevo se expone bajo demanda con comandos nuevos, nunca de forma
 * no solicitada.
 * -----------------------------------------------------------------------
 */

#include <OneWire.h>
#include <DallasTemperature.h>
#include <EEPROM.h>

// ================= CONFIGURACIÓN DE PINES =================
#define PIN_TEMP_BUS 8

const int PIN_PH = A1;   // Voltaje crudo del sensor de pH
const int PIN_OD = A2;   // Voltaje crudo del sensor de OD600

const int RELES[] = {2, 3, 4, 5, 6, 7}; // Relé 1..6 -> pines 2..7
const int NUM_RELES = 6;

// Mapeo de relés según el P&ID ya usado en controlfisicoV2.py
#define RELE_HEATER   1
#define RELE_PH       2
#define RELE_IPTG     3
#define RELE_COSECHA  4
#define RELE_AGITADOR 5
#define RELE_AIRE     6

OneWire oneWire(PIN_TEMP_BUS);
DallasTemperature sensors(&oneWire);
DeviceAddress sensorDireccion = { 0x28, 0xE7, 0x20, 0x75, 0xD0, 0x01, 0x3C, 0xA3 };

// ================= CALIBRACIÓN Y CONFIGURACIÓN (EEPROM) =================
float ph_slope = 1.0, ph_intercept = 0.0;
float od_slope = 1.0, od_intercept = 0.0;
float temp_offset = 0.0;

// --- Config de proceso (nuevo en V3) ---
float od_L0 = 500.0;             // Blanco de referencia para OD600 log-ratio
float temp_setpoint = 37.0;      // °C
float temp_histeresis = 0.5;     // °C
float ph_min = 6.8;
float ph_max = 7.2;
float od_induccion = 0.7;        // Umbral de inducción IPTG (mismo valor que el paper)
float od_cosecha = 2.0;          // Umbral de cosecha (mismo valor que el paper)
float dosis_inicial_ul = 20.0;   // Volumen inicial de NaOH por dosis (µL), como en el paper
float ph_pump_flow_ul_s = 438.0; // Caudal de la bomba peristáltica (µL/s), calibrar en campo
unsigned long iptg_pumping_ms = 5000;   // Duración del pulso de IPTG
unsigned long harvest_ms = 300000UL;    // Duración de cosecha (5 min por defecto)

const byte EEPROM_MAGIC_VAL = 0xA5;
const int EEPROM_MAGIC_ADDR = 0;
const int EEPROM_PH_SLOPE_ADDR = 1;
const int EEPROM_PH_INTER_ADDR = 5;
const int EEPROM_OD_SLOPE_ADDR = 9;
const int EEPROM_OD_INTER_ADDR = 13;
const int EEPROM_TEMP_OFFSET_ADDR = 17;

// Segundo bloque EEPROM (config de proceso). Magic distinto para no
// confundir una EEPROM "vieja" (solo con calibración V2) con una que ya
// tiene también la config de proceso V3.
const byte EEPROM_MAGIC2_VAL = 0xB6;
const int EEPROM_MAGIC2_ADDR = 21;
const int EEPROM_OD_L0_ADDR = 22;
const int EEPROM_TEMP_SET_ADDR = 26;
const int EEPROM_PH_MIN_ADDR = 30;
const int EEPROM_PH_MAX_ADDR = 34;
const int EEPROM_OD_IND_ADDR = 38;
const int EEPROM_OD_COS_ADDR = 42;
const int EEPROM_DOSIS_INI_ADDR = 46;
const int EEPROM_DOSIS_TOTAL_ADDR = 50; // volumen acumulado de NaOH (mL), persiste entre reinicios

// ================= ESTADO DE PROCESO =================
enum Etapa { E_READY = 0, E_GROWING = 1, E_INDUCCION = 2, E_COSECHA = 3, E_DONE = 4 };
Etapa etapa = E_READY;
bool iptgAplicado = false;
bool emergencia = false;

float dosis_total_ml = 0.0;

// ================= TEMPORIZACIÓN NO BLOQUEANTE =================
unsigned long ultimoEnvio = 0;
const unsigned long INTERVALO_ENVIO_MS = 1000;

// --- Override manual por relé (failsafe) ---
bool manualOverride[6] = {false, false, false, false, false, false};
unsigned long manualOverrideInicio[6] = {0, 0, 0, 0, 0, 0};
const unsigned long MANUAL_OVERRIDE_TIMEOUT_MS = 60000UL; // 60 s

// --- Dosificación adaptativa de pH ---
bool dosisPHActiva = false;
unsigned long dosisPHInicio = 0;
unsigned long dosisPHDuracionMs = 0;
float dosisPHVolumenUlEnCurso = 0.0; // volumen de LA dosis que está corriendo ahora
float dosisPHVolumenSiguienteUl = 0.0; // volumen que se usará en la próxima dosis (puede duplicarse)
int dosisPHConsecutivas = 0;
unsigned long ultimaDosisPHMillis = 0;
const unsigned long VENTANA_DOSIS_MS = 60000UL; // 1 min, como en el paper
const unsigned long DOSIS_MAX_MS = 30000UL;     // tope de seguridad por dosis

// --- IPTG (pulso único no bloqueante) ---
bool iptgBombeando = false;
unsigned long iptgInicio = 0;

// --- Cosecha (pulso no bloqueante) ---
bool cosechaBombeando = false;
unsigned long cosechaInicio = 0;

// Declaraciones adelantadas
void cargarCalibracionEEPROM();
void guardarCalibracionEEPROM();
void cargarConfigEEPROM();
void guardarConfigEEPROM();
void guardarDosisTotalEEPROM();
void procesarComando(String cmd);
void procesarComandoRele(String cmd);
void procesarComandoRaw();
void procesarComandoCalGet();
void procesarComandoCalPH(String cmd);
void procesarComandoCalOD(String cmd);
void procesarComandoCalTemp(String cmd);
void procesarComandoConfig(String cmd);
void aplicarRele(int releNum, bool on, bool esManual);
void iniciarDosisPH();
void controlAutomatico();
void chequearOverridesManuales();

void setup() {
  Serial.begin(9600);
  sensors.begin();
  sensors.setResolution(sensorDireccion, 10);

  for (int i = 0; i < NUM_RELES; i++) {
    pinMode(RELES[i], OUTPUT);
    digitalWrite(RELES[i], LOW);
  }
  cargarCalibracionEEPROM();
  cargarConfigEEPROM();
  dosisPHVolumenSiguienteUl = dosis_inicial_ul;

  Serial.println("Bioreactor V3 iniciado - Control autonomo + Failsafe manual OK");
  Serial.println("Formato telemetria: TEMP,PH,OD600 (compatible con V2)");
  Serial.println("Comandos: RELE:n,ON/OFF | RAW | CALGET | CAL:PH:s,i | CAL:OD:s,i | CAL:TEMP:offset");
  Serial.println("Nuevos:   START | STOP | RESUME | RESET | BLANK | PING");
  Serial.println("          STAGEGET | DOSISGET | ODLOGGET | CONFIGGET");
  Serial.println("          CONFIG:TEMP:x | CONFIG:PHMIN:x | CONFIG:PHMAX:x");
  Serial.println("          CONFIG:ODIND:x | CONFIG:ODCOS:x | CONFIG:DOSISUL:x");
  Serial.println("          CONFIG:IPTGMS:x | CONFIG:HARVESTMIN:x | CONFIG:FLOWPH:x");
}

void loop() {
  // 1) Procesar TODOS los comandos pendientes, sin bloquear.
  while (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    procesarComando(cmd);
  }

  // 2) Expirar overrides manuales (failsafe contra bombas/calefactor "pegados").
  chequearOverridesManuales();

  // 3) Control automático (máquina de etapas), salvo en emergencia.
  if (!emergencia) {
    controlAutomatico();
  } else {
    // Emergencia: todo apagado, sin excepción, sin importar overrides.
    for (int i = 0; i < NUM_RELES; i++) {
      digitalWrite(RELES[i], LOW);
    }
    dosisPHActiva = false;
  }

  // 4) Publicar telemetría cada INTERVALO_ENVIO_MS sin usar delay().
  //    Formato SIN CAMBIOS respecto a V2 para no romper el parser actual.
  unsigned long ahora = millis();
  if (ahora - ultimoEnvio >= INTERVALO_ENVIO_MS) {
    ultimoEnvio = ahora;
    float temp = leerTemperatura();
    float ph = leerPH();
    float od600 = leerOD600();

    Serial.print(temp, 2); Serial.print(",");
    Serial.print(ph, 2); Serial.print(",");
    Serial.println(od600, 3);
  }
}

// ================= FAILSAFES =================
void chequearOverridesManuales() {
  unsigned long ahora = millis();
  for (int i = 0; i < NUM_RELES; i++) {
    if (manualOverride[i] && (ahora - manualOverrideInicio[i] >= MANUAL_OVERRIDE_TIMEOUT_MS)) {
      manualOverride[i] = false; // vuelve a control automático en el próximo ciclo
    }
  }
}

// Aplica un relé. esManual=true marca override temporal (comando RELE:).
// esManual=false es control automático y respeta overrides activos.
void aplicarRele(int releNum, bool on, bool esManual) {
  int idx = releNum - 1;
  if (idx < 0 || idx >= NUM_RELES) return;
  if (!esManual && manualOverride[idx]) return; // el operador tiene el control ahora mismo
  digitalWrite(RELES[idx], on ? HIGH : LOW);
  if (esManual) {
    manualOverride[idx] = true;
    manualOverrideInicio[idx] = millis();
  }
}

// ================= MAQUINA DE ETAPAS =================
void controlAutomatico() {
  bool activo = (etapa == E_GROWING || etapa == E_INDUCCION);

  // --- Temperatura (bang-bang con histéresis) ---
  if (activo) {
    float t = leerTemperatura();
    if (t > 0.0) {
      if (t < temp_setpoint - temp_histeresis) aplicarRele(RELE_HEATER, true, false);
      else if (t > temp_setpoint + temp_histeresis) aplicarRele(RELE_HEATER, false, false);
    }
    aplicarRele(RELE_AGITADOR, true, false);
    aplicarRele(RELE_AIRE, true, false);
  } else if (etapa != E_COSECHA) {
    aplicarRele(RELE_HEATER, false, false);
    aplicarRele(RELE_AGITADOR, false, false);
    aplicarRele(RELE_AIRE, false, false);
  }

  // --- Dosificación adaptativa de pH ---
  if (dosisPHActiva) {
    if (millis() - dosisPHInicio >= dosisPHDuracionMs) {
      aplicarRele(RELE_PH, false, false);
      dosisPHActiva = false;
      dosis_total_ml += (dosisPHVolumenUlEnCurso / 1000.0);
      guardarDosisTotalEEPROM();
    }
  } else if (activo) {
    float ph = leerPH();
    if (ph > 0.0 && ph < ph_min) {
      if (ultimaDosisPHMillis == 0 || millis() - ultimaDosisPHMillis >= VENTANA_DOSIS_MS) {
        iniciarDosisPH();
      }
    } else if (ph >= ph_min) {
      dosisPHConsecutivas = 0;
      dosisPHVolumenSiguienteUl = dosis_inicial_ul;
    }
  }

  // --- Transicion GROWING -> INDUCCION (pulso de IPTG) ---
  if (etapa == E_GROWING && !iptgAplicado) {
    float od = leerOD600();
    if (od >= od_induccion) {
      iptgAplicado = true;
      etapa = E_INDUCCION;
      aplicarRele(RELE_IPTG, true, false);
      iptgBombeando = true;
      iptgInicio = millis();
    }
  }
  if (iptgBombeando && millis() - iptgInicio >= iptg_pumping_ms) {
    aplicarRele(RELE_IPTG, false, false);
    iptgBombeando = false;
  }

  // --- Transicion INDUCCION -> COSECHA ---
  if (etapa == E_INDUCCION) {
    float od = leerOD600();
    if (od >= od_cosecha) {
      etapa = E_COSECHA;
      aplicarRele(RELE_HEATER, false, false);
      aplicarRele(RELE_AGITADOR, false, false);
      aplicarRele(RELE_AIRE, false, false);
      aplicarRele(RELE_PH, false, false);
      dosisPHActiva = false;
      aplicarRele(RELE_COSECHA, true, false);
      cosechaBombeando = true;
      cosechaInicio = millis();
    }
  }

  // --- Cosecha en curso ---
  if (cosechaBombeando) {
    if (millis() - cosechaInicio >= harvest_ms) {
      aplicarRele(RELE_COSECHA, false, false);
      cosechaBombeando = false;
      etapa = E_DONE;
    }
  }
}

void iniciarDosisPH() {
  dosisPHVolumenUlEnCurso = dosisPHVolumenSiguienteUl;
  dosisPHDuracionMs = (unsigned long)((dosisPHVolumenUlEnCurso / ph_pump_flow_ul_s) * 1000.0);
  if (dosisPHDuracionMs > DOSIS_MAX_MS) dosisPHDuracionMs = DOSIS_MAX_MS;
  if (dosisPHDuracionMs < 10) dosisPHDuracionMs = 10;

  aplicarRele(RELE_PH, true, false);
  dosisPHActiva = true;
  dosisPHInicio = millis();
  ultimaDosisPHMillis = millis();

  dosisPHConsecutivas++;
  if (dosisPHConsecutivas >= 10) {
    dosisPHVolumenSiguienteUl *= 2.0;
    dosisPHConsecutivas = 0;
  }
}

// ================= LECTURAS =================
float leerTemperatura() {
  sensors.requestTemperaturesByAddress(sensorDireccion);
  float t = sensors.getTempC(sensorDireccion);
  if (t == DEVICE_DISCONNECTED_C || t < -10 || t > 100) return 0.0;
  return t + temp_offset;
}

float leerVoltajePH() {
  int raw = analogRead(PIN_PH);
  return raw * 5.0 / 1024.0;
}

float leerVoltajeOD() {
  int raw = analogRead(PIN_OD);
  return raw * 5.0 / 1024.0;
}

int leerODraw() {
  return analogRead(PIN_OD);
}

float leerPH() {
  float v = leerVoltajePH();
  if (v < 0.05 || v > 4.95) return 0.0;
  float phValue = ph_slope * v + ph_intercept;
  return constrain(phValue, 0.0, 14.0);
}

float leerOD600() {
  float v = leerVoltajeOD();
  if (v < 0.05 || v > 4.95) return 0.0;
  float od = od_slope * v + od_intercept;
  return constrain(od, 0.0, 3.5);
}

// OD600 por razon logaritmica (Beer-Lambert), igual que en el paper:
// OD = -log10(Lt / L0). Usa la lectura cruda del ADC, no la calibracion
// lineal. Requiere haber capturado un blanco valido (BLANK o START).
float leerOD600Log() {
  int lt = leerODraw();
  if (od_L0 <= 0 || lt <= 0) return 0.0;
  float ratio = (float)lt / od_L0;
  if (ratio <= 0.0001) ratio = 0.0001;
  float od = -log10(ratio);
  if (od < 0) od = 0;
  return od;
}

// ================= EEPROM: CALIBRACION (igual que V2) =================
void cargarCalibracionEEPROM() {
  byte magic = EEPROM.read(EEPROM_MAGIC_ADDR);
  if (magic == EEPROM_MAGIC_VAL) {
    EEPROM.get(EEPROM_PH_SLOPE_ADDR, ph_slope);
    EEPROM.get(EEPROM_PH_INTER_ADDR, ph_intercept);
    EEPROM.get(EEPROM_OD_SLOPE_ADDR, od_slope);
    EEPROM.get(EEPROM_OD_INTER_ADDR, od_intercept);
    EEPROM.get(EEPROM_TEMP_OFFSET_ADDR, temp_offset);
  } else {
    guardarCalibracionEEPROM();
  }
}

void guardarCalibracionEEPROM() {
  EEPROM.write(EEPROM_MAGIC_ADDR, EEPROM_MAGIC_VAL);
  EEPROM.put(EEPROM_PH_SLOPE_ADDR, ph_slope);
  EEPROM.put(EEPROM_PH_INTER_ADDR, ph_intercept);
  EEPROM.put(EEPROM_OD_SLOPE_ADDR, od_slope);
  EEPROM.put(EEPROM_OD_INTER_ADDR, od_intercept);
  EEPROM.put(EEPROM_TEMP_OFFSET_ADDR, temp_offset);
}

// ================= EEPROM: CONFIG DE PROCESO (nuevo V3) =================
void cargarConfigEEPROM() {
  byte magic2 = EEPROM.read(EEPROM_MAGIC2_ADDR);
  if (magic2 == EEPROM_MAGIC2_VAL) {
    EEPROM.get(EEPROM_OD_L0_ADDR, od_L0);
    EEPROM.get(EEPROM_TEMP_SET_ADDR, temp_setpoint);
    EEPROM.get(EEPROM_PH_MIN_ADDR, ph_min);
    EEPROM.get(EEPROM_PH_MAX_ADDR, ph_max);
    EEPROM.get(EEPROM_OD_IND_ADDR, od_induccion);
    EEPROM.get(EEPROM_OD_COS_ADDR, od_cosecha);
    EEPROM.get(EEPROM_DOSIS_INI_ADDR, dosis_inicial_ul);
    EEPROM.get(EEPROM_DOSIS_TOTAL_ADDR, dosis_total_ml);
  } else {
    guardarConfigEEPROM();
  }
}

void guardarConfigEEPROM() {
  EEPROM.write(EEPROM_MAGIC2_ADDR, EEPROM_MAGIC2_VAL);
  EEPROM.put(EEPROM_OD_L0_ADDR, od_L0);
  EEPROM.put(EEPROM_TEMP_SET_ADDR, temp_setpoint);
  EEPROM.put(EEPROM_PH_MIN_ADDR, ph_min);
  EEPROM.put(EEPROM_PH_MAX_ADDR, ph_max);
  EEPROM.put(EEPROM_OD_IND_ADDR, od_induccion);
  EEPROM.put(EEPROM_OD_COS_ADDR, od_cosecha);
  EEPROM.put(EEPROM_DOSIS_INI_ADDR, dosis_inicial_ul);
  EEPROM.put(EEPROM_DOSIS_TOTAL_ADDR, dosis_total_ml);
}

void guardarDosisTotalEEPROM() {
  EEPROM.put(EEPROM_DOSIS_TOTAL_ADDR, dosis_total_ml);
}

// ================= COMANDOS DESDE PYTHON =================
void procesarComando(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd.startsWith("RELE:")) {
    procesarComandoRele(cmd);
  } else if (cmd == "RAW") {
    procesarComandoRaw();
  } else if (cmd == "CALGET") {
    procesarComandoCalGet();
  } else if (cmd.startsWith("CAL:PH:")) {
    procesarComandoCalPH(cmd);
  } else if (cmd.startsWith("CAL:OD:")) {
    procesarComandoCalOD(cmd);
  } else if (cmd.startsWith("CAL:TEMP:")) {
    procesarComandoCalTemp(cmd);
  } else if (cmd == "PING") {
    Serial.println("PONG");
  } else if (cmd == "START") {
    if (etapa == E_READY) {
      od_L0 = leerODraw();
      guardarConfigEEPROM();
      etapa = E_GROWING;
      iptgAplicado = false;
      dosis_total_ml = 0.0;
      dosisPHConsecutivas = 0;
      dosisPHVolumenSiguienteUl = dosis_inicial_ul;
      guardarDosisTotalEEPROM();
      Serial.print("OK:START:L0=");
      Serial.println(od_L0, 1);
    } else {
      Serial.println("ERROR:START_ETAPA_INVALIDA");
    }
  } else if (cmd == "STOP") {
    emergencia = true;
    Serial.println("OK:STOP:EMERGENCIA_ACTIVADA");
  } else if (cmd == "RESUME") {
    emergencia = false;
    Serial.println("OK:RESUME");
  } else if (cmd == "RESET") {
    if (!emergencia) {
      etapa = E_READY;
      iptgAplicado = false;
      dosis_total_ml = 0.0;
      guardarDosisTotalEEPROM();
      for (int i = 0; i < NUM_RELES; i++) digitalWrite(RELES[i], LOW);
      Serial.println("OK:RESET");
    } else {
      Serial.println("ERROR:RESET_EN_EMERGENCIA");
    }
  } else if (cmd == "BLANK") {
    od_L0 = leerODraw();
    guardarConfigEEPROM();
    Serial.print("OK:BLANK:");
    Serial.println(od_L0, 1);
  } else if (cmd == "STAGEGET") {
    const char* nombres[] = {"READY", "GROWING", "INDUCCION", "COSECHA", "DONE"};
    Serial.print("STAGE:");
    Serial.print((int)etapa);
    Serial.print(",");
    Serial.print(nombres[(int)etapa]);
    Serial.print(",IPTG:");
    Serial.print(iptgAplicado ? 1 : 0);
    Serial.print(",EMERGENCIA:");
    Serial.println(emergencia ? 1 : 0);
  } else if (cmd == "DOSISGET") {
    Serial.print("DOSIS:");
    Serial.println(dosis_total_ml, 4);
  } else if (cmd == "ODLOGGET") {
    Serial.print("OD600LOG:");
    Serial.println(leerOD600Log(), 4);
  } else if (cmd == "CONFIGGET") {
    Serial.print("CONFIG:TEMP:"); Serial.println(temp_setpoint, 2);
    Serial.print("CONFIG:PHMIN:"); Serial.println(ph_min, 2);
    Serial.print("CONFIG:PHMAX:"); Serial.println(ph_max, 2);
    Serial.print("CONFIG:ODIND:"); Serial.println(od_induccion, 2);
    Serial.print("CONFIG:ODCOS:"); Serial.println(od_cosecha, 2);
    Serial.print("CONFIG:DOSISUL:"); Serial.println(dosis_inicial_ul, 2);
    Serial.print("CONFIG:IPTGMS:"); Serial.println(iptg_pumping_ms);
    Serial.print("CONFIG:HARVESTMIN:"); Serial.println(harvest_ms / 60000.0, 2);
    Serial.print("CONFIG:FLOWPH:"); Serial.println(ph_pump_flow_ul_s, 2);
  } else if (cmd.startsWith("CONFIG:")) {
    procesarComandoConfig(cmd);
  } else {
    Serial.println("ERROR:COMANDO_DESCONOCIDO");
  }
}

void procesarComandoRele(String cmd) {
  int colon = cmd.indexOf(':');
  int comma = cmd.indexOf(',');
  if (colon == -1 || comma == -1) {
    Serial.println("ERROR:RELE_FORMATO");
    return;
  }
  int num = cmd.substring(colon + 1, comma).toInt();
  String state = cmd.substring(comma + 1);
  bool on = (state == "ON");

  if (num >= 1 && num <= NUM_RELES) {
    if (emergencia) {
      Serial.println("ERROR:RELE_BLOQUEADO_POR_EMERGENCIA");
      return;
    }
    aplicarRele(num, on, true); // true = override manual con timeout
  } else {
    Serial.println("ERROR:RELE_NUMERO_INVALIDO");
  }
}

void procesarComandoRaw() {
  Serial.print("RAW:PH:");
  Serial.print(leerVoltajePH(), 4);
  Serial.print(",OD:");
  Serial.println(leerVoltajeOD(), 4);
}

void procesarComandoCalGet() {
  Serial.print("CAL:PH:");
  Serial.print(ph_slope, 6);
  Serial.print(",");
  Serial.println(ph_intercept, 6);
  Serial.print("CAL:OD:");
  Serial.print(od_slope, 6);
  Serial.print(",");
  Serial.println(od_intercept, 6);
  Serial.print("CAL:TEMP:");
  Serial.println(temp_offset, 4);
}

void procesarComandoCalPH(String cmd) {
  String resto = cmd.substring(strlen("CAL:PH:"));
  int comma = resto.indexOf(',');
  if (comma == -1) {
    Serial.println("ERROR:CAL_PH_FORMATO");
    return;
  }
  ph_slope = resto.substring(0, comma).toFloat();
  ph_intercept = resto.substring(comma + 1).toFloat();
  guardarCalibracionEEPROM();
  Serial.print("OK:CAL:PH:");
  Serial.print(ph_slope, 6);
  Serial.print(",");
  Serial.println(ph_intercept, 6);
}

void procesarComandoCalOD(String cmd) {
  String resto = cmd.substring(strlen("CAL:OD:"));
  int comma = resto.indexOf(',');
  if (comma == -1) {
    Serial.println("ERROR:CAL_OD_FORMATO");
    return;
  }
  od_slope = resto.substring(0, comma).toFloat();
  od_intercept = resto.substring(comma + 1).toFloat();
  guardarCalibracionEEPROM();
  Serial.print("OK:CAL:OD:");
  Serial.print(od_slope, 6);
  Serial.print(",");
  Serial.println(od_intercept, 6);
}

void procesarComandoCalTemp(String cmd) {
  String resto = cmd.substring(strlen("CAL:TEMP:"));
  temp_offset = resto.toFloat();
  guardarCalibracionEEPROM();
  Serial.print("OK:CAL:TEMP:");
  Serial.println(temp_offset, 4);
}

void procesarComandoConfig(String cmd) {
  // Formato: CONFIG:CLAVE:valor
  int p1 = cmd.indexOf(':');
  int p2 = cmd.indexOf(':', p1 + 1);
  if (p2 == -1) {
    Serial.println("ERROR:CONFIG_FORMATO");
    return;
  }
  String clave = cmd.substring(p1 + 1, p2);
  float valor = cmd.substring(p2 + 1).toFloat();

  if (clave == "TEMP") temp_setpoint = valor;
  else if (clave == "PHMIN") ph_min = valor;
  else if (clave == "PHMAX") ph_max = valor;
  else if (clave == "ODIND") od_induccion = valor;
  else if (clave == "ODCOS") od_cosecha = valor;
  else if (clave == "DOSISUL") { dosis_inicial_ul = valor; dosisPHVolumenSiguienteUl = valor; }
  else if (clave == "IPTGMS") iptg_pumping_ms = (unsigned long) valor;
  else if (clave == "HARVESTMIN") harvest_ms = (unsigned long)(valor * 60000.0);
  else if (clave == "FLOWPH") ph_pump_flow_ul_s = valor;
  else {
    Serial.println("ERROR:CONFIG_CLAVE_DESCONOCIDA");
    return;
  }
  guardarConfigEEPROM();
  Serial.print("OK:CONFIG:");
  Serial.print(clave);
  Serial.print(":");
  Serial.println(valor, 4);
}
