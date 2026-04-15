-- =========================================================
-- ARCHIVO DE ESQUEMA DE BASE DE DATOS
--
-- Contiene:
-- 1. Creación del esquema 'acceso'.
-- 2. Definición de todas las tablas.
-- 3. Funciones y Triggers.
-- 4. Creación de Índices para optimización.
--
-- Ejecución: Este script debe ser el primero en ejecutarse.
-- =========================================================

-- Nota: La creación de la base de datos se hace por fuera del script.
-- Conéctate a tu servidor PostgreSQL y ejecuta:
-- CREATE DATABASE control_acceso_inteligente WITH ENCODING = 'UTF8' TEMPLATE = template0;

CREATE SCHEMA IF NOT EXISTS acceso;

SET search_path TO acceso, public;

-- =========================================================
-- TABLA: usuarios
-- =========================================================
CREATE TABLE IF NOT EXISTS acceso.usuarios (
    id_usuario          BIGSERIAL PRIMARY KEY,
    nombre              VARCHAR(100) NOT NULL,
    apellido_paterno    VARCHAR(100),
    apellido_materno    VARCHAR(100),
    matricula           VARCHAR(30) UNIQUE,
    uid_rfid            VARCHAR(50) NOT NULL UNIQUE,
    estado_actual       VARCHAR(10) NOT NULL DEFAULT 'FUERA',
    activo              BOOLEAN NOT NULL DEFAULT TRUE,
    referencia_facial   TEXT,
    fecha_alta          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_usuarios_estado_actual
        CHECK (estado_actual IN ('FUERA', 'DENTRO', 'BLOQUEADO'))
);

-- =========================================================
-- TABLA: puntos_acceso
-- =========================================================
CREATE TABLE IF NOT EXISTS acceso.puntos_acceso (
    id_punto        BIGSERIAL PRIMARY KEY,
    nombre          VARCHAR(50) NOT NULL UNIQUE,
    tipo_punto      VARCHAR(10) NOT NULL,
    descripcion     VARCHAR(255),
    activo          BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT chk_puntos_tipo
        CHECK (tipo_punto IN ('ENTRADA', 'SALIDA', 'MIXTO'))
);

-- =========================================================
-- TABLA: motivos_evento
-- =========================================================
CREATE TABLE IF NOT EXISTS acceso.motivos_evento (
    id_motivo       SMALLSERIAL PRIMARY KEY,
    codigo          VARCHAR(50) NOT NULL UNIQUE,
    descripcion     VARCHAR(255) NOT NULL,
    es_anomalia     BOOLEAN NOT NULL DEFAULT FALSE,
    es_error        BOOLEAN NOT NULL DEFAULT FALSE,
    activo          BOOLEAN NOT NULL DEFAULT TRUE
);

-- =========================================================
-- TABLA: eventos_acceso
-- =========================================================
CREATE TABLE IF NOT EXISTS acceso.eventos_acceso (
    id_evento            BIGSERIAL PRIMARY KEY,
    id_usuario           BIGINT,
    uid_rfid_leido       VARCHAR(50) NOT NULL,
    id_punto             BIGINT NOT NULL,
    modo_evento          VARCHAR(10) NOT NULL,
    resultado            VARCHAR(12) NOT NULL,
    id_motivo            SMALLINT NOT NULL,
    estado_anterior      VARCHAR(10),
    estado_nuevo         VARCHAR(10),
    paso_detectado       BOOLEAN NOT NULL DEFAULT FALSE,
    servo_activado       BOOLEAN NOT NULL DEFAULT FALSE,
    coincidencia_facial  NUMERIC(5,2),
    evidencia_imagen     TEXT,
    anomalia_score       SMALLINT NOT NULL DEFAULT 0,
    detalle              TEXT,
    fecha_hora           TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_eventos_usuario FOREIGN KEY (id_usuario) REFERENCES acceso.usuarios(id_usuario) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_eventos_punto FOREIGN KEY (id_punto) REFERENCES acceso.puntos_acceso(id_punto) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_eventos_motivo FOREIGN KEY (id_motivo) REFERENCES acceso.motivos_evento(id_motivo) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_eventos_modo CHECK (modo_evento IN ('ENTRADA', 'SALIDA')),
    CONSTRAINT chk_eventos_resultado CHECK (resultado IN ('PERMITIDO', 'DENEGADO', 'INCOMPLETO', 'ANOMALIA')),
    CONSTRAINT chk_eventos_estado_anterior CHECK (estado_anterior IS NULL OR estado_anterior IN ('FUERA', 'DENTRO', 'BLOQUEADO')),
    CONSTRAINT chk_eventos_estado_nuevo CHECK (estado_nuevo IS NULL OR estado_nuevo IN ('FUERA', 'DENTRO', 'BLOQUEADO')),
    CONSTRAINT chk_eventos_score CHECK (anomalia_score BETWEEN 0 AND 100)
);

-- =========================================================
-- TABLA: horarios_usuario
-- =========================================================
CREATE TABLE IF NOT EXISTS acceso.horarios_usuario (
    id_horario  BIGSERIAL PRIMARY KEY,
    id_usuario  BIGINT NOT NULL REFERENCES acceso.usuarios(id_usuario),
    dia_semana  SMALLINT NOT NULL, -- 1=lunes ... 7=domingo
    hora_inicio TIME NOT NULL,
    hora_fin    TIME NOT NULL,
    materia     VARCHAR(100),
    activo      BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT chk_horarios_usuario_dia_semana CHECK (dia_semana BETWEEN 1 AND 7),
    CONSTRAINT chk_horarios_usuario_horas CHECK (hora_inicio < hora_fin)
);

-- =========================================================
-- TABLA: inasistencias
-- =========================================================
CREATE TABLE IF NOT EXISTS acceso.inasistencias (
    id_inasistencia           BIGSERIAL PRIMARY KEY,
    id_usuario                BIGINT NOT NULL,
    fecha                     DATE NOT NULL,
    dia_semana                SMALLINT NOT NULL,
    hora_inicio               TIME NOT NULL,
    hora_fin                  TIME NOT NULL,
    tipo                      VARCHAR(20) NOT NULL,
    justificacion             VARCHAR(255),
    detectada_automaticamente BOOLEAN NOT NULL DEFAULT FALSE,
    detalle                   TEXT,
    fecha_registro            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_inasistencias_usuario FOREIGN KEY (id_usuario) REFERENCES acceso.usuarios(id_usuario) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT chk_inasistencias_dia_semana CHECK (dia_semana BETWEEN 1 AND 7),
    CONSTRAINT chk_inasistencias_horas CHECK (hora_inicio < hora_fin),
    CONSTRAINT chk_inasistencias_tipo CHECK (tipo IN ('TOTAL', 'PARCIAL', 'RETARDO_GRAVE'))
);

-- =========================================================
-- FUNCIÓN Y TRIGGER para actualizar fecha_actualizacion
-- =========================================================
CREATE OR REPLACE FUNCTION acceso.fn_actualiza_fecha_usuario()
RETURNS TRIGGER
AS $$
BEGIN
    NEW.fecha_actualizacion = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_usuarios_fecha_actualizacion ON acceso.usuarios;

CREATE TRIGGER trg_usuarios_fecha_actualizacion
BEFORE UPDATE ON acceso.usuarios
FOR EACH ROW
EXECUTE FUNCTION acceso.fn_actualiza_fecha_usuario();

-- =========================================================
-- ÍNDICES
-- =========================================================
CREATE INDEX IF NOT EXISTS idx_usuarios_estado_actual ON acceso.usuarios (estado_actual);
CREATE INDEX IF NOT EXISTS idx_eventos_fecha_hora ON acceso.eventos_acceso (fecha_hora DESC);
CREATE INDEX IF NOT EXISTS idx_eventos_usuario_fecha ON acceso.eventos_acceso (id_usuario, fecha_hora DESC);
CREATE INDEX IF NOT EXISTS idx_eventos_uid_rfid_fecha ON acceso.eventos_acceso (uid_rfid_leido, fecha_hora DESC);
CREATE INDEX IF NOT EXISTS idx_eventos_resultado ON acceso.eventos_acceso (resultado);
CREATE INDEX IF NOT EXISTS idx_eventos_punto_modo_fecha ON acceso.eventos_acceso (id_punto, modo_evento, fecha_hora DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_horarios_usuario_bloque ON acceso.horarios_usuario (id_usuario, dia_semana, hora_inicio, hora_fin);
CREATE INDEX IF NOT EXISTS idx_horarios_usuario_dia ON acceso.horarios_usuario (id_usuario, dia_semana);

CREATE UNIQUE INDEX IF NOT EXISTS uq_inasistencias_usuario_bloque ON acceso.inasistencias (id_usuario, fecha, hora_inicio, hora_fin, tipo);
CREATE INDEX IF NOT EXISTS idx_inasistencias_usuario_fecha ON acceso.inasistencias (id_usuario, fecha DESC);
CREATE INDEX IF NOT EXISTS idx_inasistencias_fecha ON acceso.inasistencias (fecha DESC);