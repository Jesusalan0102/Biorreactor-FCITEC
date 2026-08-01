from fastapi import APIRouter, Request, Form
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse

import db
from deps import templates, usuario_logueado

router = APIRouter()


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
    ok = await run_in_threadpool(db.validar_usuario, username.strip(), password.strip())
    if ok:
        request.session["username"] = username.strip()
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Credenciales incorrectas o no se pudo alcanzar la base de datos"},
        status_code=401,
    )


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
