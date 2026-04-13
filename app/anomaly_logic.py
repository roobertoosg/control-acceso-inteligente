from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any


VENTANA_ENTRADA_ANTICIPADA_MIN = 20
TOLERANCIA_TARDE_MIN = 20
TARDE_FUERTE_MIN = 45

SALIDA_RAPIDA_FUERTE_MIN = 50
SALIDA_RAPIDA_MEDIA_MIN = 80
REINGRESO_RAPIDO_MIN = 15
MOVIMIENTOS_EXCESIVOS_DIA = 4

HORA_EXTREMA_INICIO = time(6, 30)
HORA_EXTREMA_FIN = time(22, 15)


@dataclass
class AnomalyCandidate:
    codigo: str
    score: int
    detalle: str


def _combine(fecha: datetime, hora: time) -> datetime:
    return fecha.replace(
        hour=hora.hour,
        minute=hora.minute,
        second=hora.second,
        microsecond=hora.microsecond,
    )


def _horarios_del_dia(horarios: list[dict], dia_semana: int) -> list[dict]:
    return sorted(
        [
            h for h in horarios
            if int(h["dia_semana"]) == int(dia_semana) and bool(h.get("activo", True))
        ],
        key=lambda x: x["hora_inicio"],
    )


def _add_candidate(candidatos: list[AnomalyCandidate], codigo: str, score: int, detalle: str) -> None:
    candidatos.append(AnomalyCandidate(codigo=codigo, score=score, detalle=detalle))


def _pick_strongest(candidatos: list[AnomalyCandidate]) -> AnomalyCandidate | None:
    if not candidatos:
        return None
    return max(candidatos, key=lambda x: x.score)


def _evaluar_horario_extremo(event_dt: datetime, candidatos: list[AnomalyCandidate]) -> None:
    hora_actual = event_dt.time()
    if hora_actual < HORA_EXTREMA_INICIO or hora_actual > HORA_EXTREMA_FIN:
        _add_candidate(
            candidatos,
            "HORARIO_EXTREMO",
            80,
            f"Acceso en horario extremo: {hora_actual.strftime('%H:%M')}",
        )


def _evaluar_dia(event_dt: datetime, bloques_dia: list[dict], candidatos: list[AnomalyCandidate]) -> None:
    dia_semana = event_dt.isoweekday()

    if dia_semana == 7:
        _add_candidate(
            candidatos,
            "ACCESO_EN_DOMINGO",
            90,
            "Acceso registrado en domingo",
        )
        return

    if not bloques_dia:
        _add_candidate(
            candidatos,
            "DIA_NO_HABITUAL",
            70,
            "El usuario no tiene clases programadas este día",
        )


def _evaluar_entrada_vs_bloques(
    event_dt: datetime,
    bloques_dia: list[dict],
    candidatos: list[AnomalyCandidate],
) -> None:
    if not bloques_dia:
        return

    ahora = event_dt
    hora_actual = ahora.time()

    # Entrada alineada a algún inicio de clase
    for bloque in bloques_dia:
        inicio = _combine(ahora, bloque["hora_inicio"])
        fin = _combine(ahora, bloque["hora_fin"])
        delta_inicio_min = (ahora - inicio).total_seconds() / 60

        # Dentro del bloque, pero llegó tarde
        if inicio <= ahora <= fin:
            if TOLERANCIA_TARDE_MIN < delta_inicio_min <= TARDE_FUERTE_MIN:
                _add_candidate(
                    candidatos,
                    "LLEGADA_TARDE",
                    30,
                    f"Llegada {int(delta_inicio_min)} min tarde respecto a {bloque['hora_inicio'].strftime('%H:%M')}",
                )
                return

            if delta_inicio_min > TARDE_FUERTE_MIN:
                _add_candidate(
                    candidatos,
                    "LLEGADA_TARDE",
                    65,
                    f"Llegada muy tarde: {int(delta_inicio_min)} min después del inicio del bloque {bloque['hora_inicio'].strftime('%H:%M')}",
                )
                return

            # Llegada normal
            if delta_inicio_min >= -VENTANA_ENTRADA_ANTICIPADA_MIN:
                return

        # Cerca del inicio: normal
        ventana_inicio = inicio - timedelta(minutes=VENTANA_ENTRADA_ANTICIPADA_MIN)
        ventana_fin = inicio + timedelta(minutes=TOLERANCIA_TARDE_MIN)
        if ventana_inicio <= ahora <= ventana_fin:
            return

    # Si no encajó en ningún bloque del día
    _add_candidate(
        candidatos,
        "HORARIO_FUERA_DE_BLOQUE",
        75,
        f"Entrada a las {hora_actual.strftime('%H:%M')} fuera de los bloques programados",
    )


def _evaluar_reingreso_rapido(db: Any, id_usuario: int, event_dt: datetime, candidatos: list[AnomalyCandidate]) -> None:
    ultima_salida = db.get_ultima_salida_valida(id_usuario)
    if not ultima_salida:
        return

    fecha_salida = ultima_salida["fecha_hora"]
    delta_min = (event_dt - fecha_salida).total_seconds() / 60

    if 0 <= delta_min <= REINGRESO_RAPIDO_MIN:
        _add_candidate(
            candidatos,
            "REINGRESO_RAPIDO",
            60,
            f"Reingreso {int(delta_min)} min después de la última salida",
        )


def _evaluar_salida_rapida(db: Any, id_usuario: int, event_dt: datetime, candidatos: list[AnomalyCandidate]) -> None:
    ultima_entrada = db.get_ultima_entrada_valida(id_usuario)
    if not ultima_entrada:
        return

    fecha_entrada = ultima_entrada["fecha_hora"]
    permanencia_min = (event_dt - fecha_entrada).total_seconds() / 60

    if permanencia_min < 0:
        return

    if permanencia_min < SALIDA_RAPIDA_FUERTE_MIN:
        _add_candidate(
            candidatos,
            "SALIDA_DEMASIADO_RAPIDA",
            85,
            f"Salida tras solo {int(permanencia_min)} min desde la entrada",
        )
        return

    if permanencia_min < SALIDA_RAPIDA_MEDIA_MIN:
        _add_candidate(
            candidatos,
            "SALIDA_DEMASIADO_RAPIDA",
            60,
            f"Permanencia corta de {int(permanencia_min)} min",
        )


def _evaluar_movimientos_excesivos(
    db: Any,
    id_usuario: int,
    event_dt: datetime,
    candidatos: list[AnomalyCandidate],
) -> None:
    total_dia = db.count_movimientos_usuario_dia(id_usuario, event_dt)

    # +1 porque aún no insertamos el evento actual
    if (total_dia + 1) > MOVIMIENTOS_EXCESIVOS_DIA:
        _add_candidate(
            candidatos,
            "MOVIMIENTOS_EXCESIVOS",
            65,
            f"Se registrarían {total_dia + 1} movimientos en el mismo día",
        )


def evaluar_anomalia_evento_completado(
    db: Any,
    usuario: dict,
    decision: dict,
    event_dt: datetime | None = None,
) -> dict:
    """
    Evalúa anomalías SOLO para eventos permitidos y completados (paso detectado).
    Devuelve el motivo final y score.
    """
    if event_dt is None:
        event_dt = datetime.now()

    id_usuario = usuario["id_usuario"]
    horarios = db.get_horarios_usuario(id_usuario)
    bloques_dia = _horarios_del_dia(horarios, event_dt.isoweekday())

    candidatos: list[AnomalyCandidate] = []

    _evaluar_horario_extremo(event_dt, candidatos)
    _evaluar_dia(event_dt, bloques_dia, candidatos)

    if decision["modo_evento"] == "ENTRADA":
        _evaluar_entrada_vs_bloques(event_dt, bloques_dia, candidatos)
        _evaluar_reingreso_rapido(db, id_usuario, event_dt, candidatos)

    elif decision["modo_evento"] == "SALIDA":
        _evaluar_salida_rapida(db, id_usuario, event_dt, candidatos)

    _evaluar_movimientos_excesivos(db, id_usuario, event_dt, candidatos)

    ganadora = _pick_strongest(candidatos)

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