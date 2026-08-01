from pathlib import Path
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.responses import RedirectResponse

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def usuario_logueado(request: Request):
    return request.session.get("username")


def requiere_login(request: Request):
    """Dependencia para rutas HTTP: si no hay sesión, redirige a /login.
    Uso: if (redir := requiere_login(request)): return redir"""
    if not usuario_logueado(request):
        return RedirectResponse(url="/login", status_code=303)
    return None
