#include <Servo.h>

Servo barrera;

// -------------------------
// Pines
// -------------------------
const int PIN_SERVO      = 9;
const int PIN_SENSOR_IR  = 7;
const int PIN_LED_VERDE  = 2;
const int PIN_LED_ROJO   = 3;
const int PIN_BUZZER     = 4;

// -------------------------
// Configuración del sensor
// Cambia a false si tu sensor se activa en HIGH
// -------------------------
const bool SENSOR_ACTIVO_EN_LOW = true;

// -------------------------
// Posiciones del servo
// Ajusta según tu maqueta
// -------------------------
const int POS_CERRADO = 0;
const int POS_ABIERTO = 90;

// -------------------------
// Estado interno
// -------------------------
bool accesoAbierto = false;
bool pasoYaReportado = false;
unsigned long ultimoCambioSensor = 0;
const unsigned long DEBOUNCE_MS = 250;

String bufferSerial = "";

// --------------------------------------------------
// Utilidades
// --------------------------------------------------
bool sensorDetectado() {
  int lectura = digitalRead(PIN_SENSOR_IR);
  if (SENSOR_ACTIVO_EN_LOW) {
    return lectura == LOW;
  } else {
    return lectura == HIGH;
  }
}

void apagarIndicadores() {
  digitalWrite(PIN_LED_VERDE, LOW);
  digitalWrite(PIN_LED_ROJO, LOW);
  digitalWrite(PIN_BUZZER, LOW);
}

void cerrarAcceso() {
  barrera.write(POS_CERRADO);
  accesoAbierto = false;
  pasoYaReportado = false;
}

void abrirAcceso() {
  barrera.write(POS_ABIERTO);
  accesoAbierto = true;
  pasoYaReportado = false;
}

void beepCorto(int ms = 150) {
  digitalWrite(PIN_BUZZER, HIGH);
  delay(ms);
  digitalWrite(PIN_BUZZER, LOW);
}

void permitirAcceso() {
  apagarIndicadores();
  digitalWrite(PIN_LED_VERDE, HIGH);
  abrirAcceso();
  Serial.println("ESTADO:ABIERTO");
}

void denegarAcceso() {
  cerrarAcceso();
  apagarIndicadores();
  digitalWrite(PIN_LED_ROJO, HIGH);
  beepCorto(200);
  Serial.println("ESTADO:DENEGADO");
}

void resetSeguro() {
  cerrarAcceso();
  apagarIndicadores();
  Serial.println("ESTADO:RESET");
}

void procesarComando(String cmd) {
  cmd.trim();

  if (cmd == "PING") {
    Serial.println("PONG");
  }
  else if (cmd == "CMD:PERMITIR") {
    permitirAcceso();
  }
  else if (cmd == "CMD:DENEGAR") {
    denegarAcceso();
  }
  else if (cmd == "CMD:CERRAR") {
    cerrarAcceso();
    apagarIndicadores();
    Serial.println("ESTADO:CERRADO");
  }
  else if (cmd == "CMD:VERDE") {
    apagarIndicadores();
    digitalWrite(PIN_LED_VERDE, HIGH);
    Serial.println("ESTADO:LED_VERDE");
  }
  else if (cmd == "CMD:ROJO") {
    apagarIndicadores();
    digitalWrite(PIN_LED_ROJO, HIGH);
    Serial.println("ESTADO:LED_ROJO");
  }
  else if (cmd == "CMD:BUZZER") {
    beepCorto(200);
    Serial.println("ESTADO:BUZZER");
  }
  else if (cmd == "CMD:RESET") {
    resetSeguro();
  }
  else {
    Serial.print("ERROR:CMD_DESCONOCIDO:");
    Serial.println(cmd);
  }
}

// --------------------------------------------------
// Setup
// --------------------------------------------------
void setup() {
  Serial.begin(9600);

  pinMode(PIN_SENSOR_IR, INPUT);
  pinMode(PIN_LED_VERDE, OUTPUT);
  pinMode(PIN_LED_ROJO, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  barrera.attach(PIN_SERVO);
  cerrarAcceso();
  apagarIndicadores();

  Serial.println("SISTEMA:LISTO");
}

// --------------------------------------------------
// Loop principal
// --------------------------------------------------
void loop() {
  // 1) Leer comandos seriales sin bloquear
  while (Serial.available() > 0) {
    char c = (char)Serial.read();

    if (c == '\n' || c == '\r') {
      if (bufferSerial.length() > 0) {
        procesarComando(bufferSerial);
        bufferSerial = "";
      }
    } else {
      bufferSerial += c;
    }
  }

  // 2) Detectar paso cuando el acceso está abierto
  bool hayPaso = sensorDetectado();

  if (accesoAbierto && !pasoYaReportado && hayPaso) {
    unsigned long ahora = millis();
    if (ahora - ultimoCambioSensor > DEBOUNCE_MS) {
      pasoYaReportado = true;
      ultimoCambioSensor = ahora;
      Serial.println("EVENTO:PASO");
    }
  }
}