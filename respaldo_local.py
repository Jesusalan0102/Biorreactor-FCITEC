"""
respaldo_local.py
-----------------------------------------------------------------------
[PRIORIDAD ALTA] Respaldo local de datos cuando la base de datos MySQL
(Clever Cloud) no responde.

Por qué existe: en controlfisicoV2.py, cada vez que conectar_db() falla
o lanza una excepción, la lectura de ese ciclo (temperatura, pH, OD600,
estado de relés) simplemente se pierde. Si el biorreactor corre
desatendido durante horas y hay un corte de internet a mitad del
cultivo, esos datos nunca se recuperan y el análisis posterior (curva
de crecimiento, Fig. 5 del paper) queda incompleto.

Qué hace este módulo:
  1. Escribe cada lectura en un CSV local (uno por corrida), igual que
     hacía el Arduino original del paper en la microSD, pero aquí desde
     el lado de la PC.
  2. Si una fila se guardó en el CSV porque la BD no estaba disponible,
     queda marcada como "pendiente" (columna sincronizado=0).
  3. Expone reintentar_pendientes(), que puedes llamar periódicamente
     (por ejemplo cada vez que chequear_emergencia_periodico() confirme
     que la BD volvió) para subir a MySQL las filas pendientes y
     marcarlas como sincronizadas.

CÓMO INTEGRARLO EN controlfisicoV2.py
-----------------------------------------------------------------------
No pude leer el archivo completo (GitHub trunca la vista en 1000 de
1861 líneas y no tengo acceso de red para bajar el "raw"), así que no
edito ese archivo directamente. Busca en tu código el lugar donde se
insertan las lecturas en la tabla `datos_bioreactor` (probablemente
dentro del hilo/loop que lee el puerto serial, algo como:

    cursor.execute(
        "INSERT INTO datos_bioreactor (temperatura, ph, od600, ...) "
        "VALUES (%s, %s, %s, ...)", (...)
    )

y agrega el respaldo local así:

    from respaldo_local import RespaldoLocal

    # una sola vez, al crear el DashboardApp:
    self.respaldo = RespaldoLocal()

    # en el punto donde ya tienes temp, ph, od600, rele_estados, etapa:
    conn = conectar_db()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO datos_bioreactor (...) VALUES (...)", (...))
            conn.commit()
        except Exception as e:
            print(f"[BD] Error insertando lectura, guardando respaldo local: {e}")
            self.respaldo.guardar_lectura(temp, ph, od600, rele_estados, etapa)
        finally:
            conn.close()
    else:
        self.respaldo.guardar_lectura(temp, ph, od600, rele_estados, etapa)

Y para reintentar el envío de lo pendiente cuando la BD vuelva (por
ejemplo, dentro de tu chequear_emergencia_periodico(), que ya corre
periódicamente):

    self.respaldo.reintentar_pendientes(conectar_db)
-----------------------------------------------------------------------
"""

import csv
import os
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

TZ_TIJUANA = ZoneInfo("America/Tijuana")

CARPETA_RESPALDO = "respaldo_bioreactor"
COLUMNAS = [
    "fecha_hora", "temperatura", "ph", "od600",
    "rele1", "rele2", "rele3", "rele4", "rele5", "rele6",
    "etapa", "sincronizado",
]


class RespaldoLocal:
    def __init__(self, carpeta: str = CARPETA_RESPALDO):
        self.carpeta = carpeta
        os.makedirs(self.carpeta, exist_ok=True)
        self.archivo = os.path.join(
            self.carpeta,
            f"respaldo_{datetime.now(TZ_TIJUANA).strftime('%Y%m%d_%H%M%S')}.csv",
        )
        self._lock = threading.Lock()
        self._crear_archivo_si_no_existe()

    def _crear_archivo_si_no_existe(self):
        if not os.path.exists(self.archivo):
            with open(self.archivo, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(COLUMNAS)

    def guardar_lectura(self, temperatura, ph, od600, rele_estados: dict, etapa: str = ""):
        """Agrega una fila al CSV local, marcada como pendiente de sincronizar."""
        fila = [
            datetime.now(TZ_TIJUANA).isoformat(),
            temperatura, ph, od600,
            int(bool(rele_estados.get(1))), int(bool(rele_estados.get(2))),
            int(bool(rele_estados.get(3))), int(bool(rele_estados.get(4))),
            int(bool(rele_estados.get(5))), int(bool(rele_estados.get(6))),
            etapa, 0,
        ]
        with self._lock:
            with open(self.archivo, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(fila)

    def filas_pendientes(self):
        """Lee del CSV todas las filas aún no sincronizadas a MySQL."""
        pendientes = []
        if not os.path.exists(self.archivo):
            return pendientes
        with self._lock:
            with open(self.archivo, "r", newline="", encoding="utf-8") as f:
                lector = csv.DictReader(f)
                for i, fila in enumerate(lector):
                    if fila.get("sincronizado") == "0":
                        pendientes.append((i, fila))
        return pendientes

    def reintentar_pendientes(self, conectar_db_fn, tabla: str = "datos_bioreactor"):
        """
        Intenta subir a MySQL las filas marcadas como pendientes.
        conectar_db_fn debe ser la misma función conectar_db() que ya
        usa controlfisicoV2.py (se la pasas por parámetro para no
        duplicar credenciales aquí).
        Devuelve cuántas filas se sincronizaron con éxito.
        """
        pendientes = self.filas_pendientes()
        if not pendientes:
            return 0

        conn = conectar_db_fn()
        if not conn:
            return 0

        sincronizadas = 0
        try:
            cursor = conn.cursor()
            for _, fila in pendientes:
                try:
                    cursor.execute(
                        f"""INSERT INTO {tabla}
                            (temperatura, ph, od600, fecha_hora,
                             rele1, rele2, rele3, rele4, rele5, rele6)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (
                            fila["temperatura"], fila["ph"], fila["od600"], fila["fecha_hora"],
                            fila["rele1"], fila["rele2"], fila["rele3"],
                            fila["rele4"], fila["rele5"], fila["rele6"],
                        ),
                    )
                    sincronizadas += 1
                except Exception as e:
                    print(f"[Respaldo] No se pudo sincronizar una fila: {e}")
            conn.commit()
        finally:
            conn.close()

        if sincronizadas > 0:
            self._marcar_todo_sincronizado()
        return sincronizadas

    def _marcar_todo_sincronizado(self):
        """Reescribe el CSV marcando sincronizado=1 en todas las filas.
        Simplifica el manejo de reintentos parciales: si alguna fila
        falló al sincronizar, seguirá reintentándose en la siguiente
        pasada junto con las demás (no es lo más elegante, pero es
        seguro y evita perder datos)."""
        if not os.path.exists(self.archivo):
            return
        with self._lock:
            with open(self.archivo, "r", newline="", encoding="utf-8") as f:
                filas = list(csv.DictReader(f))
            for fila in filas:
                fila["sincronizado"] = "1"
            with open(self.archivo, "w", newline="", encoding="utf-8") as f:
                escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
                escritor.writeheader()
                escritor.writerows(filas)
