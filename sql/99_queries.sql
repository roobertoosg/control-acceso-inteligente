-- =========================================================
-- ARCHIVO DE CONSULTAS DE VERIFICACIÓN
--
-- Contiene consultas para revisar el estado de la base de
-- datos después de ejecutar los scripts de carga.
--
-- Ejecución: Manual, para depuración y verificación.
-- =========================================================

SET search_path TO acceso, public;

-- Ver últimos 20 eventos
SELECT
    id_evento, fecha_hora, uid_rfid_leido, modo_evento, resultado,
    estado_anterior, estado_nuevo, paso_detectado, servo_activado,
    anomalia_score, detalle
FROM acceso.eventos_acceso
ORDER BY id_evento DESC
LIMIT 20;

-- Ver todos los usuarios
SELECT
    id_usuario, nombre, apellido_paterno, matricula,
    uid_rfid, estado_actual, activo
FROM acceso.usuarios
ORDER BY id_usuario;

-- Ver horarios de Roberto y Carlos
SELECT
    u.nombre, u.apellido_paterno, u.matricula,
    h.dia_semana, h.hora_inicio, h.hora_fin, h.materia, h.activo
FROM acceso.horarios_usuario h
JOIN acceso.usuarios u ON u.id_usuario = h.id_usuario
WHERE u.matricula IN ('336006979', '336007065')
ORDER BY u.matricula, h.dia_semana, h.hora_inicio;

-- Ver eventos detallados de Roberto y Carlos
SELECT
    e.id_evento, e.fecha_hora, u.nombre, u.apellido_paterno, u.matricula,
    e.modo_evento, e.resultado, m.codigo AS motivo_codigo,
    e.estado_anterior, e.estado_nuevo, e.anomalia_score, e.detalle
FROM acceso.eventos_acceso e
JOIN acceso.usuarios u ON u.id_usuario = e.id_usuario
JOIN acceso.motivos_evento m ON m.id_motivo = e.id_motivo
WHERE u.matricula IN ('336006979', '336007065')
ORDER BY e.fecha_hora DESC, e.id_evento DESC;

-- Resumen de eventos por resultado y motivo para Roberto y Carlos
SELECT
    u.matricula, e.resultado, m.codigo AS motivo_codigo, COUNT(*) AS total
FROM acceso.eventos_acceso e
JOIN acceso.usuarios u ON u.id_usuario = e.id_usuario
JOIN acceso.motivos_evento m ON m.id_motivo = e.id_motivo
WHERE u.matricula IN ('336006979', '336007065')
GROUP BY u.matricula, e.resultado, m.codigo
ORDER BY u.matricula, total DESC, m.codigo;

-- Ver estado actual final de Roberto y Carlos
SELECT
    nombre, apellido_paterno, apellido_materno, matricula, estado_actual
FROM acceso.usuarios
WHERE matricula IN ('336006979', '336007065')
ORDER BY matricula;

-- Conteo total de eventos para Roberto y Carlos
SELECT
    u.matricula, u.nombre, u.apellido_paterno, COUNT(*) AS total_eventos
FROM acceso.eventos_acceso e
JOIN acceso.usuarios u ON u.id_usuario = e.id_usuario
WHERE u.matricula IN ('336006979', '336007065')
GROUP BY u.matricula, u.nombre, u.apellido_paterno
ORDER BY u.matricula;

-- Resumen de eventos por resultado y motivo para Saul y Selena
SELECT
    u.matricula, e.resultado, m.codigo AS motivo_codigo, COUNT(*) AS total
FROM acceso.eventos_acceso e
JOIN acceso.usuarios u ON u.id_usuario = e.id_usuario
JOIN acceso.motivos_evento m ON m.id_motivo = e.id_motivo
WHERE u.matricula IN ('20230006', '336007887')
GROUP BY u.matricula, e.resultado, m.codigo
ORDER BY u.matricula, total DESC, m.codigo;

-- Ver inasistencias de Roberto y Carlos
SELECT
    fecha, nombre, apellido_paterno, apellido_materno, matricula,
    dia_semana, hora_inicio, hora_fin, tipo, detalle
FROM acceso.vw_inasistencias_detalle
WHERE matricula IN ('336006979', '336007065')
ORDER BY fecha DESC, matricula, hora_inicio;

-- Resumen de faltas para Roberto y Carlos
SELECT
    matricula, nombre, apellido_paterno,
    COUNT(*) AS total_faltas,
    SUM(CASE WHEN tipo = 'TOTAL' THEN 1 ELSE 0 END) AS faltas_totales_bloque,
    SUM(CASE WHEN tipo = 'PARCIAL' THEN 1 ELSE 0 END) AS faltas_parciales_bloque
FROM acceso.vw_inasistencias_detalle
WHERE matricula IN ('336006979', '336007065')
GROUP BY matricula, nombre, apellido_paterno
ORDER BY matricula;