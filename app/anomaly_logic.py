"""
Módulo de Lógica de Detección de Anomalías.

Este es el cerebro del sistema para identificar comportamientos inusuales. Su
responsabilidad es analizar un evento de acceso (ya sea permitido o denegado)
y, basándose en un conjunto de reglas de negocio, determinar si constituye una
anomalía.

El flujo general es:
1. Un evento de acceso ocurre (ej. una entrada permitida).
2. Se llama a la función orquestadora principal (ej. `evaluar_evento_permitido_completado`).
3. Esta función invoca una serie de evaluadores específicos (`_eval_*`).
4. Cada evaluador que detecta una irregularidad genera un `Candidato` con un `score`.
5. Al final, se elige el `Candidato` con el `score` más alto como la anomalía
   definitiva para ese evento.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

# --- Constantes de Reglas de Negocio ---
# Estos valores definen los umbrales para nuestras reglas de anomalías.
# Son el punto central para ajustar y calibrar el comportamiento del sistema
# según las observaciones del mundo real.

# Ventana de tiempo antes del inicio de un bloque en la que se permite entrar.
VENTANA_ANTICIPADA_MIN = 20
# Umbrales para considerar una llegada como "tarde" o "muy tarde".
TARDE_MEDIA_MIN = 20
TARDE_FUERTE_MIN = 45

# Umbrales para detectar una permanencia demasiado corta.
SALIDA_RAPIDA_FUERTE_MIN = 50
SALIDA_RAPIDA_MEDIA_MIN = 80

# Tiempo mínimo entre una salida y un reingreso para no ser considerado anómalo.
REINGRESO_RAPIDO_MIN = 15
# Número máximo de movimientos (entradas/salidas/intentos) en un día.
MOVIMIENTOS_EXCESIVOS_DIA = 4

# Umbrales para detectar una permanencia excesivamente larga en el recinto.
ESTANCIA_EXCESIVA_MEDIA_H = 7
ESTANCIA_EXCESIVA_FUERTE_H = 9

# Horas fuera de las cuales cualquier acceso se considera "extremo".
HORARIO_EXTREMO_INICIO = time(6, 30)
HORARIO_EXTREMO_FIN = time(22, 15)

# Parámetros para detectar reintentos de acceso denegados.
REINTENTOS_VENTANA_MIN = 5
REINTENTOS_UMBRAL = 3


@dataclass
class Candidato:
    """
    Representa una posible anomalía detectada.

    Durante la evaluación de un evento, pueden surgir varias anomalías candidatas.
    Al final del proceso, seleccionamos la "ganadora" basándonos en el `score`
    más alto, que representa la mayor severidad.
    """
    codigo: str
    score: int
    detalle: str


def _combinar(fecha: datetime, hora: time) -> datetime:
    """Helper para combinar un objeto date/datetime con un objeto time."""
    return fecha.replace(
        hour=hora.hour,
        minute=hora.minute,
        second=hora.second,
        microsecond=0,
    )


def _agregar(candidatos: list[Candidato], codigo: str, score: int, detalle: str) -> None:
    """Helper para añadir un nuevo candidato a la lista de anomalías potenciales."""
    candidatos.append(Candidato(codigo=codigo, score=score, detalle=detalle))


def _mejor(candidatos: list[Candidato]) -> Candidato | None:
    """Selecciona el candidato con el 'score' más alto de la lista."""
    if not candidatos:
        return None
    return max(candidatos, key=lambda c: c.score)


def _horarios_del_dia(horarios: list[dict], dia_semana: int) -> list[dict]:
    """Filtra y ordena los horarios de un usuario para un día de la semana específico."""
    return sorted(
        [
            h for h in horarios
            if bool(h.get("activo", True)) and int(h["dia_semana"]) == int(dia_semana)
        ],
        key=lambda x: x["hora_inicio"],
    )


def _eval_horario_extremo(event_dt: datetime, candidatos: list[Candidato]) -> None:
    """
    Evaluador: Horario Extremo.

    Verifica si el evento ocurre fuera del rango operativo general del recinto.
    """
    hora_actual = event_dt.time()
    if hora_actual < HORARIO_EXTREMO_INICIO or hora_actual > HORARIO_EXTREMO_FIN:
        _agregar(
            candidatos,
            "HORARIO_EXTREMO",
            80,
            f"Acceso en horario extremo: {hora_actual.strftime('%H:%M')}",
        )


def _eval_dia_y_programacion(
    event_dt: datetime,
    bloques_dia: list[dict],
    candidatos: list[Candidato],
) -> None:
    """
    Evaluador: Día no programado.

    Verifica si el acceso ocurre en un día inhábil (domingo) o en un día en el
    que el usuario no tiene ningún bloque de clases programado.
    """
    if event_dt.isoweekday() == 7:
        _agregar(
            candidatos,
            "ACCESO_EN_DOMINGO",
            90,
            "Acceso en domingo",
        )
        return

    if not bloques_dia:
        _agregar(
            candidatos,
            "SIN_CLASE_PROGRAMADA",
            70,
            "No hay bloques programados para este usuario en este día",
        )


def _eval_entrada_vs_bloques(
    event_dt: datetime,
    bloques_dia: list[dict],
    candidatos: list[Candidato],
) -> None:
    """
    Evaluador: Entrada vs. Bloques Horarios.

    Compara la hora de entrada con los bloques de clase del usuario. Detecta si:
    - La entrada ocurre fuera de cualquier bloque programado.
    - La entrada constituye una llegada tarde (media o fuerte).
    """
    if not bloques_dia:
        return

    ahora = event_dt

    for bloque in bloques_dia:
        inicio_dt = _combinar(ahora, bloque["hora_inicio"])
        fin_dt = _combinar(ahora, bloque["hora_fin"])

        # Dentro de ventana escolar del bloque
        if (inicio_dt - timedelta(minutes=VENTANA_ANTICIPADA_MIN)) <= ahora <= fin_dt:
            tardanza_min = (ahora - inicio_dt).total_seconds() / 60

            if TARDE_MEDIA_MIN < tardanza_min <= TARDE_FUERTE_MIN:
                _agregar(
                    candidatos,
                    "LLEGADA_TARDE",
                    30,
                    f"Llegada {int(tardanza_min)} min tarde al bloque {bloque['hora_inicio'].strftime('%H:%M')} - {bloque['hora_fin'].strftime('%H:%M')}",
                )
                return

            if tardanza_min > TARDE_FUERTE_MIN:
                _agregar(
                    candidatos,
                    "LLEGADA_TARDE",
                    65,
                    f"Llegada muy tarde: {int(tardanza_min)} min después del inicio del bloque {bloque['hora_inicio'].strftime('%H:%M')} - {bloque['hora_fin'].strftime('%H:%M')}",
                )
                return

            return

    _agregar(
        candidatos,
        "HORARIO_FUERA_DE_BLOQUE",
        75,
        f"Entrada fuera de bloque a las {ahora.strftime('%H:%M')}",
    )


def _eval_reingreso_rapido(
    db: Any,
    id_usuario: int,
    event_dt: datetime,
    candidatos: list[Candidato],
) -> None:
    """
    Evaluador: Reingreso Rápido.

    Detecta si un usuario vuelve a entrar muy poco tiempo después de haber salido.
    Esto podría indicar un olvido, pero también es un patrón a monitorear.
    """
    ultima_salida = db.get_ultima_salida_valida(id_usuario, before_dt=event_dt)
    if not ultima_salida:
        return

    fecha_salida = ultima_salida["fecha_hora"]
    delta_min = (event_dt - fecha_salida).total_seconds() / 60

    if 0 <= delta_min <= REINGRESO_RAPIDO_MIN:
        _agregar(
            candidatos,
            "REINGRESO_RAPIDO",
            60,
            f"Reingreso {int(delta_min)} min después de la última salida",
        )


def _eval_salida_rapida(
    db: Any,
    id_usuario: int,
    event_dt: datetime,
    candidatos: list[Candidato],
) -> None:
    """
    Evaluador: Salida Rápida.

    Detecta si un usuario sale muy poco tiempo después de haber entrado en el mismo día.
    Indica que su permanencia fue inusualmente corta.
    """
    ultima_entrada = db.get_ultima_entrada_valida(id_usuario, before_dt=event_dt)
    if not ultima_entrada:
        return

    fecha_entrada = ultima_entrada["fecha_hora"]

    if fecha_entrada.date() != event_dt.date():
        return

    permanencia_min = (event_dt - fecha_entrada).total_seconds() / 60
    if permanencia_min < 0:
        return

    if permanencia_min < SALIDA_RAPIDA_FUERTE_MIN:
        _agregar(
            candidatos,
            "SALIDA_DEMASIADO_RAPIDA",
            85,
            f"Salida tras solo {int(permanencia_min)} min desde la entrada",
        )
        return

    if permanencia_min < SALIDA_RAPIDA_MEDIA_MIN:
        _agregar(
            candidatos,
            "SALIDA_DEMASIADO_RAPIDA",
            60,
            f"Permanencia corta de {int(permanencia_min)} min",
        )


def _eval_estancia_excesiva(
    db: Any,
    id_usuario: int,
    event_dt: datetime,
    candidatos: list[Candidato],
) -> None:
    """
    Evaluador: Estancia Excesiva.

    Verifica si la permanencia de un usuario dentro del recinto supera los umbrales definidos.
    """
    ultima_entrada = db.get_ultima_entrada_valida(id_usuario, before_dt=event_dt)
    if not ultima_entrada:
        return

    fecha_entrada = ultima_entrada["fecha_hora"]

    if fecha_entrada.date() != event_dt.date():
        return

    horas = (event_dt - fecha_entrada).total_seconds() / 3600
    if horas < 0:
        return

    if horas > ESTANCIA_EXCESIVA_FUERTE_H:
        _agregar(
            candidatos,
            "ESTANCIA_EXCESIVA",
            75,
            f"Estancia excesiva de {horas:.2f} horas",
        )
        return

    if horas > ESTANCIA_EXCESIVA_MEDIA_H:
        _agregar(
            candidatos,
            "ESTANCIA_EXCESIVA",
            45,
            f"Estancia larga de {horas:.2f} horas",
        )


def _eval_movimientos_excesivos(
    db: Any,
    id_usuario: int,
    event_dt: datetime,
    candidatos: list[Candidato],
) -> None:
    """
    Evaluador: Movimientos Excesivos.

    Cuenta el número total de eventos (entradas, salidas, intentos) del usuario en el día.
    """
    total_dia = db.count_movimientos_usuario_dia(id_usuario, event_dt)
    if (total_dia + 1) > MOVIMIENTOS_EXCESIVOS_DIA:
        _agregar(
            candidatos,
            "MOVIMIENTOS_EXCESIVOS",
            65,
            f"Se registrarían {total_dia + 1} movimientos en el día",
        )


def evaluar_denegacion(
    db: Any,
    uid_rfid: str,
    usuario: dict | None,
    decision: dict,
    event_dt: datetime | None = None,
) -> dict:
    """
    Orquestador para eventos DENEGADOS.

    Su principal función es determinar si una simple denegación debe ser escalada
    a una anomalía. La regla principal aquí es detectar reintentos frecuentes, lo
    que podría indicar una tarjeta perdida/robada o un intento de forzar el acceso.
    """
    if event_dt is None:
        event_dt = datetime.now().astimezone()

    denegados_previos = db.count_denegados_recientes_por_uid(
        uid_rfid_leido=uid_rfid,
        minutos=REINTENTOS_VENTANA_MIN,
        fecha_ref=event_dt,
    )

    # +1 contando el evento actual
    if (denegados_previos + 1) >= REINTENTOS_UMBRAL:
        return {
            "es_anomalia": True,
            "resultado": "ANOMALIA",
            "motivo_codigo": "REINTENTOS_FRECUENTES",
            "anomalia_score": 60,
            "detalle_extra": f"Se detectaron {denegados_previos + 1} intentos denegados en menos de {REINTENTOS_VENTANA_MIN} minutos",
        }

    return {
        "es_anomalia": False,
        "resultado": "DENEGADO",
        "motivo_codigo": decision["motivo_codigo"],
        "anomalia_score": 0,
        "detalle_extra": "",
    }


def evaluar_evento_permitido_completado(
    db: Any,
    usuario: dict,
    decision: dict,
    event_dt: datetime | None = None,
) -> dict:
    """
    Orquestador principal para eventos PERMITIDOS y COMPLETADOS.

    Esta función se ejecuta después de que a un usuario se le ha permitido el
    acceso y ha pasado físicamente por el punto de control. Su trabajo es
    llamar a todos los evaluadores (`_eval_*`) relevantes para construir una
    lista de posibles anomalías y luego seleccionar la más severa.
    """
    if event_dt is None:
        event_dt = datetime.now().astimezone()


    id_usuario = usuario["id_usuario"]
    horarios = db.get_horarios_usuario(id_usuario)
    bloques_dia = _horarios_del_dia(horarios, event_dt.isoweekday())

    candidatos: list[Candidato] = []

    # --- Ejecución de todos los evaluadores aplicables ---
    _eval_horario_extremo(event_dt, candidatos)
    _eval_dia_y_programacion(event_dt, bloques_dia, candidatos)

    if decision["modo_evento"] == "ENTRADA":
        _eval_entrada_vs_bloques(event_dt, bloques_dia, candidatos)
        _eval_reingreso_rapido(db, id_usuario, event_dt, candidatos)

    elif decision["modo_evento"] == "SALIDA":
        _eval_salida_rapida(db, id_usuario, event_dt, candidatos)
        _eval_estancia_excesiva(db, id_usuario, event_dt, candidatos)

    _eval_movimientos_excesivos(db, id_usuario, event_dt, candidatos)

    # --- Selección del resultado final ---
    ganadora = _mejor(candidatos)

    if ganadora is None:
        return {
            "es_anomalia": False,
            "resultado": decision["resultado"],          # normalmente PERMITIDO
            "motivo_codigo": decision["motivo_codigo"],  # ENTRADA_VALIDA / SALIDA_VALIDA
            "anomalia_score": 0,
            "detalle_extra": "",
        }

    return {
        "es_anomalia": True,
        "resultado": "ANOMALIA",
        "motivo_codigo": ganadora.codigo,
        "anomalia_score": ganadora.score,
        "detalle_extra": ganadora.detalle,
    }
    