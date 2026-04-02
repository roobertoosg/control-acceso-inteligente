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