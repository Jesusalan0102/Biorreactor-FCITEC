# Desplegar en Clever Cloud

## 1. Sube este código a tu repo de GitHub
Puedes ponerlo en una carpeta nueva dentro de `Biorreactor-FCITEC` (ej. `web/`) o en un repo aparte —
recomiendo un repo/carpeta aparte para no mezclar con el código de escritorio (Arduino/tkinter).

## 2. Crear la app en Clever Cloud
1. Dashboard de Clever Cloud → **Create** → **An application** → **Python**.
2. Nómbrala, por ejemplo `biorreactor-scada-web`.
3. Conecta el repositorio de GitHub (o el subárbol donde quede este proyecto) y la rama a desplegar.

## 3. Variables de entorno (Console → tu app → Environment variables)
Copia los mismos valores que ya usa tu app de escritorio, pero como variables de entorno (no hardcodeadas):

| Variable         | Valor                                                          |
|------------------|------------------------------------------------------------------|
| `DB_HOST`        | `bfn0iql8vbpvwgbmq9zk-mysql.services.clever-cloud.com`           |
| `DB_USER`        | `unluguvpazazzigt`                                                |
| `DB_PASSWORD`    | *(la contraseña real — idealmente rotada, ver nota de seguridad)*|
| `DB_NAME`        | `bfn0iql8vbpvwgbmq9zk`                                            |
| `DB_PORT`        | `3306`                                                            |
| `SESSION_SECRET` | una cadena aleatoria larga (ver `.env.example`)                  |
| `CC_PYTHON_BACKEND` | `uvicorn`                                                      |
| `CC_PYTHON_MODULE`  | `main:app`                                                     |

> Si compartes la misma base de datos MySQL con `carrier-transicold`, no hay problema — son tablas
> distintas (`usuarios`, `datos_bioreactor`, `sistema_control`, `eventos`). Solo confirma que el add-on
> de MySQL no tenga un límite de conexiones simultáneas muy bajo si ambas apps van a estar activas
> al mismo tiempo (los add-ons gratuitos suelen tener pocas conexiones).

## 4. Dominio
En **Domain names**, agrega tu dominio propio o usa el subdominio `*.cleverapps.io` que te asigna
Clever Cloud por defecto.

## 5. Deploy
Con el repo conectado, cada push a la rama configurada dispara el deploy automáticamente. También
puedes usar `clever deploy` con el CLI si prefieres tu flujo actual.

## 6. Verificación
- `https://tu-dominio/health` → debe responder `{"status":"ok"}`
- `https://tu-dominio/login` → debe mostrar el formulario de acceso
- Inicia sesión con un usuario existente en tu tabla `usuarios`

---

## Nota de seguridad (importante)
Antes de subir esto a producción, rota la contraseña de MySQL en el dashboard de Clever Cloud —
la que está en el código actual (`monitoreoV2.py` / `controlfisicoV2.py`) quedó expuesta en el
repo público. Actualiza `DB_PASSWORD` aquí con la nueva contraseña y, cuando conviertas
`controlfisicoV2.py` en el agente local, usa ahí también variables de entorno en vez de
hardcodear credenciales.
