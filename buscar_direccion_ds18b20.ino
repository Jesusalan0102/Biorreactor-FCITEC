// buscar_direccion_ds18b20.ino
// Carga este sketch SOLO para leer la dirección de tu sensor DS18B20 (con el bus de datos en el pin 8).
// Abre el Monitor Serie a 9600 baudios y copia la línea "DeviceAddress ..." dentro de
// codigotesisV2.ino, en lugar de la que dice "Dirección ROM específica de TU sensor DS18B20".
#include <OneWire.h>

const int PIN_TEMP_BUS = 8;
OneWire ds(PIN_TEMP_BUS);

void setup() {
  Serial.begin(9600);
  delay(500);
  byte addr[8];
  int n = 0;
  ds.reset_search();
  while (ds.search(addr)) {
    n++;
    Serial.print("Sensor "); Serial.print(n); Serial.print(": DeviceAddress sensorDireccion = { ");
    for (int i = 0; i < 8; i++) {
      Serial.print("0x");
      if (addr[i] < 16) Serial.print("0");
      Serial.print(addr[i], HEX);
      if (i < 7) Serial.print(", ");
    }
    Serial.println(" };");
    if (OneWire::crc8(addr, 7) != addr[7]) Serial.println("  (CRC no válido: revisa el cableado y la resistencia de 4.7k)");
  }
  if (n == 0) Serial.println("No se encontró ningún sensor: revisa DATA en el pin 8, 5V, GND y la resistencia de 4.7k entre DATA y 5V.");
}

void loop() {}
