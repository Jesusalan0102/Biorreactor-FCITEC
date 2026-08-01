#include <OneWire.h>
#include <DallasTemperature.h>
#include <EEPROM.h>

// ================= CONFIGURACIÓN DE PINES =================
// El bus OneWire ya NO comparte pin con ningún relé (antes pin 2 chocaba
// con RELES[0]). Se movió al pin 8, que está libre.
#define PIN_TEMP_BUS 8
const int PIN_PH = A1;    // Pin analógico para pH (voltaje crudo del sensor)
const int PIN_OD = A2;    // Pin analógico para OD600 (voltaje crudo del sensor)
const int RELES[] = {2, 3, 4, 5, 6, 7};   // Relé 1..6 -> pines 2..7
const int NUM_RELES = 6;

OneWire oneWire(PIN_TEMP_BUS);
DallasTemperature sensors(&oneWire);

// Dirección ROM específica de TU sensor DS18B20
DeviceAddress sensorDireccion = { 0x28, 0xE7, 0x20, 0x75, 0xD0, 0x01, 0x3C, 0xA3 };

// ================= CALIBRACIÓN (RAM, respaldada en EEPROM) =================
// pH_real   = ph_slope   * V_ph  + ph_intercept
// OD600     = od_slope   * V_od  + od_intercept
// Temp_real = Temp_cruda + temp_offset
float ph_slope = 1.0,  ph_intercept = 0.0;
float od_slope = 1.0,  od_intercept = 0.0;
float temp_offset = 0.0;

const byte EEPROM_MAGIC_VAL = 0xA5;
const int EEPROM_MAGIC_ADDR      = 0;
const int EEPROM_PH_SLOPE_ADDR   = 1;
const int EEPROM_PH_INTER_ADDR   = 5;
const int EEPROM_OD_SLOPE_ADDR   = 9;
const int EEPROM_OD_INTER_ADDR   = 13;
const int EEPROM_TEMP_OFFSET_ADDR = 17;

// ================= TEMPORIZACIÓN NO BLOQUEANTE =================
unsigned long ultimoEnvio = 0;
const unsigned long INTERVALO_ENVIO_MS = 1000;

// Declaraciones adelantadas (buena práctica, evita sorpresas con el auto
// prototyping del IDE de Arduino cuando hay muchas funciones)
void cargarCalibracionEEPROM();
void guardarCalibracionEEPROM();
void procesarComando(String cmd);
void procesarComandoRele(String cmd);
void procesarComandoRaw();
void procesarComandoCalGet();
void procesarComandoCalPH(String cmd);
void procesarComandoCalOD(String cmd);
void procesarComandoCalTemp(String cmd);

void setup() {
  Serial.begin(9600);
  sensors.begin();
  sensors.setResolution(sensorDireccion, 10);

  for (int i = 0; i < NUM_RELES; i++) {
    pinMode(RELES[i], OUTPUT);
    digitalWrite(RELES[i], LOW);
  }

  cargarCalibracionEEPROM();

  Serial.println("Bioreactor iniciado - Filtros de Seguridad OK");
  Serial.println("Formato: TEMP,PH,OD600");
  Serial.println("Comandos: RELE:n,ON/OFF | RAW | CALGET | CAL:PH:s,i | CAL:OD:s,i | CAL:TEMP:offset");
}

void loop() {
  // 1) Procesar TODOS los comandos pendientes en el buffer, sin bloquear.
  //    Antes solo se leía un comando por vuelta del loop y el loop tenía
  //    un delay(1000) fijo, así que un paro de emergencia o una calibración
  //    podían tardar hasta 1 s en aplicarse. Ahora se atienden de inmediato.
  while (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    procesarComando(cmd);
  }

  // 2) Publicar telemetría cada INTERVALO_ENVIO_MS sin usar delay().
  unsigned long ahora = millis();
  if (ahora - ultimoEnvio >= INTERVALO_ENVIO_MS) {
    ultimoEnvio = ahora;

    float temp  = leerTemperatura();
    float ph    = leerPH();
    float od600 = leerOD600();

    Serial.print(temp, 2); Serial.print(",");
    Serial.print(ph, 2);   Serial.print(",");
    Serial.println(od600, 3);
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

float leerPH() {
  float v = leerVoltajePH();

  // FILTRO: fuera de este rango es ruido o sensor desconectado.
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

// ================= EEPROM =================

void cargarCalibracionEEPROM() {
  byte magic = EEPROM.read(EEPROM_MAGIC_ADDR);
  if (magic == EEPROM_MAGIC_VAL) {
    EEPROM.get(EEPROM_PH_SLOPE_ADDR, ph_slope);
    EEPROM.get(EEPROM_PH_INTER_ADDR, ph_intercept);
    EEPROM.get(EEPROM_OD_SLOPE_ADDR, od_slope);
    EEPROM.get(EEPROM_OD_INTER_ADDR, od_intercept);
    EEPROM.get(EEPROM_TEMP_OFFSET_ADDR, temp_offset);
  } else {
    // Primera vez que corre este sketch en esta placa: guarda los
    // valores por defecto (slope=1, intercept=0) como punto de partida.
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
    digitalWrite(RELES[num - 1], on ? HIGH : LOW);
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
  ph_slope     = resto.substring(0, comma).toFloat();
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
  od_slope     = resto.substring(0, comma).toFloat();
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
