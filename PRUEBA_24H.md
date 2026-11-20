# Prueba real de 24 h — qué pasa si falla algo

## Importante: el Arduino (firmware V2) NO es autónomo
Todo el control (termostato, pH, dosificación, OD) corre en Python en la laptop. El Arduino solo ejecuta
lo que la PC le manda y, si pasan **10 s sin comandos**, apaga **todos los relés** (watchdog), aunque siga
con energía. Por eso, si la laptop se **suspende/duerme/apaga**: relés apagados, sin registro en la BD y
SCADA en OFFLINE a los ~25 s. Para la prueba, **la laptop no debe suspenderse nunca**.

## Comandos para que la laptop no se suspenda (CMD como administrador, conectada a corriente)
```
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 15
powercfg /hibernate off
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setacvalueindex SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0
powercfg /setactive SCHEME_CURRENT
```
(0 = nunca; cerrar la tapa no hace nada; USB sin suspensión selectiva.) Además: Administrador de dispositivos →
puerto COM → Administración de energía → desmarcar "Permitir que el equipo apague este dispositivo",
y pausar Windows Update para evitar reinicios automáticos.

## Lo que ya hace la app (v. de este commit)
- **Reconexión automática** del COM cada 5 s si se desconecta el cable / se reinicia el Arduino. Sin ventanas emergentes.
- **Eventos en el SCADA** (tabla `eventos`): "Serial perdido", "Serial reconectado", "Sin telemetría", "Telemetría restablecida".
- **Ya no guarda datos viejos como en vivo**: si pasan >15 s sin lectura nueva, no controla ni inserta en la BD (antes repetía la última lectura cada 5 s y el SCADA se veía "ONLINE" con valores congelados).
- **Si cae internet / la BD**: cada lectura va a `respaldo_bioreactor/pendientes.csv` y se sube sola, con su hora original, cuando la BD responde. Si la app se cierra con pendientes, se suben al abrirla de nuevo.
- **Evita que Windows suspenda** la laptop mientras la app corre.
- `3_iniciar_app.bat` reinicia la app si se cierra por error.

## Preparación del equipo (una vez)
1. Conectar a la corriente; **UPS** recomendada.
2. Aplicar los comandos de arriba.
3. Arranque automático tras apagón: poner un acceso directo a `3_iniciar_app.bat` en `shell:startup`
   (la app pedirá login; el cultivo no se reanuda solo).

## Antes de dejarlo 24 h
- Dejar la ventana de la app a la vista y revisar `Diagnóstico del equipo` al inicio.
- Probar: desconectar el USB 30 s → debe aparecer "Serial perdido/reconectado" en eventos y seguir registrando.
- Probar: apagar el WiFi 2 min → al volver, la gráfica del SCADA no debe tener hueco.
- Respaldo adicional en un solo comando: `respaldo_bioreactor/` guarda lo pendiente; no se versiona en git.

## Pendiente (no implementado)
- Autonomía en firmware (termostato/agitador/aire que sigan si la PC falla): hoy V2 apaga todo a los 10 s. Opción futura con `#define` desactivado por defecto.
