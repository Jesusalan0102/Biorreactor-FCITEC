# Biorreactor FCITEC

Sistema de control y monitoreo para un biorreactor de mesa, inspirado
metodológicamente en Marinescu & Popescu (2018), *"Open-Source
bioreactor controller for bacterial protein expression"*
(PeerJ Preprints, doi:10.7287/peerj.preprints.27150v1), con mejoras de
autonomía, seguridad y trazabilidad descritas en `MEJORAS.md`.

## Arquitectura

```
[Arduino Mega/Uno]  <--serial-->  [controlfisicoV2.py]  <--MySQL-->  [monitoreoV2.py + web SCADA]
  codigotesisV3.ino      Dashboard de escritorio            Clever Cloud    Monitoreo remoto
  (control autónomo)     (CustomTkinter, login, P&ID)                       (FastAPI/Starlette)
```

- **Firmware (`codigotesisV3.ino`)**: lee pH, OD600 y temperatura;
  controla 6 relés (calefactor, bomba de pH, bomba de IPTG, bomba de
  cosecha, agitador, bomba de aire); ejecuta la máquina de etapas del
  cultivo de forma autónoma (no depende de que la PC esté conectada).
- **Control físico (`controlfisicoV2.py`)**: aplicación de escritorio
  con login (bcrypt + MySQL), diagrama P&ID animado, gráficas en vivo,
  calibración de sensores y paro de emergencia.
- **Monitoreo web (`monitoreoV2.py`)**: capa de acceso a datos para un
  SCADA web remoto sobre la misma base MySQL.

## Mapeo de relés

| Relé | Pin Arduino | Actuador |
|---|---|---|
| 1 | 2 | Calefactor (HT1) |
| 2 | 3 | Bomba de pH (NaOH) |
| 3 | 4 | Bomba de IPTG |
| 4 | 5 | Bomba de cosecha |
| 5 | 6 | Agitador (M2) |
| 6 | 7 | Bomba de aire |

Otros pines: bus OneWire (temperatura) en el pin 8, pH en A1, OD600 en
A2. No hay botón de paro de emergencia físico cableado; el paro de
emergencia es por software (`STOP`/`RESUME` vía serial).

## Protocolo serial (9600 baudios)

### Telemetría automática (cada 1 s, sin solicitarla)
```
TEMP,PH,OD600
```
Ejemplo: `37.02,7.05,0.842`

### Comandos que ya existían (V2)
| Comando | Efecto |
|---|---|
| `RELE:n,ON` / `RELE:n,OFF` | Fuerza el relé n (1-6). Ahora es temporal: revierte a control automático a los 60 s. |
| `RAW` | Devuelve voltaje crudo de pH y OD600. |
| `CALGET` | Devuelve la calibración lineal actual (pH, OD, offset de temp). |
| `CAL:PH:slope,intercept` | Calibra pH: `pH = slope*V + intercept`. |
| `CAL:OD:slope,intercept` | Calibra OD600 lineal: `OD = slope*V + intercept`. |
| `CAL:TEMP:offset` | Offset aditivo de temperatura. |

### Comandos nuevos (V3)
| Comando | Efecto |
|---|---|
| `START` | Pasa de READY a GROWING; captura el blanco de OD600 (L0). |
| `STOP` | Paro de emergencia por software: apaga todo de inmediato. |
| `RESUME` | Reanuda tras un `STOP`. |
| `RESET` | Vuelve a READY para un nuevo lote (solo si no está en emergencia). |
| `BLANK` | Recaptura el blanco (L0) de OD600 sin reiniciar el lote. |
| `PING` | Heartbeat simple; responde `PONG`. |
| `STAGEGET` | Devuelve etapa actual, si ya se indujo con IPTG, y estado de emergencia. |
| `DOSISGET` | Devuelve el volumen total de NaOH dosificado (mL) en el lote actual. |
| `ODLOGGET` | Devuelve OD600 calculado por razón logarítmica (Beer-Lambert). |
| `CONFIGGET` | Devuelve todos los parámetros de proceso configurables. |
| `CONFIG:TEMP:x` | Setpoint de temperatura (°C). |
| `CONFIG:PHMIN:x` / `CONFIG:PHMAX:x` | Rango de pH objetivo. |
| `CONFIG:ODIND:x` | OD600 al que se dispara la inducción con IPTG (default 0.7, igual que el paper). |
| `CONFIG:ODCOS:x` | OD600 al que se dispara la cosecha (default 2.0, igual que el paper). |
| `CONFIG:DOSISUL:x` | Volumen inicial de cada dosis de NaOH (µL). |
| `CONFIG:IPTGMS:x` | Duración del pulso de la bomba de IPTG (ms). |
| `CONFIG:HARVESTMIN:x` | Duración de la bomba de cosecha (minutos). |
| `CONFIG:FLOWPH:x` | Caudal calibrado de la bomba de pH (µL/s). |

## Seguridad

- **Paro de emergencia por software**: el comando `STOP` apaga todo de
  inmediato y bloquea el control automático hasta un `RESUME`. No hay
  botón físico cableado en este montaje.
- **Failsafe de override manual**: cualquier `RELE:n,ON/OFF` expira a
  los 60 segundos y el relé vuelve a control automático, para que una
  prueba manual olvidada (o una PC que se cuelga a media prueba) no
  deje una bomba o el calefactor encendidos indefinidamente.
- **Autonomía**: el ciclo completo del cultivo (calentamiento,
  dosificación de pH, inducción, cosecha) corre en el Arduino. Si se
  pierde la conexión serial/PC/BD, el cultivo sigue controlado.

## Ver también

- `MEJORAS.md` — bitácora de mejoras, priorizadas, con estado de cada
  una y pasos pendientes.
- `respaldo_local.py` — respaldo local en CSV cuando MySQL no responde.
- `migraciones.sql` — cambios de esquema para registrar etapa y dosis.
