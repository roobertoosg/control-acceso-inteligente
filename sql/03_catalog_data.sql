-- =========================================================
-- ARCHIVO DE DATOS DE CATÁLOGO
--
-- Contiene los datos iniciales para las tablas de catálogo.
--
-- Ejecución: Este script debe ejecutarse después de 01_schema.sql
-- =========================================================

SET search_path TO acceso, public;

-- =========================================================
-- CATÁLOGO INICIAL DE PUNTOS DE ACCESO
-- =========================================================
INSERT INTO acceso.puntos_acceso (nombre, tipo_punto, descripcion)
VALUES ('Acceso Principal', 'MIXTO', 'Punto de acceso del prototipo')
ON CONFLICT (nombre) DO NOTHING;

-- =========================================================
-- CATÁLOGO INICIAL DE MOTIVOS DE EVENTO
-- =========================================================
INSERT INTO acceso.motivos_evento (codigo, descripcion, es_anomalia, es_error)
VALUES
    ('ENTRADA_VALIDA', 'Entrada autorizada y completada correctamente', FALSE, FALSE),
    ('SALIDA_VALIDA', 'Salida autorizada y completada correctamente', FALSE, FALSE),
    ('RFID_NO_REGISTRADO', 'El UID RFID leído no pertenece a ningún usuario registrado', FALSE, TRUE),
    ('EVENTO_INCOMPLETO_TIMEOUT', 'La autorización expiró sin completarse el cruce', FALSE, TRUE),
    ('ACCESO_EN_DOMINGO', 'Acceso registrado en domingo', TRUE, FALSE),
    ('SALIDA_DEMASIADO_RAPIDA', 'Salida ocurrida en un tiempo menor al esperado', TRUE, FALSE),
    ('HORARIO_FUERA_DE_BLOQUE', 'Acceso fuera de los bloques horarios escolares esperados', TRUE, FALSE),
    ('LLEGADA_TARDE', 'Entrada tardía respecto al inicio esperado de clase', TRUE, FALSE),
    ('REINGRESO_RAPIDO', 'Salida y nueva entrada en un intervalo demasiado corto', TRUE, FALSE),
    ('MOVIMIENTOS_EXCESIVOS', 'Cantidad atípica de entradas y salidas en un mismo día', TRUE, FALSE),
    ('HORARIO_EXTREMO', 'Acceso en una hora demasiado alejada del horario escolar', TRUE, FALSE),
    ('ESTANCIA_EXCESIVA', 'Tiempo de permanencia excesivo respecto al patrón esperado', TRUE, FALSE),
    ('SIN_CLASE_PROGRAMADA', 'Acceso en un día sin clases programadas para el usuario', TRUE, FALSE),
    ('REINTENTOS_FRECUENTES', 'Se detectaron varios rechazos en un periodo corto', TRUE, FALSE)
ON CONFLICT (codigo) DO NOTHING;