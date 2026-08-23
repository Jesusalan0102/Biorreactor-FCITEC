# Bitácora de mejoras — Biorreactor FCITEC

Basado en la comparación contra Marinescu & Popescu (2018),
*"Open-Source bioreactor controller for bacterial protein expression"*.
Última actualización: 2026-08-23.

**Nota de alcance:** estas mejoras se generaron sin acceso de escritura
al repositorio de GitHub (no hay conector configurado) y sin poder leer
`controlfisicoV2.py` completo (GitHub trunca la vista en 1000/1861
líneas y el endpoint raw estaba bloqueado). Por eso el firmware se
reescribió completo, pero el lado Python se entrega como módulo nuevo +
instrucciones de integración puntual, para no arriesgar romper código
no visto.

## Estado por prioridad

| # | Prioridad | Mejora | Estado | Archivo |
|---|---|---|---|---|
| 1 | 🔴 Alta | Failsafe de override manual (relé no queda "pegado") | ✅ Implementado | `codigotesisV3.ino` |
| 2 | 🔴 Alta | Paro de emergencia por software (STOP/RESUME), sin botón físico | ✅ Implementado | `codigotesisV3.ino` |
| 3 | 🔴 Alta | Máquina de etapas autónoma en el Arduino | ✅ Implementado | `codigotesisV3.ino` |
| 4 | 🔴 Alta | Respaldo local de datos si MySQL falla | ✅ Módulo listo, ⏳ integración pendiente | `respaldo_local.py` |
| 5 | 🟡 Media | Dosificación adaptativa de pH + volumen total dosificado | ✅ Implementado | `codigotesisV3.ino` |
| 6 | 🟡 Media | OD600 por razón logarítmica (Beer-Lambert) con blanco | ✅ Implementado (disponible vía `ODLOGGET`, aún no es la señal de control) | `codigotesisV3.ino` |
| 7 | ⚪ Baja | Documentación (README, BOM, protocolo) | ✅ Implementado | `README.md` |
| 8 | ⚪ Baja | Campo de etapa y dosis en la BD | ✅ Migración lista, ⏳ ejecutar + integrar | `migraciones.sql` |

## Pasos pendientes (para retomar)

Estos son los puntos que requieren que alguien con acceso al código
completo de `controlfisicoV2.py` los conecte:

1. **Reemplazar el firmware**: subir `codigotesisV3.ino` al Arduino
   (reemplaza a `codigotesisV2.ino`). Es compatible con el parser
   actual (misma línea `TEMP,PH,OD600` cada segundo); todo lo nuevo es
   opt-in vía comandos nuevos.
2. **Integrar `respaldo_local.py`**: ver las instrucciones dentro del
   propio archivo (bloque de comentarios al inicio). Resumen: importar
   `RespaldoLocal`, instanciarlo una vez en `DashboardApp.__init__`, y
   llamar a `self.respaldo.guardar_lectura(...)` en el `except`/rama
   `else` de donde hoy se hace el `INSERT` a `datos_bioreactor`.
3. **Ejecutar `migraciones.sql`** contra la base de Clever Cloud, y
   luego actualizar el `INSERT` de `datos_bioreactor` para que también
   guarde `etapa` (via `STAGEGET`) y `dosis_naoh_ml` (via `DOSISGET`).
4. **Decidir si enviar los nuevos comandos automáticamente**: por ahora
   `STAGEGET`/`DOSISGET`/`ODLOGGET` solo responden bajo demanda. Hay
   que agregar, en el hilo que ya lee el puerto serial en
   `controlfisicoV2.py`, un envío periódico (por ejemplo cada 10-15 s)
   de esos tres comandos y parsear sus respuestas (`STAGE:...`,
   `DOSIS:...`, `OD600LOG:...`) sin interferir con el parseo de la
   línea `TEMP,PH,OD600`.
5. **(Opcional, prioridad media, no iniciado)** Adoptar `ODLOGGET`
   como señal de control en vez del OD600 lineal, una vez validado
   contra corridas reales — actualmente es solo diagnóstico.
6. **(Opcional)** Exponer `CONFIG:*` desde la interfaz de escritorio
   (hoy solo son accesibles enviando el comando manualmente por
   serial), para que `od_induccion`, `od_cosecha`, setpoint de
   temperatura, etc. se puedan ajustar desde el Dashboard sin recompilar
   el firmware.

## Cómo subir esto a GitHub

Estos archivos están en tu carpeta de descargas de esta conversación.
Cópialos a tu repo local y súbelos:

```bash
cd /ruta/a/tu/repo/Biorreactor-FCITEC

# 1) Reemplaza el firmware (o consérvalo como V2 y agrega V3 aparte)
cp /ruta/de/descarga/codigotesisV3.ino .

# 2) Agrega los archivos nuevos
cp /ruta/de/descarga/respaldo_local.py .
cp /ruta/de/descarga/migraciones.sql .
cp /ruta/de/descarga/MEJORAS.md .
cp /ruta/de/descarga/README.md .   # revisa que no pise contenido tuyo que quieras conservar

git add codigotesisV3.ino respaldo_local.py migraciones.sql MEJORAS.md README.md
git commit -m "Mejoras prioridad alta/media/baja: failsafe, autonomia, respaldo local, dosificacion adaptativa, OD600 log, docs"
git push origin main
```

Si prefieres mantener trazabilidad más fina, puedes hacer un commit
por prioridad en vez de uno solo (por ejemplo separando el firmware del
resto), usando este mismo `MEJORAS.md` como checklist.
