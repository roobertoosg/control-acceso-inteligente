"""
Utilerías Compartidas.

Pequeñas funciones transversales que se utilizan en múltiples partes del proyecto.
"""
from datetime import datetime


def log(message: str) -> None:
    """Impresión estándar en consola con marca de tiempo integrada."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")