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

    return {
        "permitido": False,
        "modo_evento": "ENTRADA",
        "resultado": "DENEGADO",
        "motivo_codigo": "RFID_NO_REGISTRADO",
        "estado_anterior": estado_actual,
        "estado_nuevo": estado_actual,
        "detalle": f"Estado no manejado: {estado_actual}",
    }