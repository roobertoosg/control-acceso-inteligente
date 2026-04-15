"""
Motor de Generación de Inasistencias (Batch Process).

Este script está diseñado para ejecutarse de forma asíncrona al final del día
(por ejemplo, vía un Cron Job). Su objetivo es consolidar todos los "eventos"
aislados de entrada y salida, convertirlos en "intervalos de presencia", y
compararlos contra los "bloques horarios programados" de los usuarios.

Reglas clave:
- Si el bloque de clase no está cubierto por un intervalo de presencia -> FALTA (TOTAL o PARCIAL).
- Si está cubierto, pero la llegada fue con un retraso superior al umbral -> RETARDO GRAVE.
- Permite reejecuciones idempotentes mediante el flag `--rehacer` (borra las previas del día).
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor

from app.config import Config


VENTANA_ANTICIPADA_MIN = 20
RETARDO_GRAVE_MIN = 45


@dataclass
class Intervalo:
    """
    Representa un periodo continuo de tiempo en el que sabemos con certeza que
    el usuario estuvo dentro de las instalaciones (desde una ENTRADA hasta su SALIDA).
    """
    inicio: datetime
    fin: datetime


def get_connection():
    return psycopg2.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        dbname=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        cursor_factory=RealDictCursor,
    )


def combinar(fecha: date, hora: time) -> datetime:
    return datetime.combine(fecha, hora)


def cargar_horarios(conn, fecha_obj: date) -> list[dict]:
    sql = """
        SELECT
            h.id_horario,
            h.id_usuario,
            h.dia_semana,
            h.hora_inicio,
            h.hora_fin,
            h.materia,
            h.activo,
            u.nombre,
            u.apellido_paterno,
            u.apellido_materno,
            u.matricula,
            u.uid_rfid
        FROM acceso.horarios_usuario h
        JOIN acceso.usuarios u
            ON u.id_usuario = h.id_usuario
        WHERE h.activo = TRUE
          AND u.activo = TRUE
          AND h.dia_semana = %s
        ORDER BY h.id_usuario, h.hora_inicio
    """
    with conn.cursor() as cur:
        cur.execute(sql, (fecha_obj.isoweekday(),))
        return cur.fetchall() or []


def cargar_eventos_dia(conn, fecha_obj: date) -> list[dict]:
    sql = """
        SELECT
            id_evento,
            id_usuario,
            fecha_hora,
            modo_evento,
            resultado,
            paso_detectado
        FROM acceso.eventos_acceso
        WHERE DATE(fecha_hora) = DATE(%s)
          AND resultado IN ('PERMITIDO', 'ANOMALIA')
          AND paso_detectado = TRUE
          AND modo_evento IN ('ENTRADA', 'SALIDA')
        ORDER BY id_usuario, fecha_hora, id_evento
    """
    with conn.cursor() as cur:
        cur.execute(sql, (fecha_obj,))
        return cur.fetchall() or []


def construir_intervalos(eventos: list[dict]) -> dict[int, list[Intervalo]]:
    """
    Convierte una lista plana de eventos (Entrada, Salida, Entrada...) en pares
    consolidados de `Intervalo` de tiempo. Cierra automáticamente los intervalos
    abiertos al final del día.
    """
    por_usuario = defaultdict(list)
    for e in eventos:
        por_usuario[e["id_usuario"]].append(e)

    intervalos: dict[int, list[Intervalo]] = {}

    for id_usuario, evs in por_usuario.items():
        evs = sorted(evs, key=lambda x: (x["fecha_hora"], x["id_evento"]))
        abiertos: list[Intervalo] = []
        entrada_abierta: datetime | None = None

        for e in evs:
            if e["modo_evento"] == "ENTRADA":
                entrada_abierta = e["fecha_hora"]

            elif e["modo_evento"] == "SALIDA" and entrada_abierta is not None:
                if e["fecha_hora"] > entrada_abierta:
                    abiertos.append(Intervalo(inicio=entrada_abierta, fin=e["fecha_hora"]))
                entrada_abierta = None

        # Si quedó abierta una entrada, cerramos al final del día
        if entrada_abierta is not None:
            fin_dia = entrada_abierta.replace(hour=23, minute=59, second=59, microsecond=0)
            abiertos.append(Intervalo(inicio=entrada_abierta, fin=fin_dia))

        intervalos[id_usuario] = abiertos

    return intervalos


def buscar_intervalo_que_cubre_bloque(intervalos: list[Intervalo], bloque_inicio: datetime, bloque_fin: datetime) -> Intervalo | None:
    """
    Verifica si algún intervalo de presencia física del usuario se solapa
    y cubre el horario oficial del bloque de la materia.
    """
    for it in intervalos:
        if it.fin > bloque_inicio and it.inicio < bloque_fin:
            return it
    return None


def borrar_inasistencias_automaticas_fecha(conn, fecha_obj: date) -> None:
    sql = """
        DELETE FROM acceso.inasistencias
        WHERE fecha = %s
          AND detectada_automaticamente = TRUE
    """
    with conn.cursor() as cur:
        cur.execute(sql, (fecha_obj,))


def existe_inasistencia(conn, id_usuario: int, fecha_obj: date, hora_inicio: time, hora_fin: time, tipo: str) -> bool:
    sql = """
        SELECT 1
        FROM acceso.inasistencias
        WHERE id_usuario = %s
          AND fecha = %s
          AND hora_inicio = %s
          AND hora_fin = %s
          AND tipo = %s
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(sql, (id_usuario, fecha_obj, hora_inicio, hora_fin, tipo))
        return cur.fetchone() is not None


def insertar_inasistencia(
    conn,
    id_usuario: int,
    fecha_obj: date,
    dia_semana: int,
    hora_inicio: time,
    hora_fin: time,
    tipo: str,
    detalle: str,
) -> None:
    if existe_inasistencia(conn, id_usuario, fecha_obj, hora_inicio, hora_fin, tipo):
        return

    sql = """
        INSERT INTO acceso.inasistencias (
            id_usuario,
            fecha,
            dia_semana,
            hora_inicio,
            hora_fin,
            tipo,
            detectada_automaticamente,
            detalle
        )
        VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                id_usuario,
                fecha_obj,
                dia_semana,
                hora_inicio,
                hora_fin,
                tipo,
                detalle,
            ),
        )


def procesar_inasistencias(fecha_obj: date, rehacer: bool = False) -> int:
    """
    Orquestador principal del proceso por lotes. Cruza horarios vs intervalos de
    presencia e inserta los registros de sanción/inasistencia pertinentes en la BD.
    """
    conn = get_connection()
    conn.autocommit = False

    try:
        horarios = cargar_horarios(conn, fecha_obj)
        eventos = cargar_eventos_dia(conn, fecha_obj)
        intervalos = construir_intervalos(eventos)

        if rehacer:
            borrar_inasistencias_automaticas_fecha(conn, fecha_obj)

        total_insertadas = 0
        dia_semana = fecha_obj.isoweekday()

        horarios_por_usuario = defaultdict(list)
        for h in horarios:
            horarios_por_usuario[h["id_usuario"]].append(h)

        for id_usuario, bloques in horarios_por_usuario.items():
            bloques = sorted(bloques, key=lambda x: x["hora_inicio"])
            intervalos_usuario = intervalos.get(id_usuario, [])

            tiene_presencia_dia = len(intervalos_usuario) > 0

            for bloque in bloques:
                inicio_bloque = combinar(fecha_obj, bloque["hora_inicio"])
                fin_bloque = combinar(fecha_obj, bloque["hora_fin"])

                intervalo = buscar_intervalo_que_cubre_bloque(
                    intervalos_usuario,
                    inicio_bloque,
                    fin_bloque,
                )

                if intervalo is None:
                    tipo = "PARCIAL" if tiene_presencia_dia else "TOTAL"
                    detalle = (
                        f"Bloque no cubierto entre {bloque['hora_inicio'].strftime('%H:%M')} y {bloque['hora_fin'].strftime('%H:%M')}"
                    )
                    insertar_inasistencia(
                        conn=conn,
                        id_usuario=id_usuario,
                        fecha_obj=fecha_obj,
                        dia_semana=dia_semana,
                        hora_inicio=bloque["hora_inicio"],
                        hora_fin=bloque["hora_fin"],
                        tipo=tipo,
                        detalle=detalle,
                    )
                    total_insertadas += 1
                    continue

                # Si sí hubo presencia, evaluamos retardo grave
                tolerancia_entrada = inicio_bloque + timedelta(minutes=RETARDO_GRAVE_MIN)

                if intervalo.inicio > tolerancia_entrada and intervalo.inicio < fin_bloque:
                    detalle = (
                        f"Retardo grave: ingreso a las {intervalo.inicio.strftime('%H:%M')} para bloque {bloque['hora_inicio'].strftime('%H:%M')} - {bloque['hora_fin'].strftime('%H:%M')}"
                    )
                    insertar_inasistencia(
                        conn=conn,
                        id_usuario=id_usuario,
                        fecha_obj=fecha_obj,
                        dia_semana=dia_semana,
                        hora_inicio=bloque["hora_inicio"],
                        hora_fin=bloque["hora_fin"],
                        tipo="RETARDO_GRAVE",
                        detalle=detalle,
                    )
                    total_insertadas += 1

        conn.commit()
        return total_insertadas

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Genera inasistencias automáticas a partir de horarios y accesos.")
    parser.add_argument(
        "--fecha",
        help="Fecha objetivo en formato YYYY-MM-DD. Por default usa hoy.",
        default=None,
    )
    parser.add_argument(
        "--rehacer",
        action="store_true",
        help="Borra inasistencias automáticas ya generadas para esa fecha y las recalcula.",
    )
    args = parser.parse_args()

    if args.fecha:
        fecha_obj = datetime.strptime(args.fecha, "%Y-%m-%d").date()
    else:
        fecha_obj = date.today()

    total = procesar_inasistencias(fecha_obj=fecha_obj, rehacer=args.rehacer)
    print(f"Inasistencias generadas para {fecha_obj}: {total}")


if __name__ == "__main__":
    main()