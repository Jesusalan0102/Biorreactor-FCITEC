"""
Capa de acceso a datos para el SCADA web del biorreactor.
Reutiliza el mismo esquema de MySQL que ya usan monitoreoV2.py y
controlfisicoV2.py (tablas: usuarios, datos_bioreactor, sistema_control,
eventos). Todas las funciones de este módulo son SINCRONAS (bloqueantes)
a propósito: los endpoints async las llaman envueltas en
starlette.concurrency.run_in_threadpool para no bloquear el event loop
(mismo patrón que ya usas en carrier-transicold).
"""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pymysql
import pymysql.cursors

TZ_TIJUANA = ZoneInfo("America/Tijuana")

DB_HOST = os.environ.get("DB_HOST", "")
DB_USER = os.environ.get("DB_USER", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))

# Segundos sin datos nuevos antes de considerar el sistema "OFFLINE"
VENTANA_ONLINE_SEG = 25


def ahora_tijuana() -> datetime:
    return datetime.now(TZ_TIJUANA)


def conectar():
    """Conexión bloqueante a MySQL. Devuelve None si falla (nunca lanza)."""
    try:
        return pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            connect_timeout=10,
            cursorclass=pymysql.cursors.DictCursor,
        )
    except Exception as e:
        print(f"[DB] ERROR al conectar: {e}")
        return None


def validar_usuario(username: str, password: str) -> bool:
    """Valida contra la tabla usuarios (username/password), igual que la
    app de escritorio. NOTA: si en el futuro migras a contraseñas
    hasheadas (bcrypt, como ya haces en carrier-transicold), ajusta
    aquí la comparación."""
    conn = conectar()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM usuarios WHERE username = %s AND password = %s",
                (username, password),
            )
            return cur.fetchone() is not None
    except Exception as e:
        print(f"[DB] Error validando usuario: {e}")
        return False
    finally:
        conn.close()


def obtener_estado_actual(limit: int = 20) -> dict:
    """Devuelve el paquete completo que consume el dashboard: últimas N
    lecturas (orden cronológico ascendente), bandera de emergencia,
    estado del sensor de flujo (pulsos/litros acumulados + si hay
    alguna bomba de dosificación sin flujo detectado ahora mismo) y
    estado online/offline calculado con hora de Tijuana."""
    conn = conectar()
    if not conn:
        return {"ok": False, "status": "ERROR_BD", "rows": [], "emergencia": False}
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT temperatura, ph, od600, fecha_hora,
                       IFNULL(rele1, 0) AS rele1,
                       IFNULL(rele2, 0) AS rele2,
                       IFNULL(rele3, 0) AS rele3,
                       IFNULL(rele4, 0) AS rele4,
                       IFNULL(rele5, 0) AS rele5,
                       IFNULL(rele6, 0) AS rele6,
                       IFNULL(flujo_pulsos, 0) AS flujo_pulsos,
                       IFNULL(flujo_litros_acum, 0) AS flujo_litros_acum,
                       IFNULL(flujo_alerta, 0) AS flujo_alerta
                FROM datos_bioreactor
                ORDER BY fecha_hora DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()[::-1]  # cronológico ascendente

            cur.execute("SELECT emergencia FROM sistema_control WHERE id = 1")
            em_row = cur.fetchone()
            emergencia = bool(em_row["emergencia"]) if em_row else False

            if not rows:
                return {"ok": True, "status": "SIN_DATOS", "rows": [], "emergencia": emergencia}

            ultimo = rows[-1]
            fh = ultimo["fecha_hora"]
            esta_vivo = False
            if fh is not None:
                if fh.tzinfo is None:
                    fh = fh.replace(tzinfo=TZ_TIJUANA)
                esta_vivo = (ahora_tijuana() - fh).total_seconds() < VENTANA_ONLINE_SEG
                print(f"[DEBUG TZ] fh_ajustado={fh} | ahora_tijuana={ahora_tijuana()} | "
                      f"diff_seg={(ahora_tijuana() - fh).total_seconds()}")

            if emergencia:
                status = "EMERGENCIA"
            elif esta_vivo:
                status = "ONLINE"
            else:
                status = "OFFLINE"

            # Serializar fechas a ISO para JSON / websocket
            for r in rows:
                if r.get("fecha_hora") is not None:
                    r["fecha_hora"] = r["fecha_hora"].isoformat()

            # Bandera de conveniencia para el frontend: True si la última
            # fila trae una alerta de flujo activa (evita que el
            # dashboard tenga que inspeccionar rows[-1] por su cuenta).
            flujo_alerta_actual = bool(ultimo.get("flujo_alerta", 0))

            return {
                "ok": True,
                "status": status,
                "rows": rows,
                "emergencia": emergencia,
                "flujo_alerta": flujo_alerta_actual,
            }
    except Exception as e:
        print(f"[DB] Error obteniendo estado: {e}")
        return {"ok": False, "status": "ERROR_BD", "rows": [], "emergencia": False}
    finally:
        conn.close()


def obtener_eventos(limit: int = 15) -> list:
    conn = conectar()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT hora, descripcion FROM eventos ORDER BY hora DESC LIMIT %s",
                (limit,),
            )
            rows = cur.fetchall()
            for r in rows:
                if hasattr(r.get("hora"), "isoformat"):
                    r["hora"] = r["hora"].isoformat()
            return rows
    except Exception as e:
        print(f"[DB] Error obteniendo eventos: {e}")
        return []
    finally:
        conn.close()


def registrar_evento(mensaje: str) -> bool:
    conn = conectar()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO eventos (hora, descripcion) VALUES (%s, %s)",
                (ahora_tijuana().strftime("%Y-%m-%d %H:%M:%S"), mensaje),
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"[DB] Error registrando evento: {e}")
        return False
    finally:
        conn.close()


def activar_paro() -> bool:
    conn = conectar()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE sistema_control
                   SET emergencia = 1, comando_reanudar = 0,
                       rele1 = 0, rele2 = 0, rele3 = 0,
                       rele4 = 0, rele5 = 0, rele6 = 0
                   WHERE id = 1"""
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"[DB] Error activando paro: {e}")
        return False
    finally:
        conn.close()


def reanudar_sistema() -> bool:
    conn = conectar()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sistema_control SET emergencia = 0, comando_reanudar = 1 WHERE id = 1"
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"[DB] Error reanudando sistema: {e}")
        return False
    finally:
        conn.close()
