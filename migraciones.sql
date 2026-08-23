-- migraciones.sql
-- -----------------------------------------------------------------------
-- [PRIORIDAD BAJA] Agrega a la tabla datos_bioreactor los campos que el
-- paper de Marinescu & Popescu (2018) sí registra y que permiten
-- reconstruir la curva de crecimiento con las fases marcadas
-- (equivalente a su Figura 5A/E):
--
--   - etapa: READY / GROWING / INDUCCION / COSECHA / DONE
--            (viene del comando STAGEGET del firmware V3)
--   - dosis_naoh_ml: volumen acumulado de NaOH dosificado en la corrida
--            (viene del comando DOSISGET del firmware V3; en el paper
--            este dato correlaciona con el OD600 durante la fase log,
--            Fig. 5C/E, y sirve como estimador de biomasa de respaldo)
--   - od600_log: OD600 calculado por razón logarítmica (Beer-Lambert),
--            además del OD600 con calibración lineal que ya guardas
--            (viene del comando ODLOGGET del firmware V3)
--
-- Ejecuta esto una sola vez contra tu base de Clever Cloud:
--   mysql -h <DB_HOST> -u <DB_USER> -p <DB_NAME> < migraciones.sql
-- -----------------------------------------------------------------------

ALTER TABLE datos_bioreactor
  ADD COLUMN IF NOT EXISTS etapa VARCHAR(20) NULL,
  ADD COLUMN IF NOT EXISTS dosis_naoh_ml FLOAT NULL,
  ADD COLUMN IF NOT EXISTS od600_log FLOAT NULL;

-- Nota: MySQL < 8.0.29 no soporta "ADD COLUMN IF NOT EXISTS". Si tu
-- versión de Clever Cloud da error de sintaxis, quita "IF NOT EXISTS"
-- de las tres líneas y ejecuta una sola vez (fallará con un error claro
-- si la columna ya existe, lo cual es seguro).
