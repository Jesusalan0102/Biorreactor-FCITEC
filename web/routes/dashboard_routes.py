from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

import db
from deps import templates, requiere_login, usuario_logueado

router = APIRouter()


@router.get("/")
async def dashboard(request: Request):
    redir = requiere_login(request)
    if redir:
        return redir
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "username": usuario_logueado(request)}
    )


@router.post("/api/paro")
async def api_paro(request: Request):
    if not usuario_logueado(request):
        return JSONResponse({"ok": False, "error": "No autenticado"}, status_code=401)

    ok = await run_in_threadpool(db.activar_paro)
    if ok:
        await run_in_threadpool(
            db.registrar_evento,
            f"!!! PARO DE EMERGENCIA ENVIADO DESDE SCADA WEB por {usuario_logueado(request)} !!!",
        )
        return {"ok": True}
    return JSONResponse({"ok": False, "error": "No se pudo activar el paro"}, status_code=500)


@router.post("/api/reanudar")
async def api_reanudar(request: Request):
    if not usuario_logueado(request):
        return JSONResponse({"ok": False, "error": "No autenticado"}, status_code=401)

    ok = await run_in_threadpool(db.reanudar_sistema)
    if ok:
        await run_in_threadpool(
            db.registrar_evento,
            f">>> SOLICITUD DE REANUDACIÓN ENVIADA DESDE SCADA WEB por {usuario_logueado(request)} <<<",
        )
        return {"ok": True}
    return JSONResponse({"ok": False, "error": "No se pudo reanudar"}, status_code=500)


@router.post("/api/limpiar-datos")
async def api_limpiar_datos(request: Request):
    """Dispara manualmente la limpieza de retención (normalmente corre
    sola una vez al día). Útil para probarla sin esperar 24h."""
    if not usuario_logueado(request):
        return JSONResponse({"ok": False, "error": "No autenticado"}, status_code=401)

    resultado = await run_in_threadpool(db.limpiar_datos_antiguos)
    return resultado
