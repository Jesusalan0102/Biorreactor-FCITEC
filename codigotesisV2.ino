#include <OneWire.h>
#include <DallasTemperature.h>

// --- CONFIGURACIÓN DE PINES ---
#define PIN_TEMP 2        // Pin donde detectaste el sensor DS18B20
const int PIN_PH = A1;    // Pin analógico para pH
const int PIN_OD = A2;    // Pin analógico para OD600
const int RELES[] = {2, 3, 4, 5, 6, 7}; 

OneWire oneWire(PIN_TEMP);
DallasTemperature sensors(&oneWire);

// Dirección ROM específica de TU sensor
DeviceAddress sensorDireccion = { 0x28, 0xE7, 0x20, 0x75, 0xD0, 0x01, 0x3C, 0xA3 };

// --- CONSTANTES DE CALIBRACIÓN (Ajustar con buffers reales) ---
float ph7_v = 2.50;    
float ph4_v = 3.05;    
float od_aire_v = 4.5; 
float od_max_v  = 0.5; 

void setup() {
  Serial.begin(9600);
  sensors.begin();
  sensors.setResolution(sensorDireccion, 10); 

  for (int i = 0; i < 6; i++) {
    pinMode(RELES[i], OUTPUT);
    digitalWrite(RELES[i], LOW);
  }

  Serial.println("Bioreactor iniciado - Filtros de Seguridad OK");
  Serial.println("TEMP,PH,OD600");
}

void loop() {
  float temp  = leerTemperatura();
  float ph    = leerPH();
  float od600 = leerOD600();

  // Envío de datos formateados para Python/SCADA
  Serial.print(temp, 2); Serial.print(",");
  Serial.print(ph, 2);   Serial.print(",");
  Serial.println(od600, 3);

  if (Serial.available() > 0) {
    procesarComando(Serial.readStringUntil('\n'));
  }
  delay(1000); 
}

// --- FUNCIONES DE LECTURA ---

float leerTemperatura() {
  sensors.requestTemperaturesByAddress(sensorDireccion);
  float t = sensors.getTempC(sensorDireccion);
  
  // Si el sensor se desconecta o da error, marcar 0.0
  if (t == DEVICE_DISCONNECTED_C || t < -10 || t > 100) return 0.0;
  return t;
}

float leerPH() {
  int raw = analogRead(PIN_PH);
  float v = raw * 5.0 / 1024.0;
  
  // FILTRO: Si el voltaje es muy bajo (<0.5V) o muy alto (>4.8V), 
  // es ruido o sensor desconectado. Forzamos a pH 0.0.
  if (v < 0.5 || v > 4.8) return 0.0; 

  float slope = (7.0 - 4.0) / (ph7_v - ph4_v);
  float phValue = 7.0 + (v - ph7_v) * slope;
  
  return constrain(phValue, 0.0, 14.0);
}

float leerOD600() {
  int raw = analogRead(PIN_OD);
  float v = raw * 5.0 / 1024.0;

  // FILTRO: Voltaje por debajo de 0.5V suele ser ruido en pin vacío
  if (v < 0.5) return 0.0;

  float od = (v - od_aire_v) * (3.0 - 0.0) / (od_max_v - od_aire_v) + 0.0;
  return constrain(od, 0.0, 3.5); 
}

void procesarComando(String cmd) {
  cmd.trim();
  if (cmd.startsWith("RELE:")) {
    int colon = cmd.indexOf(':');
    int comma = cmd.indexOf(',');
    if (colon == -1 || comma == -1) return;

    int num = cmd.substring(colon + 1, comma).toInt();
    String state = cmd.substring(comma + 1);
    bool on = (state == "ON");

    if (num >= 1 && num <= 6) {
      digitalWrite(RELES[num - 1], on ? HIGH : LOW);
    }
  }
}