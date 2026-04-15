-- =========================================================
-- ARCHIVO DE USUARIOS Y HORARIOS DE MUESTRA
--
-- Contiene datos de ejemplo para usuarios y sus horarios.
--
-- Ejecución: Opcional. Ejecutar después de 03_catalog_data.sql
-- =========================================================

SET search_path TO acceso, public;

-- =========================================================
-- USUARIOS DE MUESTRA
-- =========================================================
INSERT INTO acceso.usuarios (nombre, apellido_paterno, apellido_materno, matricula, uid_rfid, estado_actual, activo)
VALUES
    ('Roberto', 'Serrano', 'Gonzalez', '336006979', '10008D56D8', 'FUERA', TRUE),
    ('Carlos Martin', 'Cruz', 'Martinez', '336007065', '540037E9ED', 'FUERA', TRUE),
    ('Franciso Gael', 'Garcia', 'Cardenas', '336007501', '3F00180103', 'FUERA', TRUE),
    ('Selena Daimar', 'Aguilar', 'Garcia', '336007887', 'MOCK_UID_0004', 'FUERA', TRUE),
    ('Carlos', 'Ramirez', 'Diaz', '20230005', 'MOCK_UID_0005', 'FUERA', TRUE),
    ('Saul', 'Martinez', 'Gomez', '20230006', 'MOCK_UID_0006', 'FUERA', TRUE)
ON CONFLICT (matricula) DO NOTHING;

-- =========================================================
-- HORARIOS DE MUESTRA (ROBERTO Y CARLOS)
-- =========================================================
DELETE FROM acceso.horarios_usuario
WHERE id_usuario IN (
    SELECT id_usuario FROM acceso.usuarios WHERE matricula IN ('336006979', '336007065')
);

INSERT INTO acceso.horarios_usuario (id_usuario, dia_semana, hora_inicio, hora_fin, materia, activo)
SELECT
    u.id_usuario,
    h.dia_semana,
    h.hora_inicio::time,
    h.hora_fin::time,
    h.materia,
    TRUE
FROM acceso.usuarios u
JOIN (
    VALUES
        ('336006979', 1, '16:00', '18:00', 'Clase 1 - Lunes'),
        ('336006979', 1, '18:00', '20:00', 'Clase 2 - Lunes'),
        ('336006979', 3, '18:00', '20:00', 'Clase 1 - Miércoles'),
        ('336006979', 3, '20:00', '22:00', 'Clase 2 - Miércoles'),
        ('336006979', 4, '16:00', '18:00', 'Clase 1 - Jueves'),
        ('336006979', 4, '18:00', '20:00', 'Clase 2 - Jueves'),

        ('336007065', 1, '16:00', '18:00', 'Clase 1 - Lunes'),
        ('336007065', 1, '18:00', '20:00', 'Clase 2 - Lunes'),
        ('336007065', 3, '18:00', '20:00', 'Clase 1 - Miércoles'),
        ('336007065', 3, '20:00', '22:00', 'Clase 2 - Miércoles'),
        ('336007065', 4, '16:00', '18:00', 'Clase 1 - Jueves'),
        ('336007065', 4, '18:00', '20:00', 'Clase 2 - Jueves')
) AS h(matricula, dia_semana, hora_inicio, hora_fin, materia)
    ON u.matricula = h.matricula;