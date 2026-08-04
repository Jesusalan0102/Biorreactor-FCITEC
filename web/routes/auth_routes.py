import time
from fastapi import APIRouter, Request, Form
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse

import db
from deps import templates, usuario_logueado

router = APIRouter()

# Rate limiting simple en memoria: {ip: [timestamps de intentos fallidos]}
# Se reinicia si la app se redespliega/reinicia - suficiente para un
# proyecto de tesis de una sola instancia. Si migran a multi-instancia,
# esto habría que moverlo a la BD o a Redis.
_INTENTOS_FALLIDOS: dict[str, list[float]] = {}
MAX_INTENTOS = 5
VENTANA_BLOQUEO_SEG = 5 * 60  # 5 minutos


def _ip_bloqueada(ip: str) -> tuple[bool, int]:
    ahora = time.time()
    intentos = _INTENTOS_FALLIDOS.get(ip, [])
    intentos = [t for t in intentos if ahora - t < VENTANA_BLOQUEO_SEG]
    _INTENTOS_FALLIDOS[ip] = intentos
    if len(intentos) >= MAX_INTENTOS:
        restante = int(VENTANA_BLOQUEO_SEG - (ahora - intentos[0]))
        return True, max(restante, 1)
    return False, 0


def _registrar_fallo(ip: str):
    _INTENTOS_FALLIDOS.setdefault(ip, []).append(time.time())


def _limpiar_intentos(ip: str):
    _INTENTOS_FALLIDOS.pop(ip, None)


@router.get("/login")
async def login_form(request: Request):
    if usuario_logueado(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": None}
    )


@router.post("/login")
async def login_submit(
    request: Request, username: str = Form(...), password: str = Form(...)
):
    ip = request.client.host if request.client else "desconocida"

    bloqueada, restante_seg = _ip_bloqueada(ip)
    if bloqueada:
        minutos = max(restante_seg // 60, 1)
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": f"Demasiados intentos fallidos. Intenta de nuevo en ~{minutos} min.",
            },
            status_code=429,
        )

    ok = await run_in_threadpool(db.validar_usuario, username.strip(), password.strip())
    if ok:
        _limpiar_intentos(ip)
        request.session["username"] = username.strip()
        return RedirectResponse(url="/", status_code=303)

    _registrar_fallo(ip)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Credenciales incorrectas o no se pudo alcanzar la base de datos"},
        status_code=401,
    )


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
