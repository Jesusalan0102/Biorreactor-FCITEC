# Prueba real de 24 h — qué pasa si falla algo

## Si la laptop se apaga (y solo queda el Arduino por el cable COM)
| Qué | Resultado |
|---|---|
| Arduino (firmware V2) | A los **10 s** sin comandos apaga **todos los relés** (calentador, agitador, aire, bombas). Es el watchdog de seguridad. |
| Registro en la BD | **Se detiene.** El Arduino no tiene internet; solo la PC lo lleva a la BD. |
| SCADA web | Pasa a **OFFLINE** a los ~25 s. Última lectura queda visible. |
| Al volver la luz / encender | La app no arranca sola (ver "Arranque automático") y el cultivo hay que reanudarlo. |

**Ningún software puede registrar ni controlar sin un equipo encendido conectado al COM.**
Para que el apagón de la laptop no corte la prueba, el COM debe ir a un equipo que no se apague
(mini-PC o Raspberry/PC de escritorio con UPS) corriendo esta misma app.

## Lo que ya hace la app (v. de este commit)
- **Reconexión automática** del COM cada 5 s si se desconecta el cable / se reinicia el Arduino. Sin ventanas emergentes.
- **Eventos en el SCADA** (tabla `eventos`): "Serial perdido", "Serial reconectado", "Sin telemetría", "Telemetría restablecida".
- **Ya no guarda datos viejos como en vivo**: si pasan >15 s sin lectura nueva, no controla ni inserta en la BD (antes repetía la última lectura cada 5 s y el SCADA se veía "ONLINE" con valores congelados).
- **Si cae internet / la BD**: cada lectura va a `respaldo_bioreactor/pendientes.csv` y se sube sola, con su hora original, cuando la BD responde. Si la app se cierra con pendientes, se suben al abrirla de nuevo.
- **Evita que Windows suspenda** la laptop mientras la app corre.
- `3_iniciar_app.bat` reinicia la app si se cierra por error.

## Preparación del equipo (una vez)
1. Conectar a la corriente y usar **UPS** (aunque sea pequeña): protege de apagones y de reinicios.
2. Windows → *Configuración › Sistema › Inicio/apagado*: **Suspender = Nunca** (en corriente). Cerrar la tapa: **No hacer nada**.
   Por consola (admin): `powercfg /change standby-timeout-ac 0` y `powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0`.
3. Desactivar **Windows Update reinicio automático** durante la prueba (Horas activas / pausar actualizaciones).
4. En el Administrador de dispositivos → puerto COM → Administración de energía: desmarcar "Permitir que el equipo apague este dispositivo".
5. Arranque automático tras apagón: poner un acceso directo a `3_iniciar_app.bat` en `shell:startup`
   (la app pedirá login; el cultivo no se reanuda solo).

## Antes de dejarlo 24 h
- Dejar la ventana de la app a la vista y revisar `Diagnóstico del equipo` al inicio.
- Probar: desconectar el USB 30 s → debe aparecer "Serial perdido/reconectado" en eventos y seguir registrando.
- Probar: apagar el WiFi 2 min → al volver, la gráfica del SCADA no debe tener hueco.
- Respaldo adicional en un solo comando: `respaldo_bioreactor/` guarda lo pendiente; no se versiona en git.
