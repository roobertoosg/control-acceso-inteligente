-- =========================================================
-- ARCHIVO DE DATOS DE DEMOSTRACIÓN
--
-- Contiene scripts complejos para generar un historial de
-- eventos de acceso, incluyendo anomalías e inasistencias.
-- Ideal para poblar una base de datos para pruebas y demos.
--
-- Ejecución: Opcional. Ejecutar después de 04_sample_users_and_schedules.sql
-- =========================================================

SET search_path TO acceso, public;

-- =========================================================
-- SCRIPT 1: HISTÓRICO Y ANOMALÍAS PARA ROBERTO Y CARLOS
-- =========================================================
BEGIN;

-- 0) Usuarios objetivo
DROP TABLE IF EXISTS tmp_usuarios_objetivo;
CREATE TEMP TABLE tmp_usuarios_objetivo AS
SELECT id_usuario, matricula, nombre, apellido_paterno, apellido_materno
FROM acceso.usuarios
WHERE matricula IN ('336006979', '336007065');

-- 1) Fechas recientes que usaremos para anomalías
DROP TABLE IF EXISTS tmp_fechas_anomalia;
CREATE TEMP TABLE tmp_fechas_anomalia AS
WITH dias AS (
    SELECT gs::date AS fecha, EXTRACT(ISODOW FROM gs)::int AS dow
    FROM generate_series(current_date - interval '21 day', current_date - interval '1 day', interval '1 day') gs
)
SELECT
    MAX(fecha) FILTER (WHERE dow = 2) AS martes_reciente,
    MAX(fecha) FILTER (WHERE dow = 3) AS miercoles_reciente,
    MAX(fecha) FILTER (WHERE dow = 4) AS jueves_reciente,
    MAX(fecha) FILTER (WHERE dow = 7) AS domingo_reciente
FROM dias;

-- 2) Limpieza de eventos previos para estos usuarios
DELETE FROM acceso.eventos_acceso
WHERE id_usuario IN (SELECT id_usuario FROM tmp_usuarios_objetivo);

UPDATE acceso.usuarios SET estado_actual = 'FUERA'
WHERE id_usuario IN (SELECT id_usuario FROM tmp_usuarios_objetivo);

-- 3) Base histórica NORMAL
DROP TABLE IF EXISTS tmp_historial_normal;
CREATE TEMP TABLE tmp_historial_normal AS
WITH calendario AS (
    SELECT gs::date AS fecha
    FROM generate_series(current_date - interval '35 day', current_date - interval '1 day', interval '1 day') gs
),
bloques AS (
    SELECT u.id_usuario, u.matricula, c.fecha, MIN(h.hora_inicio) AS hora_inicio_dia, MAX(h.hora_fin) AS hora_fin_dia
    FROM tmp_usuarios_objetivo u
    JOIN acceso.horarios_usuario h ON h.id_usuario = u.id_usuario AND h.activo = TRUE
    JOIN calendario c ON EXTRACT(ISODOW FROM c.fecha)::int = h.dia_semana
    GROUP BY u.id_usuario, u.matricula, c.fecha
),
filtrado AS (
    SELECT b.* FROM bloques b CROSS JOIN tmp_fechas_anomalia f
    WHERE NOT (
        (b.matricula = '336006979' AND b.fecha = f.miercoles_reciente) OR
        (b.matricula = '336007065' AND b.fecha = f.jueves_reciente)
    )
)
SELECT
    id_usuario, matricula, fecha,
    (fecha::timestamp + hora_inicio_dia) + make_interval(mins => (-10 + floor(random() * 21))::int) AS ts_entrada,
    (fecha::timestamp + hora_fin_dia) - make_interval(mins => (floor(random() * 11))::int) AS ts_salida
FROM filtrado;

-- Entradas normales
INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, usr.uid_rfid, p.id_punto, 'ENTRADA', 'PERMITIDO', m.id_motivo, 'FUERA', 'DENTRO', TRUE, TRUE, 0, 'Histórico normal generado automáticamente', u.ts_entrada
FROM tmp_historial_normal u
JOIN acceso.usuarios usr ON usr.id_usuario = u.id_usuario
JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal'
JOIN acceso.motivos_evento m ON m.codigo = 'ENTRADA_VALIDA';

-- Salidas normales
INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, usr.uid_rfid, p.id_punto, 'SALIDA', 'PERMITIDO', m.id_motivo, 'DENTRO', 'FUERA', TRUE, TRUE, 0, 'Histórico normal generado automáticamente', u.ts_salida
FROM tmp_historial_normal u
JOIN acceso.usuarios usr ON usr.id_usuario = u.id_usuario
JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal'
JOIN acceso.motivos_evento m ON m.codigo = 'SALIDA_VALIDA';

-- 4) ANOMALÍAS MANUALES

-- 4.1 Roberto -> martes sin clase (SIN_CLASE_PROGRAMADA)
INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, usr.uid_rfid, p.id_punto, 'ENTRADA', 'ANOMALIA', m.id_motivo, 'FUERA', 'DENTRO', TRUE, TRUE, 70, 'Acceso anómalo: día sin clases programadas', (f.martes_reciente::timestamp + time '17:12')
FROM tmp_usuarios_objetivo u JOIN acceso.usuarios usr ON usr.id_usuario = u.id_usuario JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'SIN_CLASE_PROGRAMADA' CROSS JOIN tmp_fechas_anomalia f
WHERE u.matricula = '336006979';

INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, usr.uid_rfid, p.id_punto, 'SALIDA', 'ANOMALIA', m.id_motivo, 'DENTRO', 'FUERA', TRUE, TRUE, 85, 'Acceso anómalo: salida demasiado rápida tras día no habitual', (f.martes_reciente::timestamp + time '17:47')
FROM tmp_usuarios_objetivo u JOIN acceso.usuarios usr ON usr.id_usuario = u.id_usuario JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'SALIDA_DEMASIADO_RAPIDA' CROSS JOIN tmp_fechas_anomalia f
WHERE u.matricula = '336006979';

-- 4.2 Roberto -> miércoles con permanencia muy corta
INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, usr.uid_rfid, p.id_punto, 'ENTRADA', 'PERMITIDO', m.id_motivo, 'FUERA', 'DENTRO', TRUE, TRUE, 0, 'Entrada válida previa a salida demasiado rápida', (f.miercoles_reciente::timestamp + time '18:03')
FROM tmp_usuarios_objetivo u JOIN acceso.usuarios usr ON usr.id_usuario = u.id_usuario JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'ENTRADA_VALIDA' CROSS JOIN tmp_fechas_anomalia f
WHERE u.matricula = '336006979';

INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, usr.uid_rfid, p.id_punto, 'SALIDA', 'ANOMALIA', m.id_motivo, 'DENTRO', 'FUERA', TRUE, TRUE, 85, 'Salida demasiado rápida: solo 39 minutos de permanencia', (f.miercoles_reciente::timestamp + time '18:42')
FROM tmp_usuarios_objetivo u JOIN acceso.usuarios usr ON usr.id_usuario = u.id_usuario JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'SALIDA_DEMASIADO_RAPIDA' CROSS JOIN tmp_fechas_anomalia f
WHERE u.matricula = '336006979';

-- 4.3 Carlos Martin -> acceso en domingo
INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, usr.uid_rfid, p.id_punto, 'ENTRADA', 'ANOMALIA', m.id_motivo, 'FUERA', 'DENTRO', TRUE, TRUE, 90, 'Acceso anómalo en domingo', (f.domingo_reciente::timestamp + time '18:05')
FROM tmp_usuarios_objetivo u JOIN acceso.usuarios usr ON usr.id_usuario = u.id_usuario JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'ACCESO_EN_DOMINGO' CROSS JOIN tmp_fechas_anomalia f
WHERE u.matricula = '336007065';

INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, usr.uid_rfid, p.id_punto, 'SALIDA', 'ANOMALIA', m.id_motivo, 'DENTRO', 'FUERA', TRUE, TRUE, 85, 'Salida demasiado rápida en acceso dominical', (f.domingo_reciente::timestamp + time '18:40')
FROM tmp_usuarios_objetivo u JOIN acceso.usuarios usr ON usr.id_usuario = u.id_usuario JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'SALIDA_DEMASIADO_RAPIDA' CROSS JOIN tmp_fechas_anomalia f
WHERE u.matricula = '336007065';

-- 4.4 Carlos Martin -> jueves con reingreso rápido y movimientos excesivos
-- Entrada normal
INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, usr.uid_rfid, p.id_punto, 'ENTRADA', 'PERMITIDO', m.id_motivo, 'FUERA', 'DENTRO', TRUE, TRUE, 0, 'Jornada con múltiples movimientos', (f.jueves_reciente::timestamp + time '15:56')
FROM tmp_usuarios_objetivo u JOIN acceso.usuarios usr ON usr.id_usuario = u.id_usuario JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'ENTRADA_VALIDA' CROSS JOIN tmp_fechas_anomalia f
WHERE u.matricula = '336007065';

-- Primera salida
INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, usr.uid_rfid, p.id_punto, 'SALIDA', 'PERMITIDO', m.id_motivo, 'DENTRO', 'FUERA', TRUE, TRUE, 0, 'Salida intermedia del día', (f.jueves_reciente::timestamp + time '17:05')
FROM tmp_usuarios_objetivo u JOIN acceso.usuarios usr ON usr.id_usuario = u.id_usuario JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'SALIDA_VALIDA' CROSS JOIN tmp_fechas_anomalia f
WHERE u.matricula = '336007065';

-- Reingreso rápido
INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, usr.uid_rfid, p.id_punto, 'ENTRADA', 'ANOMALIA', m.id_motivo, 'FUERA', 'DENTRO', TRUE, TRUE, 60, 'Reingreso rápido 7 minutos después de la salida', (f.jueves_reciente::timestamp + time '17:12')
FROM tmp_usuarios_objetivo u JOIN acceso.usuarios usr ON usr.id_usuario = u.id_usuario JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'REINGRESO_RAPIDO' CROSS JOIN tmp_fechas_anomalia f
WHERE u.matricula = '336007065';

-- Nueva salida demasiado rápida
INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, usr.uid_rfid, p.id_punto, 'SALIDA', 'ANOMALIA', m.id_motivo, 'DENTRO', 'FUERA', TRUE, TRUE, 85, 'Salida demasiado rápida tras reingreso', (f.jueves_reciente::timestamp + time '17:38')
FROM tmp_usuarios_objetivo u JOIN acceso.usuarios usr ON usr.id_usuario = u.id_usuario JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'SALIDA_DEMASIADO_RAPIDA' CROSS JOIN tmp_fechas_anomalia f
WHERE u.matricula = '336007065';

-- Entrada marcada como movimientos excesivos
INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, usr.uid_rfid, p.id_punto, 'ENTRADA', 'ANOMALIA', m.id_motivo, 'FUERA', 'DENTRO', TRUE, TRUE, 65, 'Tercer ingreso del día: movimientos excesivos', (f.jueves_reciente::timestamp + time '18:02')
FROM tmp_usuarios_objetivo u JOIN acceso.usuarios usr ON usr.id_usuario = u.id_usuario JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'MOVIMIENTOS_EXCESIVOS' CROSS JOIN tmp_fechas_anomalia f
WHERE u.matricula = '336007065';

-- Salida final del día
INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, usr.uid_rfid, p.id_punto, 'SALIDA', 'PERMITIDO', m.id_motivo, 'DENTRO', 'FUERA', TRUE, TRUE, 0, 'Salida final del día con historial irregular', (f.jueves_reciente::timestamp + time '19:54')
FROM tmp_usuarios_objetivo u JOIN acceso.usuarios usr ON usr.id_usuario = u.id_usuario JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'SALIDA_VALIDA' CROSS JOIN tmp_fechas_anomalia f
WHERE u.matricula = '336007065';

-- 5) Recalcular estado actual de los usuarios objetivo
UPDATE acceso.usuarios u SET estado_actual = 'FUERA'
WHERE u.id_usuario IN (SELECT id_usuario FROM tmp_usuarios_objetivo);

WITH ultimo AS (
    SELECT DISTINCT ON (e.id_usuario) e.id_usuario, e.estado_nuevo
    FROM acceso.eventos_acceso e
    WHERE e.id_usuario IN (SELECT id_usuario FROM tmp_usuarios_objetivo)
    ORDER BY e.id_usuario, e.fecha_hora DESC, e.id_evento DESC
)
UPDATE acceso.usuarios u SET estado_actual = COALESCE(ultimo.estado_nuevo, 'FUERA')
FROM ultimo WHERE u.id_usuario = ultimo.id_usuario;

COMMIT;

-- =========================================================
-- SCRIPT 2: HISTÓRICO Y ANOMALÍAS PARA SAUL Y SELENA
-- =========================================================
BEGIN;

-- 1) Usuarios objetivo
DROP TABLE IF EXISTS tmp_usuarios_objetivo_2;
CREATE TEMP TABLE tmp_usuarios_objetivo_2 AS
SELECT id_usuario, matricula, nombre, apellido_paterno, apellido_materno, uid_rfid
FROM acceso.usuarios
WHERE matricula IN ('20230006', '336007887');

-- 2) Reconfigurar horarios de Saúl y Selena
DELETE FROM acceso.horarios_usuario
WHERE id_usuario IN (SELECT id_usuario FROM tmp_usuarios_objetivo_2);

-- Saúl: regular, casi siempre entra 4 pm y sale 6 u 8 pm
INSERT INTO acceso.horarios_usuario (id_usuario, dia_semana, hora_inicio, hora_fin, materia, activo)
SELECT u.id_usuario, h.dia_semana, h.hora_inicio::time, h.hora_fin::time, h.materia, TRUE
FROM tmp_usuarios_objetivo_2 u
JOIN (VALUES
    ('20230006', 1, '16:00', '18:00', 'Clase 1 - Lunes'),
    ('20230006', 1, '18:00', '20:00', 'Clase 2 - Lunes'),
    ('20230006', 3, '16:00', '18:00', 'Clase 1 - Miércoles'),
    ('20230006', 3, '18:00', '20:00', 'Clase 2 - Miércoles'),
    ('20230006', 4, '16:00', '18:00', 'Clase 1 - Jueves'),
    ('20230006', 4, '18:00', '20:00', 'Clase 2 - Jueves')
) AS h(matricula, dia_semana, hora_inicio, hora_fin, materia) ON u.matricula = h.matricula;

-- Selena: estancia más larga por servicio social
INSERT INTO acceso.horarios_usuario (id_usuario, dia_semana, hora_inicio, hora_fin, materia, activo)
SELECT u.id_usuario, h.dia_semana, h.hora_inicio::time, h.hora_fin::time, h.materia, TRUE
FROM tmp_usuarios_objetivo_2 u
JOIN (VALUES
    ('336007887', 1, '13:00', '15:00', 'Servicio social / bloque 1 - Lunes'),
    ('336007887', 1, '16:00', '18:00', 'Servicio social / bloque 2 - Lunes'),
    ('336007887', 1, '18:00', '20:00', 'Servicio social / bloque 3 - Lunes'),
    ('336007887', 2, '13:00', '15:00', 'Servicio social / bloque 1 - Martes'),
    ('336007887', 2, '16:00', '18:00', 'Servicio social / bloque 2 - Martes'),
    ('336007887', 2, '18:00', '20:00', 'Servicio social / bloque 3 - Martes'),
    ('336007887', 3, '13:00', '15:00', 'Servicio social / bloque 1 - Miércoles'),
    ('336007887', 3, '16:00', '18:00', 'Servicio social / bloque 2 - Miércoles'),
    ('336007887', 3, '18:00', '20:00', 'Servicio social / bloque 3 - Miércoles'),
    ('336007887', 4, '13:00', '15:00', 'Servicio social / bloque 1 - Jueves'),
    ('336007887', 4, '16:00', '18:00', 'Servicio social / bloque 2 - Jueves'),
    ('336007887', 4, '18:00', '20:00', 'Servicio social / bloque 3 - Jueves'),
    ('336007887', 5, '13:00', '15:00', 'Servicio social / bloque 1 - Viernes'),
    ('336007887', 5, '16:00', '18:00', 'Servicio social / bloque 2 - Viernes'),
    ('336007887', 5, '18:00', '20:00', 'Servicio social / bloque 3 - Viernes'),
    ('336007887', 6, '07:00', '09:00', 'Servicio social / bloque 1 - Sábado'),
    ('336007887', 6, '09:00', '11:00', 'Servicio social / bloque 2 - Sábado'),
    ('336007887', 6, '11:00', '13:00', 'Servicio social / bloque 3 - Sábado'),
    ('336007887', 6, '13:00', '15:00', 'Servicio social / bloque 4 - Sábado')
) AS h(matricula, dia_semana, hora_inicio, hora_fin, materia) ON u.matricula = h.matricula;

-- 3) Limpiar historial previo de Saúl y Selena
DELETE FROM acceso.eventos_acceso WHERE id_usuario IN (SELECT id_usuario FROM tmp_usuarios_objetivo_2);
UPDATE acceso.usuarios SET estado_actual = 'FUERA' WHERE id_usuario IN (SELECT id_usuario FROM tmp_usuarios_objetivo_2);

-- 4) Fechas especiales para anomalías
DROP TABLE IF EXISTS tmp_fechas_especiales;
CREATE TEMP TABLE tmp_fechas_especiales AS
WITH dias AS (
    SELECT gs::date AS fecha, EXTRACT(ISODOW FROM gs)::int AS dow
    FROM generate_series(current_date - interval '42 day', current_date - interval '1 day', interval '1 day') gs
)
SELECT
    MAX(fecha) FILTER (WHERE dow = 1) AS lunes_reciente,
    MAX(fecha) FILTER (WHERE dow = 4) AS jueves_reciente,
    MAX(fecha) FILTER (WHERE dow = 5) AS viernes_reciente
FROM dias;

-- 5) Histórico NORMAL de Saúl
DROP TABLE IF EXISTS tmp_hist_saul;
CREATE TEMP TABLE tmp_hist_saul AS
WITH calendario AS (
    SELECT gs::date AS fecha FROM generate_series(current_date - interval '42 day', current_date - interval '1 day', interval '1 day') gs
),
dias_saul AS (
    SELECT u.id_usuario, u.matricula, u.uid_rfid, c.fecha, EXTRACT(ISODOW FROM c.fecha)::int AS dow
    FROM tmp_usuarios_objetivo_2 u JOIN calendario c ON TRUE
    WHERE u.matricula = '20230006' AND EXTRACT(ISODOW FROM c.fecha)::int IN (1, 3, 4)
)
SELECT id_usuario, matricula, uid_rfid, fecha,
    (fecha::timestamp + time '15:54' + make_interval(mins => ((EXTRACT(day FROM fecha)::int % 12)))) AS ts_entrada,
    CASE WHEN (EXTRACT(day FROM fecha)::int % 3) = 0 THEN fecha::timestamp + time '17:56' - make_interval(mins => ((EXTRACT(day FROM fecha)::int % 6)))
         ELSE fecha::timestamp + time '19:54' - make_interval(mins => ((EXTRACT(day FROM fecha)::int % 8)))
    END AS ts_salida
FROM dias_saul;

INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT h.id_usuario, h.uid_rfid, p.id_punto, 'ENTRADA', 'PERMITIDO', m.id_motivo, 'FUERA', 'DENTRO', TRUE, TRUE, 0, 'Histórico regular de Saúl', h.ts_entrada
FROM tmp_hist_saul h JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'ENTRADA_VALIDA';

INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT h.id_usuario, h.uid_rfid, p.id_punto, 'SALIDA', 'PERMITIDO', m.id_motivo, 'DENTRO', 'FUERA', TRUE, TRUE, 0, 'Histórico regular de Saúl', h.ts_salida
FROM tmp_hist_saul h JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'SALIDA_VALIDA';

-- 6) Histórico NORMAL de Selena
DROP TABLE IF EXISTS tmp_hist_selena;
CREATE TEMP TABLE tmp_hist_selena AS
WITH calendario AS (
    SELECT gs::date AS fecha FROM generate_series(current_date - interval '42 day', current_date - interval '1 day', interval '1 day') gs
),
base AS (
    SELECT u.id_usuario, u.matricula, u.uid_rfid, c.fecha, EXTRACT(ISODOW FROM c.fecha)::int AS dow, EXTRACT(week FROM c.fecha)::int AS sem
    FROM tmp_usuarios_objetivo_2 u JOIN calendario c ON TRUE CROSS JOIN tmp_fechas_especiales f
    WHERE u.matricula = '336007887'
      AND (EXTRACT(ISODOW FROM c.fecha)::int BETWEEN 1 AND 5 OR (EXTRACT(ISODOW FROM c.fecha)::int = 6 AND (EXTRACT(week FROM c.fecha)::int % 2 = 0)))
      AND c.fecha NOT IN (f.lunes_reciente, f.jueves_reciente, f.viernes_reciente)
)
SELECT id_usuario, matricula, uid_rfid, fecha,
    CASE WHEN dow = 1 THEN fecha::timestamp + time '12:56' + make_interval(mins => ((EXTRACT(day FROM fecha)::int % 8)))
         WHEN dow = 2 THEN fecha::timestamp + time '15:50' + make_interval(mins => ((EXTRACT(day FROM fecha)::int % 10)))
         WHEN dow = 3 THEN fecha::timestamp + time '13:04' + make_interval(mins => ((EXTRACT(day FROM fecha)::int % 9)))
         WHEN dow = 4 THEN fecha::timestamp + time '16:01' + make_interval(mins => ((EXTRACT(day FROM fecha)::int % 12)))
         WHEN dow = 5 THEN fecha::timestamp + time '14:06' + make_interval(mins => ((EXTRACT(day FROM fecha)::int % 15)))
         WHEN dow = 6 THEN fecha::timestamp + time '07:10' + make_interval(mins => ((EXTRACT(day FROM fecha)::int % 10)))
    END AS ts_entrada,
    CASE WHEN dow = 1 THEN fecha::timestamp + time '19:42' - make_interval(mins => ((EXTRACT(day FROM fecha)::int % 10)))
         WHEN dow = 2 THEN fecha::timestamp + time '19:18' - make_interval(mins => ((EXTRACT(day FROM fecha)::int % 10)))
         WHEN dow = 3 THEN fecha::timestamp + time '19:54' - make_interval(mins => ((EXTRACT(day FROM fecha)::int % 12)))
         WHEN dow = 4 THEN fecha::timestamp + time '19:10' - make_interval(mins => ((EXTRACT(day FROM fecha)::int % 12)))
         WHEN dow = 5 THEN fecha::timestamp + time '18:36' - make_interval(mins => ((EXTRACT(day FROM fecha)::int % 10)))
         WHEN dow = 6 THEN fecha::timestamp + time '14:26' - make_interval(mins => ((EXTRACT(day FROM fecha)::int % 12)))
    END AS ts_salida
FROM base;

INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT h.id_usuario, h.uid_rfid, p.id_punto, 'ENTRADA', 'PERMITIDO', m.id_motivo, 'FUERA', 'DENTRO', TRUE, TRUE, 0, 'Histórico extendido de Selena (servicio social)', h.ts_entrada
FROM tmp_hist_selena h JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'ENTRADA_VALIDA';

INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT h.id_usuario, h.uid_rfid, p.id_punto, 'SALIDA', 'PERMITIDO', m.id_motivo, 'DENTRO', 'FUERA', TRUE, TRUE, 0, 'Histórico extendido de Selena (servicio social)', h.ts_salida
FROM tmp_hist_selena h JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'SALIDA_VALIDA';

-- 7) Anomalías manuales de Selena

-- 7.1 Lunes: entrada fuera de bloque
INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, u.uid_rfid, p.id_punto, 'ENTRADA', 'ANOMALIA', m.id_motivo, 'FUERA', 'DENTRO', TRUE, TRUE, 75, 'Selena: entrada fuera de bloque por llegada en horario intermedio', (f.lunes_reciente::timestamp + time '15:18')
FROM tmp_usuarios_objetivo_2 u CROSS JOIN tmp_fechas_especiales f JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'HORARIO_FUERA_DE_BLOQUE'
WHERE u.matricula = '336007887';

INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, u.uid_rfid, p.id_punto, 'SALIDA', 'PERMITIDO', m.id_motivo, 'DENTRO', 'FUERA', TRUE, TRUE, 0, 'Selena: salida después de jornada extendida', (f.lunes_reciente::timestamp + time '19:31')
FROM tmp_usuarios_objetivo_2 u CROSS JOIN tmp_fechas_especiales f JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'SALIDA_VALIDA'
WHERE u.matricula = '336007887';

-- 7.2 Jueves: llegada tarde
INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, u.uid_rfid, p.id_punto, 'ENTRADA', 'ANOMALIA', m.id_motivo, 'FUERA', 'DENTRO', TRUE, TRUE, 65, 'Selena: llegada tarde al bloque de 16:00', (f.jueves_reciente::timestamp + time '16:43')
FROM tmp_usuarios_objetivo_2 u CROSS JOIN tmp_fechas_especiales f JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'LLEGADA_TARDE'
WHERE u.matricula = '336007887';

INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, u.uid_rfid, p.id_punto, 'SALIDA', 'PERMITIDO', m.id_motivo, 'DENTRO', 'FUERA', TRUE, TRUE, 0, 'Selena: salida tras jornada larga', (f.jueves_reciente::timestamp + time '19:24')
FROM tmp_usuarios_objetivo_2 u CROSS JOIN tmp_fechas_especiales f JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'SALIDA_VALIDA'
WHERE u.matricula = '336007887';

-- 7.3 Viernes: muchos movimientos en un mismo día
INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, u.uid_rfid, p.id_punto, 'ENTRADA', 'PERMITIDO', m.id_motivo, 'FUERA', 'DENTRO', TRUE, TRUE, 0, 'Selena: inicio de jornada con múltiples movimientos', (f.viernes_reciente::timestamp + time '16:01')
FROM tmp_usuarios_objetivo_2 u CROSS JOIN tmp_fechas_especiales f JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'ENTRADA_VALIDA'
WHERE u.matricula = '336007887';

INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, u.uid_rfid, p.id_punto, 'SALIDA', 'PERMITIDO', m.id_motivo, 'DENTRO', 'FUERA', TRUE, TRUE, 0, 'Selena: salida intermedia', (f.viernes_reciente::timestamp + time '16:49')
FROM tmp_usuarios_objetivo_2 u CROSS JOIN tmp_fechas_especiales f JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'SALIDA_VALIDA'
WHERE u.matricula = '336007887';

INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, u.uid_rfid, p.id_punto, 'ENTRADA', 'ANOMALIA', m.id_motivo, 'FUERA', 'DENTRO', TRUE, TRUE, 60, 'Selena: reingreso rápido 8 minutos después', (f.viernes_reciente::timestamp + time '16:57')
FROM tmp_usuarios_objetivo_2 u CROSS JOIN tmp_fechas_especiales f JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'REINGRESO_RAPIDO'
WHERE u.matricula = '336007887';

INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, u.uid_rfid, p.id_punto, 'SALIDA', 'ANOMALIA', m.id_motivo, 'DENTRO', 'FUERA', TRUE, TRUE, 85, 'Selena: salida demasiado rápida tras reingreso', (f.viernes_reciente::timestamp + time '17:33')
FROM tmp_usuarios_objetivo_2 u CROSS JOIN tmp_fechas_especiales f JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'SALIDA_DEMASIADO_RAPIDA'
WHERE u.matricula = '336007887';

INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, u.uid_rfid, p.id_punto, 'ENTRADA', 'ANOMALIA', m.id_motivo, 'FUERA', 'DENTRO', TRUE, TRUE, 65, 'Selena: tercer ingreso del día, movimientos excesivos', (f.viernes_reciente::timestamp + time '18:04')
FROM tmp_usuarios_objetivo_2 u CROSS JOIN tmp_fechas_especiales f JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'MOVIMIENTOS_EXCESIVOS'
WHERE u.matricula = '336007887';

INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, u.uid_rfid, p.id_punto, 'SALIDA', 'PERMITIDO', m.id_motivo, 'DENTRO', 'FUERA', TRUE, TRUE, 0, 'Selena: salida final del día', (f.viernes_reciente::timestamp + time '19:38')
FROM tmp_usuarios_objetivo_2 u CROSS JOIN tmp_fechas_especiales f JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'SALIDA_VALIDA'
WHERE u.matricula = '336007887';

-- 8) Recalcular estado actual final
UPDATE acceso.usuarios SET estado_actual = 'FUERA' WHERE id_usuario IN (SELECT id_usuario FROM tmp_usuarios_objetivo_2);

WITH ultimo AS (
    SELECT DISTINCT ON (e.id_usuario) e.id_usuario, e.estado_nuevo
    FROM acceso.eventos_acceso e WHERE e.id_usuario IN (SELECT id_usuario FROM tmp_usuarios_objetivo_2)
    ORDER BY e.id_usuario, e.fecha_hora DESC, e.id_evento DESC
)
UPDATE acceso.usuarios u SET estado_actual = COALESCE(ultimo.estado_nuevo, 'FUERA')
FROM ultimo WHERE u.id_usuario = ultimo.id_usuario;

COMMIT;

-- =========================================================
-- SCRIPT 3: INASISTENCIAS MANUALES PARA DEMO
-- =========================================================
BEGIN;

-- 1) Fechas recientes para los escenarios
DROP TABLE IF EXISTS tmp_fechas_faltas;
CREATE TEMP TABLE tmp_fechas_faltas AS
WITH dias AS (
    SELECT gs::date AS fecha, EXTRACT(ISODOW FROM gs)::int AS dow
    FROM generate_series(current_date - interval '42 day', current_date - interval '1 day', interval '1 day') gs
),
ranked AS (
    SELECT fecha, dow, ROW_NUMBER() OVER (PARTITION BY dow ORDER BY fecha DESC) AS rn
    FROM dias WHERE dow IN (1, 3, 4)
)
SELECT
    MAX(fecha) FILTER (WHERE dow = 1 AND rn = 2) AS lunes_roberto_total,
    MAX(fecha) FILTER (WHERE dow = 4 AND rn = 2) AS jueves_roberto_parcial,
    MAX(fecha) FILTER (WHERE dow = 3 AND rn = 2) AS miercoles_carlos_total,
    MAX(fecha) FILTER (WHERE dow = 1 AND rn = 3) AS lunes_carlos_parcial
FROM ranked;

-- 2) Usuarios objetivo
DROP TABLE IF EXISTS tmp_usuarios_faltas;
CREATE TEMP TABLE tmp_usuarios_faltas AS
SELECT id_usuario, matricula, uid_rfid, nombre, apellido_paterno, apellido_materno
FROM acceso.usuarios
WHERE matricula IN ('336006979', '336007065');

-- 3) Limpieza previa de inasistencias y eventos de esos días
-- Roberto
DELETE FROM acceso.inasistencias WHERE id_usuario = (SELECT id_usuario FROM tmp_usuarios_faltas WHERE matricula = '336006979')
AND fecha IN (SELECT lunes_roberto_total FROM tmp_fechas_faltas UNION SELECT jueves_roberto_parcial FROM tmp_fechas_faltas);

DELETE FROM acceso.eventos_acceso WHERE id_usuario = (SELECT id_usuario FROM tmp_usuarios_faltas WHERE matricula = '336006979')
AND DATE(fecha_hora) IN (SELECT lunes_roberto_total FROM tmp_fechas_faltas UNION SELECT jueves_roberto_parcial FROM tmp_fechas_faltas);

-- Carlos Martin
DELETE FROM acceso.inasistencias WHERE id_usuario = (SELECT id_usuario FROM tmp_usuarios_faltas WHERE matricula = '336007065')
AND fecha IN (SELECT miercoles_carlos_total FROM tmp_fechas_faltas UNION SELECT lunes_carlos_parcial FROM tmp_fechas_faltas);

DELETE FROM acceso.eventos_acceso WHERE id_usuario = (SELECT id_usuario FROM tmp_usuarios_faltas WHERE matricula = '336007065')
AND DATE(fecha_hora) IN (SELECT miercoles_carlos_total FROM tmp_fechas_faltas UNION SELECT lunes_carlos_parcial FROM tmp_fechas_faltas);

-- 4) ROBERTO - FALTA TOTAL EN LUNES
INSERT INTO acceso.inasistencias (id_usuario, fecha, dia_semana, hora_inicio, hora_fin, tipo, justificacion, detectada_automaticamente, detalle)
SELECT u.id_usuario, f.lunes_roberto_total, 1, x.hora_inicio::time, x.hora_fin::time, 'TOTAL', NULL, FALSE, 'Escenario manual de falta total para demo'
FROM tmp_usuarios_faltas u CROSS JOIN tmp_fechas_faltas f CROSS JOIN (VALUES ('16:00', '18:00'), ('18:00', '20:00')) AS x(hora_inicio, hora_fin)
WHERE u.matricula = '336006979';

-- 5) ROBERTO - FALTA PARCIAL EN JUEVES
INSERT INTO acceso.inasistencias (id_usuario, fecha, dia_semana, hora_inicio, hora_fin, tipo, justificacion, detectada_automaticamente, detalle)
SELECT u.id_usuario, f.jueves_roberto_parcial, 4, time '16:00', time '18:00', 'PARCIAL', NULL, FALSE, 'Escenario manual: faltó al primer bloque, asistió al segundo'
FROM tmp_usuarios_faltas u CROSS JOIN tmp_fechas_faltas f
WHERE u.matricula = '336006979';

-- Entrada al segundo bloque
INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, u.uid_rfid, p.id_punto, 'ENTRADA', 'PERMITIDO', m.id_motivo, 'FUERA', 'DENTRO', TRUE, TRUE, 0, 'Asistencia parcial: Roberto sí asistió al segundo bloque', (f.jueves_roberto_parcial::timestamp + time '18:04')
FROM tmp_usuarios_faltas u CROSS JOIN tmp_fechas_faltas f JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'ENTRADA_VALIDA'
WHERE u.matricula = '336006979';

INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, u.uid_rfid, p.id_punto, 'SALIDA', 'PERMITIDO', m.id_motivo, 'DENTRO', 'FUERA', TRUE, TRUE, 0, 'Salida normal del segundo bloque', (f.jueves_roberto_parcial::timestamp + time '19:53')
FROM tmp_usuarios_faltas u CROSS JOIN tmp_fechas_faltas f JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'SALIDA_VALIDA'
WHERE u.matricula = '336006979';

-- 6) CARLOS MARTIN - FALTA TOTAL EN MIÉRCOLES
INSERT INTO acceso.inasistencias (id_usuario, fecha, dia_semana, hora_inicio, hora_fin, tipo, justificacion, detectada_automaticamente, detalle)
SELECT u.id_usuario, f.miercoles_carlos_total, 3, x.hora_inicio::time, x.hora_fin::time, 'TOTAL', NULL, FALSE, 'Escenario manual de falta total para demo'
FROM tmp_usuarios_faltas u CROSS JOIN tmp_fechas_faltas f CROSS JOIN (VALUES ('18:00', '20:00'), ('20:00', '22:00')) AS x(hora_inicio, hora_fin)
WHERE u.matricula = '336007065';

-- 7) CARLOS MARTIN - FALTA PARCIAL EN LUNES
INSERT INTO acceso.inasistencias (id_usuario, fecha, dia_semana, hora_inicio, hora_fin, tipo, justificacion, detectada_automaticamente, detalle)
SELECT u.id_usuario, f.lunes_carlos_parcial, 1, time '18:00', time '20:00', 'PARCIAL', NULL, FALSE, 'Escenario manual: asistió al primer bloque, faltó al segundo'
FROM tmp_usuarios_faltas u CROSS JOIN tmp_fechas_faltas f
WHERE u.matricula = '336007065';

-- Entrada al primer bloque
INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, u.uid_rfid, p.id_punto, 'ENTRADA', 'PERMITIDO', m.id_motivo, 'FUERA', 'DENTRO', TRUE, TRUE, 0, 'Asistencia parcial: Carlos Martin sí asistió al primer bloque', (f.lunes_carlos_parcial::timestamp + time '15:58')
FROM tmp_usuarios_faltas u CROSS JOIN tmp_fechas_faltas f JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'ENTRADA_VALIDA'
WHERE u.matricula = '336007065';

INSERT INTO acceso.eventos_acceso (id_usuario, uid_rfid_leido, id_punto, modo_evento, resultado, id_motivo, estado_anterior, estado_nuevo, paso_detectado, servo_activado, anomalia_score, detalle, fecha_hora)
SELECT u.id_usuario, u.uid_rfid, p.id_punto, 'SALIDA', 'PERMITIDO', m.id_motivo, 'DENTRO', 'FUERA', TRUE, TRUE, 0, 'Salida al terminar el primer bloque', (f.lunes_carlos_parcial::timestamp + time '17:54')
FROM tmp_usuarios_faltas u CROSS JOIN tmp_fechas_faltas f JOIN acceso.puntos_acceso p ON p.nombre = 'Acceso Principal' JOIN acceso.motivos_evento m ON m.codigo = 'SALIDA_VALIDA'
WHERE u.matricula = '336007065';

-- 8) Recalcular estado actual final
UPDATE acceso.usuarios SET estado_actual = 'FUERA' WHERE matricula IN ('336006979', '336007065');

WITH ultimo AS (
    SELECT DISTINCT ON (e.id_usuario) e.id_usuario, e.estado_nuevo
    FROM acceso.eventos_acceso e WHERE e.id_usuario IN (SELECT id_usuario FROM tmp_usuarios_faltas)
    ORDER BY e.id_usuario, e.fecha_hora DESC, e.id_evento DESC
)
UPDATE acceso.usuarios u SET estado_actual = COALESCE(ultimo.estado_nuevo, 'FUERA')
FROM ultimo WHERE u.id_usuario = ultimo.id_usuario;

COMMIT;