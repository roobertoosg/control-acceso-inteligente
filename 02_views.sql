-- =========================================================
-- ARCHIVO DE VISTAS
--
-- Contiene las vistas para simplificar consultas comunes.
--
-- Ejecución: Este script debe ejecutarse después de 01_schema.sql
-- =========================================================

SET search_path TO acceso, public;

-- =========================================================
-- VISTA: vw_eventos_detalle
-- =========================================================
CREATE OR REPLACE VIEW acceso.vw_eventos_detalle AS
SELECT
    e.id_evento,
    e.fecha_hora,
    e.uid_rfid_leido,
    u.id_usuario,
    u.nombre,
    u.apellido_paterno,
    u.apellido_materno,
    u.matricula,
    p.nombre AS punto_acceso,
    e.modo_evento,
    e.resultado,
    m.codigo AS motivo_codigo,
    m.descripcion AS motivo_descripcion,
    e.estado_anterior,
    e.estado_nuevo,
    e.paso_detectado,
    e.servo_activado,
    e.coincidencia_facial,
    e.anomalia_score,
    e.detalle
FROM acceso.eventos_acceso e
LEFT JOIN acceso.usuarios u ON e.id_usuario = u.id_usuario
INNER JOIN acceso.puntos_acceso p ON e.id_punto = p.id_punto
INNER JOIN acceso.motivos_evento m ON e.id_motivo = m.id_motivo;

-- =========================================================
-- VISTA: vw_inasistencias_detalle
-- =========================================================
CREATE OR REPLACE VIEW acceso.vw_inasistencias_detalle AS
SELECT
    i.*,
    u.nombre, u.apellido_paterno, u.apellido_materno, u.matricula, u.uid_rfid
FROM acceso.inasistencias i
JOIN acceso.usuarios u ON u.id_usuario = i.id_usuario;