# Biorreactor FCITEC · paquete completo para pruebas

## Contenido
| Archivo | Para qué sirve |
|---|---|
| `codigotesisV2.ino` | Firmware del Arduino Mega (el que debes cargar). **Relé 7 = bomba de OD en el pin 9**; el sensor de flujo (1380 pulsos/L) se vigila solo en esa bomba |
| `controlfisicoV2.py` | App de escritorio: bomba de OD (P-106) con muestreo automático, sensor de flujo en su línea, panel de parámetros, calibración de bombas y sensores, diagnóstico |
| `monitoreoV2.py` + `web/` | SCADA web (FastAPI). Incluye la bomba de OD y el sensor F en su línea |
| `schema_bd.sql` | **Todas las tablas** de la base de datos nueva |
| `inicializar_bd.py` | Crea las tablas y tu primer usuario leyendo el `.env` |
| `migracion_rele7.sql` | Solo si ya tenías una base con 6 relés: agrega la columna `rele7` |
| `respaldo_local.py` | Respaldo en CSV si la base no responde |
| `.env.example`, `requirements.txt`, `render.yaml` | Configuración y despliegue |
| `codigotesisV3.ino`, `migraciones.sql` | Del repositorio, sin cambios (V3 no es compatible con la app) |

## 1. Base de datos nueva
1. Crea un MySQL/MariaDB (local o en un proveedor) y anota host, puerto, usuario, contraseña y nombre.
2. Copia `.env.example` a `.env` junto a `controlfisicoV2.py` y llénalo (`DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT`, `CLAVE_MAESTRA`).
   Si el proveedor exige SSL, agrega `DB_SSL=true` (o `DB_SSL_CA=ruta\ca.pem`).
3. `pip install -r requirements.txt` y luego `python inicializar_bd.py --usuario TU_USUARIO`
   (también puedes ejecutar `schema_bd.sql` con el cliente `mysql` o desde el panel web del proveedor).
4. Datos que debes dar al nuevo proveedor/cuenta: nombre de la base, usuario y contraseña con permisos CREATE/INSERT/SELECT/UPDATE/DELETE, conexión desde internet (si usarás el SCADA web en Render) y MySQL 5.7+ u 8.x.

Tablas: `usuarios`, `datos_bioreactor` (con `rele7`), `eventos`, `sistema_control` (una fila con id = 1) y `calibracion_sensores`.

Si Clever Cloud falla, mira el mensaje en la consola de la app (`ERROR en PyMySQL: (código, …)`). Un "Too many connections" o "max_user_connections" indica que se agotaron las conexiones permitidas por el plan; cierra el SCADA web y la app antes de reintentar.

## 2. Orden de pruebas recomendado
1. **Base**: `inicializar_bd.py` sin errores; login en la app con tu usuario.
2. **Arduino**: carga `codigotesisV2.ino`; en el monitor serie (9600) manda `PING` → `PONG` y revisa que llegue `TEMP,PH,OD600` cada segundo.
3. **Relés**: en la app, prueba cada bomba/relé y confirma que el elemento del P&ID cambia de color.
4. **Calibración**: pH, OD600 y temperatura (pestañas de siempre).
5. **Bombas y flujo** (Calibración → pestaña "Bombas y flujo"), con agua y etapa READY:
   - Probar la **bomba de OD** (el tiempo sugerido aparece solo) y ver cuántos pulsos cuenta el sensor.
   - Con ≥ 20 pulsos el sensor queda VALIDADO. Escribe los mL de la probeta y presiona "Aplicar caudal" (y "Calibrar K").
   - Repite con NaOH, IPTG y cosecha usando solo la probeta (esas líneas no tienen sensor).
6. **Parámetros**: botón "Parámetros y Diagnóstico": mL por pulso de IPTG (1) y de NaOH, espera de 10 s, rangos y el muestreo de OD (activar, cada cuántos segundos, duración, caudal). Se guardan en `parametros_proceso.json`.
   Muestreo de OD (por defecto): en GROWING e INDUCED la bomba de OD enciende 10 s cada 60 s; el sensor de flujo verifica cada muestreo (esperado vs. medido).
7. **SCADA web** (local): `cd web`, `pip install -r requirements.txt`, define las variables del `.env`, `uvicorn main:app --reload`, abre http://localhost:8000.
8. **Render**: sube el repositorio y define `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT` (y `DB_SSL` si aplica) en las variables de entorno.

## Conexión del sensor FL-S402B
Rojo → 5 V, negro → GND, amarillo → pin 18 (solo en Arduino Mega). Instálalo en la línea de la bomba de OD, respeta la flecha del flujo y cebra para que no pase aire.
Relé 7 (bomba de OD): módulo de relés canal 7 ← pin 9 del Mega. El módulo de 8 canales de tu diagrama ya tiene el canal.
