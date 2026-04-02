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