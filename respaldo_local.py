"""
respaldo_local.py - Cola local en CSV para no perder lecturas cuando la
base de datos (TiDB/MySQL) no responde.

Flujo (ya integrado en controlfisicoV2.py):
  1. guardar_en_bd() intenta el INSERT. Si falla (sin internet, BD caída),
     la lectura se agrega a respaldo_bioreactor/pendientes.csv.
  2. En cuanto un INSERT vuelve a funcionar, se suben a la BD todas las
     filas pendientes con su hora ORIGINAL (así la gráfica del SCADA queda
     sin huecos) y el archivo se vacía.
  3. Si la app se cierra o la laptop se apaga con filas pendientes, el
     archivo sigue en disco y se sube en la siguiente ejecución.
"""

import csv
import os
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

TZ_TIJUANA = ZoneInfo("America/Tijuana")

CARPETA_RESPALDO = "respaldo_bioreactor"
NOMBRE_ARCHIVO = "pendientes.csv"
COLUMNAS = [
    "fecha_hora", "temperatura", "ph", "od600",
    "rele1", "rele2", "rele3", "rele4", "rele5", "rele6", "rele7",
    "bomba_ph_on", "bomba_iptg_on", "bomba_cosecha_on",
    "sistema_funcionando",
    "flujo_pulsos", "flujo_litros_acum", "flujo_alerta",
]
LOTE = 200  # filas por commit al sincronizar


class RespaldoLocal:
    def __init__(self, carpeta: str = CARPETA_RESPALDO):
        self.carpeta = carpeta
        os.makedirs(self.carpeta, exist_ok=True)
        self.archivo = os.path.join(self.carpeta, NOMBRE_ARCHIVO)
        self._lock = threading.Lock()
        self._crear_archivo_si_no_existe()
        self.pendientes = self._contar()

    # ---------------------------------------------------------- archivo
    def _crear_archivo_si_no_existe(self):
        if not os.path.exists(self.archivo):
            with open(self.archivo, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(COLUMNAS)

    def _leer(self):
        with open(self.archivo, "r", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _contar(self):
        with self._lock:
            try:
                return len(self._leer())
            except Exception:
                return 0

    def _reescribir(self, filas):
        tmp = self.archivo + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNAS)
            w.writeheader()
            w.writerows(filas)
        os.replace(tmp, self.archivo)

    # ---------------------------------------------------------- API
    def guardar_lectura(self, fila: dict):
        """Agrega una lectura (dict con las columnas de COLUMNAS; la clave
        fecha_hora es obligatoria, formato 'YYYY-MM-DD HH:MM:SS' Tijuana)."""
        with self._lock:
            self._crear_archivo_si_no_existe()
            with open(self.archivo, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="ignore", restval=0)
                w.writerow(fila)
            self.pendientes += 1
            return self.pendientes

    def reintentar_pendientes(self, obtener_conn, tabla: str = "datos_bioreactor"):
        """Sube a la BD las filas pendientes usando la conexión que devuelve
        obtener_conn() (NO la cierra: es la conexión persistente de la app).
        Devuelve cuántas filas se sincronizaron. Las que fallen se conservan."""
        if self.pendientes <= 0:
            return 0
        conn = obtener_conn()
        if not conn:
            return 0
        with self._lock:
            filas = self._leer()
            if not filas:
                self.pendientes = 0
                return 0
            cols_sql = ", ".join(COLUMNAS)
            marcas = ", ".join(["%s"] * len(COLUMNAS))
            sql = f"INSERT INTO {tabla} ({cols_sql}) VALUES ({marcas})"
            subidas = 0
            try:
                cur = conn.cursor()
                for i in range(0, len(filas), LOTE):
                    bloque = filas[i:i + LOTE]
                    cur.executemany(sql, [tuple(f.get(c, 0) for c in COLUMNAS) for f in bloque])
                    conn.commit()
                    subidas += len(bloque)
            except Exception as e:
                print(f"[Respaldo] Sincronización interrumpida tras {subidas} filas: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass
            restantes = filas[subidas:]
            self._reescribir(restantes)
            self.pendientes = len(restantes)
        if subidas:
            print(f"[Respaldo] {subidas} filas pendientes subidas a la BD ({self.pendientes} restantes)")
        return subidas
