"""
Módulo de Lógica de Acceso Principal (Gatekeeper).

Este módulo actúa como el primer filtro de seguridad del sistema. Antes de evaluar
anomalías complejas (como retrasos o tiempos de estancia), necesitamos decidir
rápidamente si la puerta debe abrirse o no, basándonos puramente en el estado
físico y administrativo actual del usuario.
"""
from __future__ import annotations


def decidir_evento(usuario: dict | None) -> dict:
    """
    Regla rápida del MVP con punto mixto:
    - usuario inexistente -> denegar
    - usuario inactivo -> denegar
    - usuario bloqueado -> denegar
    - estado FUERA -> ENTRADA permitida
    - estado DENTRO -> SALIDA permitida
    """
    # 1. Validación de existencia (Fail-fast)
    # Si el UID no cruza con ningún registro, bloqueamos inmediatamente.
    if usuario is None:
        return {
            "permitido": False,
            "modo_evento": "ENTRADA",
            "resultado": "DENEGADO",
            "motivo_codigo": "RFID_NO_REGISTRADO",
            "estado_anterior": None,
            "estado_nuevo": None,
            "detalle": "UID no encontrado en la base de datos",
        }

    # 2. Validación de estado administrativo
    # Si el usuario ha sido dado de baja lógica en el sistema, bloqueamos.
    if not usuario["activo"]:
        return {
            "permitido": False,
            "modo_evento": "ENTRADA",
            "resultado": "DENEGADO",
            "motivo_codigo": "RFID_NO_REGISTRADO",
            "estado_anterior": usuario["estado_actual"],
            "estado_nuevo": usuario["estado_actual"],
            "detalle": "Usuario inactivo",
        }

    estado_actual = usuario["estado_actual"]

    # 3. Validación de restricciones disciplinarias / bloqueos
    # Si el usuario está bloqueado por mora, sanción, o credencial robada, bloqueamos.
    if estado_actual == "BLOQUEADO":
        return {
            "permitido": False,
            "modo_evento": "ENTRADA",
            "resultado": "DENEGADO",
            "motivo_codigo": "RFID_NO_REGISTRADO",
            "estado_anterior": estado_actual,
            "estado_nuevo": estado_actual,
            "detalle": "Usuario bloqueado",
        }

    # 4. Lógica de inferencia de movimiento (Punto Mixto)
    # Si el sistema sabe que el usuario está físicamente afuera, lógicamente
    # un toque de la tarjeta en este punto mixto es un intento de entrada.
    if estado_actual == "FUERA":
        return {
            "permitido": True,
            "modo_evento": "ENTRADA",
            "resultado": "PERMITIDO",
            "motivo_codigo": "ENTRADA_VALIDA",
            "estado_anterior": "FUERA",
            "estado_nuevo": "DENTRO",
            "detalle": "Entrada autorizada",
        }

    # Por el contrario, si ya está físicamente adentro, el toque de la
    # tarjeta se interpreta como un intento de salida.
    if estado_actual == "DENTRO":
        return {
            "permitido": True,
            "modo_evento": "SALIDA",
            "resultado": "PERMITIDO",
            "motivo_codigo": "SALIDA_VALIDA",
            "estado_anterior": "DENTRO",
            "estado_nuevo": "FUERA",
            "detalle": "Salida autorizada",
        }

    # 5. Red de seguridad (Fallback)
    # Atrapa cualquier estado inconsistente en la base de datos que no hayamos
    # contemplado (por ejemplo, si alguien inserta un estado 'EN_SALA_DE_ESPERA').
    return {
        "permitido": False,
        "modo_evento": "ENTRADA",
        "resultado": "DENEGADO",
        "motivo_codigo": "RFID_NO_REGISTRADO",
        "estado_anterior": estado_actual,
        "estado_nuevo": estado_actual,
        "detalle": f"Estado no manejado: {estado_actual}",
    }