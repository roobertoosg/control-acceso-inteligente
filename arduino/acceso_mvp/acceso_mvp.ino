#include <Servo.h>
#include <SoftwareSerial.h>

Servo barrera;

// -------------------------
// Pines
// -------------------------
const int PIN_SERVO      = 9;
const int PIN_SENSOR_IR  = 7;
const int PIN_LED_VERDE  = 2;
const int PIN_LED_ROJO   = 3;
const int PIN_BUZZER     = 4;

// RDM6300
const int PIN_RDM_RX     = 10;   // Arduino RX <- TX del RDM6300
const int PIN_RDM_TX     = 11;   // No se usa realmente, pero ponlo

SoftwareSerial rdmSerial(PIN_RDM_RX, PIN_RDM_TX);

// -------------------------
// Configuración del sensor
// -------------------------
const bool SENSOR_ACTIVO_EN_LOW = true;

// -------------------------
// Posiciones del servo
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

// Antirrebote RFID
String ultimoUid = "";
unsigned long ultimoUidMs = 0;
const unsigned long UID_LOCK_MS = 1500;

String bufferSerial = "";
String bufferRFID = "";

// --------------------------------------------------
// Utilidades
// --------------------------------------------------
bool sensorDetectado() {
  int lectura = digitalRead(PIN_SENSOR_IR);
  return SENSOR_ACTIVO_EN_LOW ? (lectura == LOW) : (lectura == HIGH);
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

void beepCorto(int ms = 120) {
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

bool leerUidRDM(String &uid) {
  while (rdmSerial.available() > 0) {
    char c = (char)rdmSerial.read();

    if ((uint8_t)c == 0x02) {   // STX
      bufferRFID = "";
    }
    else if ((uint8_t)c == 0x03) { // ETX
      if (bufferRFID.length() >= 10) {
        uid = bufferRFID.substring(0, 10); // tomamos los 10 primeros hex
        uid.toUpperCase();
        bufferRFID = "";
        return true;
      }
      bufferRFID = "";
    }
    else if (isHexadecimalDigit(c)) {
      bufferRFID += c;
      if (bufferRFID.length() > 12) {
        bufferRFID.remove(0, bufferRFID.length() - 12);
      }
    }
  }
  return false;
}

bool esUidRepetidoReciente(const String &uid) {
  return (uid == ultimoUid) && ((millis() - ultimoUidMs) < UID_LOCK_MS);
}

// --------------------------------------------------
// Setup
// --------------------------------------------------
void setup() {
  Serial.begin(9600);
  rdmSerial.begin(9600);

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
  // 1) Leer comandos desde Python por USB serial
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

  // 2) Leer RFID desde RDM6300
  String uidLeido = "";
  if (leerUidRDM(uidLeido)) {
    if (!esUidRepetidoReciente(uidLeido)) {
      ultimoUid = uidLeido;
      ultimoUidMs = millis();
      Serial.print("EVENTO:RFID:");
      Serial.println(uidLeido);
    }
  }

  // 3) Detectar paso cuando el acceso está abierto
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