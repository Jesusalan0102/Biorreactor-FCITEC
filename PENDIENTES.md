# Pendientes — Biorreactor FCITEC

Actualizado: 2026-11-12. Punto de retoma tras la revisión contra Marinescu & Popescu (2018).

## Ya hecho (commits `ce56bff` y `5ffe013`)
- Vigilancia de bombas cada 200 ms (pulsos de NaOH/IPTG ya no duran hasta 5 s).
- Filtro de 10 lecturas consecutivas de OD600 antes de inducir/cosechar.
- `CLAVE_MAESTRA` vacía ya no da acceso admin; la contraseña no se imprime.
- Web: `SESSION_SECRET` aleatoria si falta; aviso honesto del paro remoto.
- README: qué firmware usar (V2 sí, V3 no todavía).
- P&ID (escritorio y web): instrumentos de pH, temperatura, OD600 y flujo con valores en vivo.

## Por decidir / confirmar (necesitan tu criterio)
- [ ] Dosis inicial de NaOH: hoy 0.5 mL; el paper usa 20 µL (`ph_dosificacion['volumen_base_ml']`). Sin tope a la duplicación.
- [ ] Rango de pH: hoy 6.8–7.2; el paper usa 7.0–7.4 (en su corrida 7.0–7.2).
- [ ] Temperatura: hoy oscila 36.5–37.0 °C (centro 36.75); el paper apunta a 37 °C con PID externo.
- [ ] Línea donde va instalado el sensor de flujo FL1 (en el P&ID está sobre la línea de cosecha).
- [ ] Placa real (Mega o Uno) y cableado: comprobar pines del firmware contra el montaje físico.

## Pendiente técnico
- [ ] Registro de datos: guardar `etapa`, `dosis_naoh_ml`, `od600_log` (ejecutar `migraciones.sql`, actualizar el INSERT de `guardar_en_bd`).
- [ ] Integrar `respaldo_local.py` (respaldo si MySQL falla).
- [ ] Retención de 30 días borra corridas: exportar datos de tesis antes; proteger `/api/limpiar-datos`.
- [ ] Web: leer y mostrar flujo (`flujo_*`) y etapa.
- [ ] Decidir firmware: seguir con V2, o llevar V3 a paridad (watchdog, sensor de flujo, `OD:BLANK`, OD logarítmica en telemetría), integrar `START/STOP/STAGEGET` en la app, persistir `IPTGMS/HARVESTMIN/FLOWPH` en EEPROM y apagar el calefactor si el sensor de temperatura falla.
- [ ] Calibrar caudales (0.438 y 0.417 mL/s), concentración del stock de IPTG y volumen de cultivo.
- [ ] Probar con agua antes de un cultivo real: duración real de pulsos de bomba y alarma de flujo.

## Configuración
- [ ] Render: definir `SESSION_SECRET`.
- [ ] PC: `.env` con `CLAVE_MAESTRA`.
- [ ] Revocar los tokens de GitHub pegados en el chat.

## Sin revisar
- Páginas 20–27 del paper (resultados, figuras, tablas y suplementos).
