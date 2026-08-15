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

// Sensor de flujo (tipo turbina con salida de pulsos, igual en principio
// al FL1 del paper de referencia). A diferencia del paper, aquí NO se usa
// para el OD600 -- este diseño usa el sensor de OD sumergido (Beer-
// Lambert), que no requiere bombear la muestra a través de él, así que no
// existe una "OD Pump" que monitorear. En su lugar, este sensor se usa
// para verificar que las bombas de dosificación (pH/NaOH, IPTG, cosecha)
// realmente estén moviendo líquido cuando están encendidas -- útil para
// detectar una manguera doblada, una bomba atascada o un reservorio vacío.
// Pin 18 es uno de los pines con capacidad de interrupción externa del
// Mega (INT5); los pines 2 y 3, que también la tienen, ya están tomados
// por los relés 1 y 2.
const int PIN_FLOW = 18;

// El módulo de 8 relés SRD-05VDC-SL-C (Songle) es de activación en BAJO:
// el optoacoplador enciende el relé (LED prendido, contacto cerrado)
// cuando el pin de control recibe LOW, y lo apaga con HIGH. Es el
// comportamiento estándar de fábrica de estos módulos, no un defecto.
// Se centraliza aquí para no repetir la inversión (!) en cada llamada
// y para que quede documentado por qué se escribe "al revés".
inline void escribirRele(int pin, bool encender) {
  digitalWrite(pin, encender ? LOW : HIGH);
}

OneWire oneWire(PIN_TEMP_BUS);
DallasTemperature sensors(&oneWire);

// Dirección ROM específica de TU sensor DS18B20
DeviceAddress sensorDireccion = { 0x28, 0xE7, 0x20, 0x75, 0xD0, 0x01, 0x3C, 0xA3 };

// ================= CALIBRACIÓN (RAM, respaldada en EEPROM) =================
// pH_real   = ph_slope * V_ph + ph_intercept
// Temp_real = Temp_cruda + temp_offset
//
// OD600 usa el método de Beer-Lambert (igual que el paper de referencia):
//   OD600 = od_slope * ( -log10(V_od / od_v0) ) + od_intercept
// donde od_v0 es el voltaje "blanco" (medio sin inocular / referencia),
// capturado con el comando OD:BLANK. od_slope/od_intercept quedan como
// corrección fina de ganancia/offset sobre el resultado logarítmico,
// calibrable con estándares conocidos igual que antes.
float ph_slope = 1.0,  ph_intercept = 0.0;
float od_slope = 1.0,  od_intercept = 0.0;
float od_v0 = 0.0; // 0.0 = sin blanco capturado todavía
float temp_offset = 0.0;

// Segunda capa de seguridad, independiente de la validación que ya hace
// la app Python en el wizard de calibración (ver CalibracionWindow en
// controlfisicoV2.py). Si algún día se manda un comando CAL:PH o CAL:OD
// directamente por serial -monitor serial, otro script, prueba manual-
// sin pasar por el wizard, el firmware rechaza de plano cualquier slope
// con magnitud fuera de rango físico razonable, en vez de aplicarlo y
// guardarlo en EEPROM en silencio. Un slope de pH (ADC 0-5V -> pH 0-14)
// o de OD600 (Beer-Lambert) con |slope| > 50 no es fisicamente legítimo:
// significa que los dos puntos de calibración eran casi indistinguibles
// entre sí, y produce una lectura siempre pegada en un extremo (0/14 en
// pH, el techo de seguridad en OD600).
const float SLOPE_SOSPECHOSO = 50.0;

const byte EEPROM_MAGIC_VAL = 0xA6; // subido de 0xA5 -> fuerza reinit por el nuevo campo od_v0
const int EEPROM_MAGIC_ADDR       = 0;
const int EEPROM_PH_SLOPE_ADDR    = 1;
const int EEPROM_PH_INTER_ADDR    = 5;
const int EEPROM_OD_SLOPE_ADDR    = 9;
const int EEPROM_OD_INTER_ADDR    = 13;
const int EEPROM_TEMP_OFFSET_ADDR = 17;
const int EEPROM_OD_V0_ADDR       = 21;

// ================= SENSOR DE FLUJO (FL1) =================
// Contador de pulsos incrementado por interrupción externa. "volatile"
// es obligatorio: el compilador no debe optimizar el acceso a esta
// variable, porque cambia fuera del flujo normal del programa (dentro
// de la ISR).
volatile unsigned long pulsosFlujo = 0;

void isrFlujo() {
  pulsosFlujo++;
}

// Sensibilidad del sensor: pulsos por litro. Este valor depende del
// modelo físico de sensor de flujo que se instale (p.ej. YF-S201 da
// ~450 pulsos/litro; el sensor 1/8'' SEN0216 usado en el paper de
// referencia tiene su propia constante en su datasheet). Es solo un
// valor de referencia -- AJUSTAR al sensor real antes de confiar en el
// caudal estimado en mL/min. El conteo de pulsos crudo (que es lo que
// se usa para detectar "bomba sin flujo") no depende de este valor.
const float FLOW_PULSOS_POR_LITRO = 450.0;

// Vigilancia de "bomba sin flujo": las bombas de dosificación (pH/NaOH,
// IPTG, cosecha) son las que tiene sentido monitorear -- no el
// agitador, la aireación, ni la calefacción. Si un relé de esta lista
// lleva encendido más de FLOW_TIMEOUT_MS sin que se detecte NINGÚN
// pulso nuevo del sensor de flujo, se reporta una advertencia por
// serial. Esto es una señal de diagnóstico para que el operador revise
// la línea físicamente -- NO apaga el relé automáticamente, porque
// solo una línea a la vez suele tener el sensor de flujo intercalado
// (a diferencia del watchdog de comunicación, que sí es una función de
// seguridad y si actúa solo).
const int RELES_DOSIFICACION[] = {2, 3, 4}; // pH/NaOH, IPTG, cosecha
const int NUM_RELES_DOSIFICACION = 3;
const unsigned long FLOW_TIMEOUT_MS = 5000;

// Indexados 1..6 (mismo número que usa RELE:n en los comandos); la
// posición 0 no se usa. encendidoDesde[n]==0 significa "relé apagado".
unsigned long releEncendidoDesde[7]   = {0, 0, 0, 0, 0, 0, 0};
unsigned long pulsosAlEncenderRele[7] = {0, 0, 0, 0, 0, 0, 0};
bool releAvisoFlujoEnviado[7]         = {false, false, false, false, false, false, false};

// ================= TEMPORIZACIÓN NO BLOQUEANTE =================
unsigned long ultimoEnvio = 0;
const unsigned long INTERVALO_ENVIO_MS = 1000;

// ================= WATCHDOG DE SEGURIDAD =================
// Si no llega NINGÚN comando (ni siquiera un PING) en este tiempo, se
// asume que se perdió la conexión con la PC (crash de la app, cable
// desconectado, etc.) y se apagan todos los relés como fail-safe.
// Esto sustituye la protección física independiente que en el paper
// daba el controlador de temperatura PIDT1 (Inkbird), que regulaba el
// calentador sin depender del Arduino principal.
const unsigned long WATCHDOG_TIMEOUT_MS = 10000; // 10 s
unsigned long ultimoComandoRecibido = 0;
bool watchdogDisparado = false;

// Declaraciones adelantadas (buena práctica, evita sorpresas con el auto
// prototyping del IDE de Arduino cuando hay muchas funciones)
void cargarCalibracionEEPROM();
void guardarCalibracionEEPROM();
bool valoresIguales(float a, float b);
void procesarComando(String cmd);
void procesarComandoRele(String cmd);
void procesarComandoRaw();
void procesarComandoCalGet();
void procesarComandoCalPH(String cmd);
void procesarComandoCalOD(String cmd);
void procesarComandoCalTemp(String cmd);
void procesarComandoOdBlank();
void apagarTodosReles();
void chequearWatchdog();
void chequearFlujoBombas();
void procesarComandoFlow();
bool esReleDosificacion(int num);

void setup() {
  Serial.begin(9600);
  sensors.begin();
  sensors.setResolution(sensorDireccion, 10);

  for (int i = 0; i < NUM_RELES; i++) {
    // Se fija el nivel OFF (HIGH, por la polaridad activa-en-bajo del
    // módulo) ANTES de declarar el pin como OUTPUT. Así se evita el
    // parpadeo de "todo encendido" que había antes: al declarar un pin
    // como OUTPUT sin haber fijado su nivel primero, el AVR puede sacar
    // brevemente el valor por defecto (LOW), que con este módulo
    // significa relé energizado.
    digitalWrite(RELES[i], HIGH);
    pinMode(RELES[i], OUTPUT);
  }

  cargarCalibracionEEPROM();
  ultimoComandoRecibido = millis();

  // Sensor de flujo: entrada con pull-up interno (la mayoría de estos
  // sensores tipo turbina son de colector abierto) y una interrupción
  // por flanco de bajada que solo incrementa un contador -- se mantiene
  // deliberadamente mínima porque corre en contexto de interrupción.
  pinMode(PIN_FLOW, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_FLOW), isrFlujo, FALLING);

  Serial.println("Bioreactor iniciado - Filtros de Seguridad OK");
  Serial.println("Formato: TEMP,PH,OD600");
  Serial.println("Comandos: RELE:n,ON/OFF | RAW | CALGET | CAL:PH:s,i | CAL:OD:s,i | CAL:TEMP:offset | OD:BLANK | FLOW | PING");
  Serial.print("Watchdog: apaga reles si no hay comandos por ");
  Serial.print(WATCHDOG_TIMEOUT_MS / 1000);
  Serial.println(" s (enviar PING periodicamente desde la app)");
}

void loop() {
  // 1) Procesar TODOS los comandos pendientes en el buffer, sin bloquear.
  //    Antes solo se leía un comando por vuelta del loop y el loop tenía
  //    un delay(1000) fijo, así que un paro de emergencia o una calibración
  //    podían tardar hasta 1 s en aplicarse. Ahora se atienden de inmediato.
  while (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    // Cualquier línea recibida (válida o no) cuenta como señal de vida
    // de la conexión y resetea el watchdog.
    ultimoComandoRecibido = millis();
    if (watchdogDisparado) {
      watchdogDisparado = false;
      Serial.println("WATCHDOG:RECUPERADO");
    }
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

  // 3) Watchdog: revisa en cada vuelta si se perdió la conexión.
  chequearWatchdog();

  // 4) Vigilancia de bombas de dosificación sin flujo detectado.
  chequearFlujoBombas();
}

// ================= WATCHDOG =================

void chequearWatchdog() {
  unsigned long ahora = millis();
  if (ahora - ultimoComandoRecibido > WATCHDOG_TIMEOUT_MS) {
    apagarTodosReles();
    if (!watchdogDisparado) {
      watchdogDisparado = true;
      Serial.println("WATCHDOG:DISPARADO - reles apagados por perdida de comunicacion");
    }
  }
}

void apagarTodosReles() {
  for (int i = 0; i < NUM_RELES; i++) {
    escribirRele(RELES[i], false);
  }
  // Al apagar todo (paro de emergencia o watchdog), se limpia también el
  // seguimiento de flujo: ya no tiene sentido seguir contando "tiempo
  // encendido sin flujo" para relés que se acaban de apagar.
  for (int n = 1; n <= NUM_RELES; n++) {
    releEncendidoDesde[n] = 0;
    releAvisoFlujoEnviado[n] = false;
  }
}

bool esReleDosificacion(int num) {
  for (int i = 0; i < NUM_RELES_DOSIFICACION; i++) {
    if (RELES_DOSIFICACION[i] == num) return true;
  }
  return false;
}

// Revisa, en cada vuelta del loop, si alguna bomba de dosificación lleva
// encendida más tiempo del permitido sin que el sensor de flujo haya
// registrado ni un solo pulso nuevo desde que se encendió. No bloquea
// nada: solo imprime una advertencia una vez por cada vez que el relé se
// enciende (releAvisoFlujoEnviado evita spamear el mismo aviso cada
// vuelta del loop mientras el problema persiste).
void chequearFlujoBombas() {
  unsigned long ahora = millis();
  for (int i = 0; i < NUM_RELES_DOSIFICACION; i++) {
    int num = RELES_DOSIFICACION[i];
    if (releEncendidoDesde[num] == 0) continue; // relé apagado, nada que vigilar
    if (releAvisoFlujoEnviado[num]) continue;    // ya se avisó para este encendido

    if (ahora - releEncendidoDesde[num] > FLOW_TIMEOUT_MS) {
      noInterrupts();
      unsigned long pulsosActuales = pulsosFlujo;
      interrupts();

      if (pulsosActuales == pulsosAlEncenderRele[num]) {
        Serial.print("WARNING:BOMBA_SIN_FLUJO:RELE:");
        Serial.println(num);
        releAvisoFlujoEnviado[num] = true;
      }
    }
  }
}

void procesarComandoFlow() {
  noInterrupts();
  unsigned long pulsos = pulsosFlujo;
  interrupts();

  // Esto es volumen ACUMULADO desde que arrancó el Arduino, no un caudal
  // instantáneo (para eso habría que medir pulsos en una ventana de
  // tiempo, como se podría agregar después si hace falta). Útil para
  // saber "cuánto ha pasado en total" por esta línea.
  float litrosAcumulados = pulsos / FLOW_PULSOS_POR_LITRO;
  Serial.print("FLOW:PULSOS:");
  Serial.print(pulsos);
  Serial.print(",LITROS_ACUM:");
  Serial.println(litrosAcumulados, 4);
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

// Techo de seguridad para OD600: NO es un límite físico del cultivo (un
// cultivo denso puede superar 3.5 sin problema), es solo una defensa
// contra valores absurdos por ruido del sensor o una calibración corrupta
// (ver limpiar_calibracion_od.sql). Antes estaba en 3.5, exactamente el
// mismo valor que el eje Y fijo de la gráfica en Python, así que un
// culivo real acercándose a ese techo se veía idéntico a un error de
// calibración saturando el cálculo. Se sube el techo aquí y, del lado de
// Python, el eje Y ahora es dinámico (ver actualizar_grafica), así que
// ambos dejaron de estar acoplados por esta coincidencia numérica.
const float OD600_MAX_SEGURIDAD = 6.0;

float leerOD600() {
  float v = leerVoltajeOD();

  if (v < 0.05 || v > 4.95) return 0.0;

  // Sin blanco capturado todavía -> no se puede calcular OD600 real.
  if (od_v0 <= 0.0) return 0.0;

  float ratio = v / od_v0;
  if (ratio < 0.0001) ratio = 0.0001; // evita log(0) / valores negativos
  if (ratio > 10.0)   ratio = 10.0;   // por si el sensor lee mas luz que el blanco (ruido)

  float od = od_slope * (-log10(ratio)) + od_intercept;
  return constrain(od, 0.0, OD600_MAX_SEGURIDAD);
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
    EEPROM.get(EEPROM_OD_V0_ADDR, od_v0);
  } else {
    // Primera vez que corre este sketch en esta placa (o se subio una
    // version con un campo nuevo, como od_v0): guarda los valores por
    // defecto como punto de partida.
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
  EEPROM.put(EEPROM_OD_V0_ADDR, od_v0);
}

// Compara dos floats con una tolerancia pequeña. Se usa antes de escribir
// en EEPROM: la app Python resincroniza la calibración desde la base de
// datos cada vez que conecta (ver sincronizar_calibracion_inicial en
// controlfisicoV2.py), así que sin esto cada conexión dispara una
// escritura EEPROM aunque el valor sea idéntico al que ya estaba - un
// desgaste innecesario en un componente con vida útil limitada
// (~100,000 ciclos de escritura por celda).
bool valoresIguales(float a, float b) {
  return fabs(a - b) < 0.0000005;
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
  } else if (cmd == "OD:BLANK") {
    procesarComandoOdBlank();
  } else if (cmd == "FLOW") {
    procesarComandoFlow();
  } else if (cmd == "PING") {
    Serial.println("OK:PING");
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
  state.trim();

  bool on;
  if (state == "ON") {
    on = true;
  } else if (state == "OFF") {
    on = false;
  } else {
    // Antes, cualquier texto que no fuera exactamente "ON" se trataba en
    // silencio como OFF. Es un fallback seguro (apaga en vez de encender
    // ante datos corruptos), pero puede esconder un bug de comunicación
    // sin que nadie se entere. Ahora se reporta el error explícitamente.
    Serial.println("ERROR:RELE_ESTADO_INVALIDO");
    return;
  }

  if (num >= 1 && num <= NUM_RELES) {
    escribirRele(RELES[num - 1], on);

    // Seguimiento para la vigilancia de flujo (ver chequearFlujoBombas):
    // solo importa para las bombas de dosificación (pH/NaOH, IPTG,
    // cosecha), no para agitador/aireación/calefacción.
    if (esReleDosificacion(num)) {
      if (on) {
        noInterrupts();
        pulsosAlEncenderRele[num] = pulsosFlujo;
        interrupts();
        releEncendidoDesde[num] = millis();
        releAvisoFlujoEnviado[num] = false;
      } else {
        releEncendidoDesde[num] = 0;
        releAvisoFlujoEnviado[num] = false;
      }
    }
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

  Serial.print("BLANKOD:");
  Serial.println(od_v0, 4);

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
  float nuevo_slope     = resto.substring(0, comma).toFloat();
  float nuevo_intercept = resto.substring(comma + 1).toFloat();

  if (fabs(nuevo_slope) > SLOPE_SOSPECHOSO) {
    // Rechazo duro: se mantiene la calibración anterior, no se toca la
    // EEPROM. A diferencia del wizard en Python, aquí no hay forma de
    // "aplicar de todas formas" -- este slope nunca es físicamente
    // legítimo para este sensor.
    Serial.print("ERROR:CAL_PH_SLOPE_SOSPECHOSO:");
    Serial.println(nuevo_slope, 6);
    return;
  }

  if (!valoresIguales(nuevo_slope, ph_slope) || !valoresIguales(nuevo_intercept, ph_intercept)) {
    ph_slope     = nuevo_slope;
    ph_intercept = nuevo_intercept;
    guardarCalibracionEEPROM();
  }

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
  float nuevo_slope     = resto.substring(0, comma).toFloat();
  float nuevo_intercept = resto.substring(comma + 1).toFloat();

  if (fabs(nuevo_slope) > SLOPE_SOSPECHOSO) {
    Serial.print("ERROR:CAL_OD_SLOPE_SOSPECHOSO:");
    Serial.println(nuevo_slope, 6);
    return;
  }

  if (!valoresIguales(nuevo_slope, od_slope) || !valoresIguales(nuevo_intercept, od_intercept)) {
    od_slope     = nuevo_slope;
    od_intercept = nuevo_intercept;
    guardarCalibracionEEPROM();
  }

  Serial.print("OK:CAL:OD:");
  Serial.print(od_slope, 6);
  Serial.print(",");
  Serial.println(od_intercept, 6);
}

void procesarComandoCalTemp(String cmd) {
  String resto = cmd.substring(strlen("CAL:TEMP:"));
  float nuevo_offset = resto.toFloat();
  if (!valoresIguales(nuevo_offset, temp_offset)) {
    temp_offset = nuevo_offset;
    guardarCalibracionEEPROM();
  }

  Serial.print("OK:CAL:TEMP:");
  Serial.println(temp_offset, 4);
}

void procesarComandoOdBlank() {
  // Captura el voltaje actual del sensor OD como referencia "blanco"
  // (medio de cultivo sin inocular), igual que el paper hace con l0
  // al pasar de la etapa Ready -> Growing.
  od_v0 = leerVoltajeOD();
  guardarCalibracionEEPROM();

  Serial.print("OK:BLANKOD:");
  Serial.println(od_v0, 4);
}
