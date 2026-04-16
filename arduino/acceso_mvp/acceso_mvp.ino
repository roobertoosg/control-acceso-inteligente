#include <Servo.h>
#include <SoftwareSerial.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h> // LIBRERÍA DE LA PANTALLA

// Inicializamos la pantalla en la dirección 0x27, de 16 columnas y 2 filas
LiquidCrystal_I2C lcd(0x27, 16, 2); 

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
const int PIN_RDM_RX     = 10;
const int PIN_RDM_TX     = 11;

SoftwareSerial rdmSerial(PIN_RDM_RX, PIN_RDM_TX);

// -------------------------
// Configuración del sensor
// -------------------------
const bool SENSOR_ACTIVO_EN_LOW = true;
const int POS_CERRADO = 0;
const int POS_ABIERTO = 90;

// -------------------------
// Estado interno
// -------------------------
bool accesoAbierto = false;
bool pasoYaReportado = false;
unsigned long ultimoCambioSensor = 0;
const unsigned long DEBOUNCE_MS = 250;

String ultimoUid = "";
unsigned long ultimoUidMs = 0;
const unsigned long UID_LOCK_MS = 5000; 
const unsigned long TIEMPO_COOLDOWN_MS = 5000; 
unsigned long finSoploMs = 0; 

// --- VARIABLES SALUD ---
const int PIN_MQ3 = A0;
bool esperandoSoplo = false;
unsigned long inicioSoploMs = 0;
const unsigned long TIEMPO_SOPLO_MS = 10000; 

int maxAlcoholDetectado = 0;
float maxTempDetectada = 0.0;
// ----------------------------------------

String bufferSerial = "";
String bufferRFID = "";

// --------------------------------------------------
// Utilidades de Pantalla LCD
// --------------------------------------------------
void mostrarMensajeLCD(String linea1, String linea2) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(linea1);
  lcd.setCursor(0, 1);
  lcd.print(linea2);
}

void mostrarPantallaEspera() {
  mostrarMensajeLCD(" SISTEMA LISTO ", "Acerque Tarjeta ");
}

// --------------------------------------------------
// Utilidades Físicas
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
  if (!barrera.attached()) {
    barrera.attach(PIN_SERVO); // Lo volvemos a conectar si estaba apagado
  }
  barrera.write(POS_CERRADO);
  delay(400); // Le damos 0.4 segundos físicos al motor para que baje la barrera
  barrera.detach(); // ¡EL TRUCO! Apagamos la señal del motor para que deje de temblar
  
  accesoAbierto = false;
  pasoYaReportado = false;
  mostrarPantallaEspera(); 
}

void abrirAcceso() {
  if (!barrera.attached()) {
    barrera.attach(PIN_SERVO); // Despertamos al motor
  }
  barrera.write(POS_ABIERTO); // Levantamos la barrera
  
  accesoAbierto = true;
  pasoYaReportado = false;
}

void beepCorto(int ms = 120) {
  digitalWrite(PIN_BUZZER, HIGH);
  delay(ms);
  digitalWrite(PIN_BUZZER, LOW);
}

void permitirAcceso(String mensajeInferior) {
  apagarIndicadores();
  digitalWrite(PIN_LED_VERDE, HIGH);
  mostrarMensajeLCD("ACCESO PERMITIDO", mensajeInferior);
  abrirAcceso();
  Serial.println("ESTADO:ABIERTO");
}

void denegarAcceso(String razon) {
  cerrarAcceso();
  apagarIndicadores();
  digitalWrite(PIN_LED_ROJO, HIGH);
  
  // Centramos el texto de denegado y mostramos la razón exacta
  mostrarMensajeLCD("ACCESO DENEGADO!", razon);
  
  beepCorto(200);
  delay(2500); // Le damos 2.5 segundos al usuario para leer su castigo
  mostrarPantallaEspera();
  Serial.println("ESTADO:DENEGADO");
}

void procesarComando(String cmd) {
  cmd.trim();

  if (cmd == "PING") {
    Serial.println("PONG");
  }
  else if (cmd.startsWith("CMD:PERMITIR")) {
    // Leemos qué tipo de acceso es
    if (cmd.indexOf("ENTRADA") > 0) permitirAcceso(" Bienvenido(a)!");
    else if (cmd.indexOf("SALIDA") > 0) permitirAcceso(" Hasta pronto! ");
    else permitirAcceso("   Adelante ->  ");
  }
  else if (cmd.startsWith("CMD:DENEGAR")) {
    // Leemos el apellido del castigo para la pantalla LCD (Máximo 16 letras por renglón)
    String razon = " Consulte Admin "; // Razón por defecto
    
    if (cmd.indexOf("ALCOHOL") > 0) razon = "Alcohol Detectad";
    else if (cmd.indexOf("FIEBRE") > 0) razon = "   Temp. Alta   ";
    else if (cmd.indexOf("MALATEMP") > 0) razon = "  Mala Lectura  ";
    else if (cmd.indexOf("NO_REG") > 0) razon = " No Registrado  ";
    else if (cmd.indexOf("HORARIO") > 0) razon = "Fuera de Horario";
    
    denegarAcceso(razon);
  }
  else if (cmd == "CMD:CERRAR") {
    cerrarAcceso();
    apagarIndicadores();
    Serial.println("ESTADO:CERRADO");
  }
  else if (cmd == "CMD:SOPLAR") {
    esperandoSoplo = true;
    maxAlcoholDetectado = 0;
    maxTempDetectada = 0.0; 
    inicioSoploMs = millis();
    mostrarMensajeLCD("SOPLE Y ACERQUE", " SU FRENTE: 10s ");
    Serial.println("ESTADO:MUESTREANDO");
  }

  else if (cmd == "CMD:VERDE") {
    apagarIndicadores();
    digitalWrite(PIN_LED_VERDE, HIGH);
  }
  else if (cmd == "CMD:ROJO") {
    apagarIndicadores();
    digitalWrite(PIN_LED_ROJO, HIGH);
  }
  else if (cmd == "CMD:BUZZER") {
    beepCorto(200);
  }
}

bool leerUidRDM(String &uid) {
  while (rdmSerial.available() > 0) {
    char c = (char)rdmSerial.read();
    if ((uint8_t)c == 0x02) { bufferRFID = ""; }
    else if ((uint8_t)c == 0x03) {
      if (bufferRFID.length() >= 10) {
        uid = bufferRFID.substring(0, 10);
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

void setup() {
  Serial.begin(9600);
  rdmSerial.begin(9600);
  
  // Encendemos la pantalla LCD
  lcd.init();
  lcd.backlight();
  mostrarMensajeLCD(" INICIANDO... ", " Control Acceso ");
  delay(1000);
  
  pinMode(PIN_SENSOR_IR, INPUT);
  pinMode(PIN_LED_VERDE, OUTPUT);
  pinMode(PIN_LED_ROJO, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  
  barrera.attach(PIN_SERVO);
  cerrarAcceso(); // Aquí llama a mostrarPantallaEspera()
  apagarIndicadores();

  Serial.println("SISTEMA:LISTO");
}

void loop() {
  // 1) Leer comandos
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

  // 2) Leer RFID
  String uidLeido = "";
  if (!esperandoSoplo && (millis() - finSoploMs > TIEMPO_COOLDOWN_MS) && leerUidRDM(uidLeido)) {
    if (!esUidRepetidoReciente(uidLeido)) {
      ultimoUid = uidLeido;
      ultimoUidMs = millis();
      mostrarMensajeLCD("TARJETA LEIDA", "Analizando...");
      Serial.print("EVENTO:RFID:");
      Serial.println(uidLeido);
      beepCorto(50);
    }
  }

  // 3) Fase de Salud (10 Segundos)
  if (esperandoSoplo) {
    int lecturaAlc = analogRead(PIN_MQ3);
    if (lecturaAlc > maxAlcoholDetectado) { maxAlcoholDetectado = lecturaAlc; }

    float lecturaTemp = 36.5; // MOCK DE TEMPERATURA
    if (lecturaTemp > maxTempDetectada) { maxTempDetectada = lecturaTemp; }
    
    // Contador regresivo en la pantalla (Opcional pero se ve muy pro)
    int segundosRestantes = 10 - ((millis() - inicioSoploMs) / 1000);
    lcd.setCursor(14, 1);
    if (segundosRestantes < 10) lcd.print(" ");
    lcd.print(segundosRestantes);

    if (millis() - inicioSoploMs >= TIEMPO_SOPLO_MS) {
      esperandoSoplo = false;
      beepCorto(150);
      mostrarMensajeLCD(" PROCESANDO... ", "Por favor espere");
      
      Serial.print("EVENTO:ALCOHOL:");
      Serial.println(maxAlcoholDetectado);
      Serial.print("EVENTO:TEMP:");
      Serial.println(maxTempDetectada);

      while (rdmSerial.available() > 0) { rdmSerial.read(); }
      bufferRFID = "";
      
      finSoploMs = millis(); 
      ultimoUidMs = millis(); 
    }
  }

  // 4) Sensor de Paso
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