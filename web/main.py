import os
import asyncio
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

import db
from routes.auth_routes import router as auth_router
from routes.dashboard_routes import router as dashboard_router
from routes.ws_routes import router as ws_router

BASE_DIR = Path(__file__).resolve().parent

SEGUNDOS_ENTRE_LIMPIEZAS = 24 * 60 * 60  # una vez al día


async def _tarea_limpieza_periodica():
    """Corre en segundo plano mientras la app viva. Espera un rato al
    arrancar (para no competir con el primer tráfico de deploy) y luego
    limpia datos viejos una vez al día. Si un ciclo falla, no mata la
    tarea - lo reintenta en el siguiente ciclo."""
    await asyncio.sleep(60)
    while True:
        try:
            await run_in_threadpool(db.limpiar_datos_antiguos)
        except Exception as e:
            print(f"[CLEANUP] Error inesperado en limpieza periódica: {e}")
        await asyncio.sleep(SEGUNDOS_ENTRE_LIMPIEZAS)


app = FastAPI(title="SCADA Biorreactor Web")


@app.on_event("startup")
async def _iniciar_tarea_limpieza():
    asyncio.create_task(_tarea_limpieza_periodica())


app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "cambia-esta-clave-en-produccion"),
    session_cookie="scada_session",
    max_age=60 * 60 * 8,  # 8 horas
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
