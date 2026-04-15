# 🎫 Control de Acceso Inteligente

Un sistema integral de control de acceso físico basado en RFID, diseñado para entornos educativos o corporativos. Este proyecto no solo gestiona la apertura de puertas (vía microcontroladores/Arduino), sino que incorpora un **motor de reglas de negocio** para detectar anomalías en tiempo real, calcular inasistencias por lotes, y visualizar métricas en un Dashboard analítico interactivo.

---

## 🚀 Características Principales

- **Lógica de Acceso Rápida (Gatekeeper):** Validación en milisegundos del estado del usuario (Activo, Bloqueado) y gestión de "Punto Mixto" (un solo lector infiere si es Entrada o Salida basándose en el estado actual del usuario).
- **Detección de Anomalías Avanzada:** Motor de reglas que detecta en tiempo real comportamientos inusuales como:
  - Accesos en días/horarios no programados.
  - Llegadas tarde y estancias excesivamente largas.
  - Reingresos o salidas inusualmente rápidas (posible uso indebido de tarjeta).
  - Movimientos excesivos en un mismo día.
  - Intentos de acceso denegados frecuentes.
- **Cálculo de Inasistencias Batch:** Proceso asíncrono que cruza los intervalos de presencia real del usuario contra sus bloques horarios escolares para dictaminar faltas totales, parciales o retardos graves.
- **Dashboard Interactivo:** Interfaz construida con Streamlit y Pandas para monitorear accesos, incidencias y asistencia en tiempo real.
- **Modo de Prueba / Consola:** Permite simular lecturas RFID directamente desde la terminal, facilitando el desarrollo sin necesidad del hardware conectado.

---

## 🏗️ Arquitectura del Sistema

El proyecto está construido en Python y se apoya en PostgreSQL para la persistencia.

- `app/main.py`: Orquestador principal. Levanta hilos paralelos para escuchar el puerto serial y la consola, e inyecta los eventos en una cola segura (Thread-Safe) para evitar condiciones de carrera.
- `app/access_logic.py`: Filtro primario que decide si se otorga acceso basándose en estado administrativo.
- `app/anomaly_logic.py`: Cerebro evaluador que otorga puntuaciones de riesgo (`anomalia_score`) basándose en patrones de uso.
- `app/generar_inasistencias.py`: Tarea programable (Cron Job) para calcular y registrar la asistencia diaria.
- `app/dashboard.py`: Aplicación web analítica de solo lectura.
- `app/serial_manager.py`: Puente de comunicación UART con el hardware físico (Arduino/ESP).
- `app/db.py`: Capa de acceso a datos pura (DAO) para aislar la lógica de negocio del SQL.

---

## 🛠️ Requisitos Previos

- **Python:** >= 3.9
- **Base de Datos:** PostgreSQL >= 13
- **Hardware (Opcional):** Arduino/ESP8266 con lector RFID RC522 y servomotor, conectado vía USB.

---

## ⚙️ Instalación y Configuración

### 1. Clonar el repositorio
```bash
git clone <URL_DEL_REPOSITORIO>
cd control-acceso-inteligente
```

### 2. Entorno Virtual y Dependencias
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configuración de Base de Datos
Asegúrate de tener un servidor PostgreSQL corriendo. Ejecuta los scripts ubicados en la carpeta `sql/` en el siguiente orden para crear el esquema, vistas y datos iniciales:
1. `01_schema.sql`
2. `02_views.sql`
3. `03_catalog_data.sql`
4. `04_sample_users_and_schedules.sql` (Opcional - Datos de prueba)
5. `05_demo_data.sql` (Opcional - Histórico para el dashboard)

### 4. Variables de Entorno
Crea un archivo `.env` en la raíz del proyecto basándote en este ejemplo:
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=control_acceso_inteligente
DB_USER=tu_usuario
DB_PASSWORD=tu_contraseña

SERIAL_PORT=COM3          # En Linux/Mac suele ser /dev/ttyUSB0
SERIAL_BAUDRATE=9600
SERIAL_TIMEOUT=1
PASO_TIMEOUT=10

PUNTO_ACCESO="Acceso Principal"
```

---

## 🖥️ Uso del Sistema

### 1. Iniciar el Orquestador Principal (Backend)
Este comando arranca el servicio de escucha (Serial y Consola). Te preguntará si deseas usar el hardware físico o si prefieres capturar los UID manualmente:
```bash
python -m app.main
```

### 2. Levantar el Dashboard (Frontend)
Para visualizar las métricas y los registros, ejecuta la aplicación de Streamlit en una nueva terminal:
```bash
streamlit run app/dashboard.py
```

### 3. Calcular Inasistencias (Batch Process)
Este comando suele configurarse en un Cron Job al final del día. Para probarlo manualmente:
```bash
# Calcula las inasistencias del día actual
python -m app.generar_inasistencias

# Calcula las inasistencias de un día específico borrando intentos previos
python -m app.generar_inasistencias --fecha "2023-10-25" --rehacer
```

---

## 👥 Equipo de Desarrollo
Desarrollado como solución tecnológica para el control de accesos inteligente y monitoreo de asistencia automatizado.