import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

import db

router = APIRouter()

INTERVALO_SEG = 2.5  # frecuencia de actualización push al navegador


@router.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket):
    # SessionMiddleware también puebla websocket.session a partir de la
    # cookie de sesión, así que reusamos el mismo login que las rutas HTTP.
    if not websocket.session.get("username"):
        await websocket.close(code=4401)
        return

    await websocket.accept()
    try:
        while True:
            estado = await run_in_threadpool(db.obtener_estado_actual, 20)
            eventos = await run_in_threadpool(db.obtener_eventos, 15)
            await websocket.send_json({"estado": estado, "eventos": eventos})
            await asyncio.sleep(INTERVALO_SEG)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS] Error en loop de dashboard: {e}")
