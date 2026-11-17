-- migracion_rele7.sql
-- SOLO si ya tienes una base creada con el esquema anterior (6 relés): agrega el relé 7 (bomba de OD).
-- En una base nueva creada con schema_bd.sql NO hace falta.
ALTER TABLE datos_bioreactor ADD COLUMN rele7 TINYINT(1) NOT NULL DEFAULT 0 AFTER rele6;
ALTER TABLE sistema_control  ADD COLUMN rele7 TINYINT(1) NOT NULL DEFAULT 0;
