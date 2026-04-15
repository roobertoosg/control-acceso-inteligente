from __future__ import annotations

import psycopg2
from psycopg2.extras import RealDictCursor


class Database:
    
    def __init__(self, host: str, port: int, dbname: str, user: str, password: str):
        self.conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            cursor_factory=RealDictCursor,
        )
        self.conn.autocommit = False

    def close(self) -> None:
        if self.conn:
            self.conn.close()

    def get_usuario_by_uid(self, uid_rfid: str) -> dict | None:
        sql = """
            SELECT
                id_usuario,
                nombre,
                apellido_paterno,
                apellido_materno,
                matricula,
                uid_rfid,
                estado_actual,
                activo
            FROM acceso.usuarios
            WHERE uid_rfid = %s
            LIMIT 1
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (uid_rfid,))
            return cur.fetchone()

    def get_punto_acceso(self, nombre_punto: str) -> dict:
        sql = """
            SELECT id_punto, nombre, tipo_punto
            FROM acceso.puntos_acceso
            WHERE nombre = %s
            LIMIT 1
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (nombre_punto,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"No existe el punto de acceso: {nombre_punto}")
            return row

    def get_motivo_by_codigo(self, codigo: str) -> dict:
        sql = """
            SELECT id_motivo, codigo, descripcion
            FROM acceso.motivos_evento
            WHERE codigo = %s
            LIMIT 1
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (codigo,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"No existe el motivo: {codigo}")
            return row

    def insert_evento(
        self,
        id_usuario: int | None,
        uid_rfid_leido: str,
        id_punto: int,
        modo_evento: str,
        resultado: str,
        id_motivo: int,
        estado_anterior: str | None,
        estado_nuevo: str | None,
        paso_detectado: bool,
        servo_activado: bool,
        anomalia_score: int,
        detalle: str | None = None,
    ) -> int:
        sql = """
            INSERT INTO acceso.eventos_acceso (
                id_usuario,
                uid_rfid_leido,
                id_punto,
                modo_evento,
                resultado,
                id_motivo,
                estado_anterior,
                estado_nuevo,
                paso_detectado,
                servo_activado,
                anomalia_score,
                detalle
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            RETURNING id_evento
        """
        with self.conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    id_usuario,
                    uid_rfid_leido,
                    id_punto,
                    modo_evento,
                    resultado,
                    id_motivo,
                    estado_anterior,
                    estado_nuevo,
                    paso_detectado,
                    servo_activado,
                    anomalia_score,
                    detalle,
                ),
            )
            row = cur.fetchone()
            return row["id_evento"]

    def update_estado_usuario(self, id_usuario: int, nuevo_estado: str) -> None:
        sql = """
            UPDATE acceso.usuarios
            SET estado_actual = %s
            WHERE id_usuario = %s
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (nuevo_estado, id_usuario))

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()
    def get_horarios_usuario(self, id_usuario: int) -> list[dict]:
        sql = """
            SELECT
                id_horario,
                id_usuario,
                dia_semana,
                hora_inicio,
                hora_fin,
                materia,
                activo
            FROM acceso.horarios_usuario
            WHERE id_usuario = %s
            ORDER BY dia_semana, hora_inicio
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (id_usuario,))
            return cur.fetchall() or []

    def get_ultima_entrada_valida(self, id_usuario: int, before_dt=None) -> dict | None:
        sql = """
            SELECT
                id_evento,
                id_usuario,
                fecha_hora,
                modo_evento,
                resultado,
                paso_detectado
            FROM acceso.eventos_acceso
            WHERE id_usuario = %s
              AND modo_evento = 'ENTRADA'
              AND paso_detectado = TRUE
              AND resultado IN ('PERMITIDO', 'ANOMALIA')
              AND (%s IS NULL OR fecha_hora < %s)
            ORDER BY fecha_hora DESC, id_evento DESC
            LIMIT 1
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (id_usuario, before_dt, before_dt))
            return cur.fetchone()

    def get_ultima_salida_valida(self, id_usuario: int, before_dt=None) -> dict | None:
        sql = """
            SELECT
                id_evento,
                id_usuario,
                fecha_hora,
                modo_evento,
                resultado,
                paso_detectado
            FROM acceso.eventos_acceso
            WHERE id_usuario = %s
              AND modo_evento = 'SALIDA'
              AND paso_detectado = TRUE
              AND resultado IN ('PERMITIDO', 'ANOMALIA')
              AND (%s IS NULL OR fecha_hora < %s)
            ORDER BY fecha_hora DESC, id_evento DESC
            LIMIT 1
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (id_usuario, before_dt, before_dt))
            return cur.fetchone()

    def count_movimientos_usuario_dia(self, id_usuario: int, fecha_ref) -> int:
        sql = """
            SELECT COUNT(*) AS total
            FROM acceso.eventos_acceso
            WHERE id_usuario = %s
              AND DATE(fecha_hora) = DATE(%s)
              AND resultado IN ('PERMITIDO', 'ANOMALIA', 'INCOMPLETO', 'DENEGADO')
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (id_usuario, fecha_ref))
            row = cur.fetchone()
            return int(row["total"] or 0)

    def count_denegados_recientes_por_uid(self, uid_rfid_leido: str, minutos: int, fecha_ref) -> int:
        sql = """
            SELECT COUNT(*) AS total
            FROM acceso.eventos_acceso
            WHERE uid_rfid_leido = %s
              AND resultado = 'DENEGADO'
              AND fecha_hora >= (%s - (%s || ' minutes')::interval)
              AND fecha_hora < %s
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (uid_rfid_leido, fecha_ref, minutos, fecha_ref))
            row = cur.fetchone()
            return int(row["total"] or 0)