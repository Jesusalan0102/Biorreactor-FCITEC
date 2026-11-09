# Desplegar el SCADA web en Render

1. render.com -> **New + -> Blueprint** -> elige este repo (usa `render.yaml`).
   (Alternativa manual: New + -> Web Service, **Root Directory** `web`,
   Build `pip install -r requirements.txt`,
   Start `uvicorn main:app --host 0.0.0.0 --port $PORT`.)
2. En **Environment** captura: `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
   (`DB_PORT=3306` y `SESSION_SECRET` ya vienen en el blueprint).
3. Deploy. Verifica `https://<tu-app>.onrender.com/health` -> `{"status":"ok"}`
   y luego `/login`.

Notas:
- Plan Free: el servicio se duerme tras ~15 min sin trafico (primer acceso ~50 s).
- La BD sigue en Clever Cloud (MySQL); revisa el limite de conexiones del add-on.
- El Arduino / `controlfisicoV2.py` corre en tu PC y escribe a la BD; Render solo
  sirve el monitoreo web.
