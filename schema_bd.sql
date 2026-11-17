-- schema_bd.sql  ·  Base de datos del Biorreactor FCITEC (MySQL 5.7+ / 8.x / MariaDB 10.3+)
-- Crea TODAS las tablas que usan controlfisicoV2.py, monitoreoV2.py y el SCADA web.
-- Es seguro ejecutarlo más de una vez (CREATE TABLE IF NOT EXISTS / INSERT IGNORE).
--
-- Uso:  mysql -h HOST -P PUERTO -u USUARIO -p NOMBRE_BD < schema_bd.sql
--       o bien:  python inicializar_bd.py        (lee el .env y además crea tu usuario)
--
-- La base de datos (NOMBRE_BD) ya debe existir; en la mayoría de los proveedores la crean
-- por ti al registrar el servicio. Si la creas a mano:
--   CREATE DATABASE biorreactor CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Usuarios de la app de escritorio y del SCADA web (contraseñas con bcrypt, ~60 caracteres).
CREATE TABLE IF NOT EXISTS usuarios (
  id        INT AUTO_INCREMENT PRIMARY KEY,
  username  VARCHAR(50)  NOT NULL UNIQUE,
  password  VARCHAR(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Lecturas del sensor y estado de los relés (1 fila por muestra; la app guarda cada pocos segundos).
-- fecha_hora se guarda en hora de Tijuana (la app la manda explícita; ver controlfisicoV2.py).
CREATE TABLE IF NOT EXISTS datos_bioreactor (
  id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
  fecha_hora          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  temperatura         FLOAT NULL,
  ph                  FLOAT NULL,
  od600               FLOAT NULL,
  rele1               TINYINT(1) NOT NULL DEFAULT 0,   -- calefactor
  rele2               TINYINT(1) NOT NULL DEFAULT 0,   -- bomba de pH (NaOH)
  rele3               TINYINT(1) NOT NULL DEFAULT 0,   -- bomba de IPTG
  rele4               TINYINT(1) NOT NULL DEFAULT 0,   -- bomba de cosecha
  rele5               TINYINT(1) NOT NULL DEFAULT 0,   -- agitador
  rele6               TINYINT(1) NOT NULL DEFAULT 0,   -- bomba de aire
  rele7               TINYINT(1) NOT NULL DEFAULT 0,   -- bomba de OD (muestreo; sensor de flujo en su línea)
  bomba_ph_on         TINYINT(1) NOT NULL DEFAULT 0,
  bomba_iptg_on       TINYINT(1) NOT NULL DEFAULT 0,
  bomba_cosecha_on    TINYINT(1) NOT NULL DEFAULT 0,
  sistema_funcionando TINYINT(1) NOT NULL DEFAULT 1,   -- 0 = paro de emergencia
  flujo_pulsos        INT   NOT NULL DEFAULT 0,        -- sensor de flujo FL1
  flujo_litros_acum   FLOAT NOT NULL DEFAULT 0,
  flujo_alerta        TINYINT(1) NOT NULL DEFAULT 0,
  etapa               VARCHAR(20) NULL,                -- opcionales (migraciones.sql)
  dosis_naoh_ml       FLOAT NULL,
  od600_log           FLOAT NULL,
  INDEX idx_datos_fecha (fecha_hora)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bitácora de eventos (dosis, verificaciones de flujo, cambios de parámetros, calibraciones...).
CREATE TABLE IF NOT EXISTS eventos (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  hora         DATETIME NOT NULL,
  descripcion  VARCHAR(500) NOT NULL,
  INDEX idx_eventos_hora (hora)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Fila única (id = 1) con el paro de emergencia compartido entre escritorio y web.
CREATE TABLE IF NOT EXISTS sistema_control (
  id                INT PRIMARY KEY,
  emergencia        TINYINT(1) NOT NULL DEFAULT 0,
  comando_reanudar  TINYINT(1) NOT NULL DEFAULT 0,
  rele1 TINYINT(1) NOT NULL DEFAULT 0, rele2 TINYINT(1) NOT NULL DEFAULT 0,
  rele3 TINYINT(1) NOT NULL DEFAULT 0, rele4 TINYINT(1) NOT NULL DEFAULT 0,
  rele5 TINYINT(1) NOT NULL DEFAULT 0, rele6 TINYINT(1) NOT NULL DEFAULT 0,
  rele7 TINYINT(1) NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
INSERT IGNORE INTO sistema_control (id, emergencia, comando_reanudar) VALUES (1, 0, 0);

-- Calibraciones de pH, OD600 y temperatura (la app guarda la última y se la manda al Arduino).
CREATE TABLE IF NOT EXISTS calibracion_sensores (
  id                 INT AUTO_INCREMENT PRIMARY KEY,
  sensor             VARCHAR(20) NOT NULL,
  slope              FLOAT NOT NULL,
  intercept          FLOAT NOT NULL,
  fecha_calibracion  DATETIME NOT NULL,
  usuario_id         INT NULL,
  notas              VARCHAR(255) NULL,
  INDEX idx_calib_sensor (sensor, fecha_calibracion)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
