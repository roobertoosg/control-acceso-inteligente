"""
Configuración del Entorno.

Centraliza todas las variables de entorno (cargadas desde el archivo .env).
Proporciona valores por defecto seguros para facilitar el desarrollo local.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SERIAL_PORT = os.getenv("SERIAL_PORT", "COM3")
    SERIAL_BAUDRATE = int(os.getenv("SERIAL_BAUDRATE", "9600"))
    SERIAL_TIMEOUT = float(os.getenv("SERIAL_TIMEOUT", "1"))
    PASO_TIMEOUT = int(os.getenv("PASO_TIMEOUT", "10"))

    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "control_acceso_inteligente")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

    PUNTO_ACCESO = os.getenv("PUNTO_ACCESO", "Acceso Principal")

    # --- NUEVOS LÍMITES DEL ALCOHOLÍMETRO ---
    ALCOHOL_MAX_PERMITIDO = int(os.getenv("ALCOHOL_MAX_PERMITIDO", "400"))
    ALCOHOL_ADVERTENCIA = int(os.getenv("ALCOHOL_ADVERTENCIA", "300"))

    # --- NUEVOS LÍMITES TEMPERATURA (MLX90614) ---
    TEMP_MIN_VALIDA = 34.0    # Menos de esto es mala posición (aire frío)
    TEMP_MAX_NORMAL = 37.4    # Rango saludable
    TEMP_FIEBRE = 38.0        # Bloqueo inmediato