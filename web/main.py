import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from routes.auth_routes import router as auth_router
from routes.dashboard_routes import router as dashboard_router
from routes.ws_routes import router as ws_router

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="SCADA Biorreactor Web")

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
