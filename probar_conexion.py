"""probar_conexion.py - Diagnostica la conexión a la base de datos leyendo el .env (no muestra la contraseña)."""
import os
import sys

import pymysql
from dotenv import load_dotenv

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA_ENV = os.path.join(AQUI, ".env")
previas = [k for k in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME") if k in os.environ]
load_dotenv(RUTA_ENV, override=True)

host, port = os.getenv("DB_HOST", ""), int(os.getenv("DB_PORT", "3306") or 3306)
user, pwd, base = os.getenv("DB_USER", ""), os.getenv("DB_PASSWORD", ""), os.getenv("DB_NAME", "")
ca = os.getenv("DB_SSL_CA", "")
if ca and not os.path.isabs(ca):
    ca = os.path.join(AQUI, ca)

print(f"Archivo .env leído: {RUTA_ENV}  ->  {'existe' if os.path.exists(RUTA_ENV) else 'NO EXISTE (crea el .env en esta carpeta)'}")
if previas:
    print(f"Aviso: Windows tiene variables de entorno ({', '.join(previas)}); aquí el .env tiene prioridad.")
print("=== Lo que la app lee de tu .env ===")
print(f"Host      : {host}")
print(f"Puerto    : {port}")
print(f"Usuario   : {user!r}  ({len(user)} caracteres)")
print(f"Contraseña: {len(pwd)} caracteres" + (f", empieza con '{pwd[0]}' y termina con '{pwd[-1]}'" if pwd else " (VACÍA)"))
print(f"Base      : {base}")
print(f"Certificado: {ca or '(ninguno)'} -> {'existe' if ca and os.path.exists(ca) else 'NO existe' if ca else ''}")

avisos = []
if not pwd or pwd.startswith("PON_AQUI"):
    avisos.append("La contraseña sigue siendo el texto de ejemplo o está vacía: edita DB_PASSWORD en el .env.")
if user != user.strip() or pwd != pwd.strip():
    avisos.append("El usuario o la contraseña tienen espacios al inicio o al final.")
if pwd[:1] in "'\"" or pwd[-1:] in "'\"":
    avisos.append("La contraseña parece incluir comillas dentro del valor.")
if " #" in pwd:
    avisos.append("La contraseña contiene ' #': el .env lo toma como comentario. Ponla entre comillas simples: DB_PASSWORD='...'.")
if any(c in pwd for c in "#$&\\") and not (pwd.startswith("'")):
    avisos.append("La contraseña tiene símbolos (# $ & \\). Si falla, ponla entre comillas simples en el .env: DB_PASSWORD='...'.")
if "tidbcloud" in host and not user.endswith(".root"):
    avisos.append("En TiDB Cloud el usuario lleva un prefijo y termina en .root (ej. 2abc123.root).")
if any(ord(c) > 127 for c in user):
    avisos.append("El usuario tiene caracteres raros: cópialo con el botón de copiar del panel de TiDB.")
for a in avisos:
    print("  ⚠", a)

kw = dict(host=host, port=port, user=user, password=pwd, connect_timeout=15)
if ca and os.path.exists(ca):
    kw["ssl_ca"] = ca
elif os.getenv("DB_SSL", "").lower() in ("1", "true", "yes", "si", "sí"):
    kw["ssl_verify_cert"] = True

print("\n=== Probando la conexión ===")
try:
    conn = pymysql.connect(database=base, **kw)
    with conn.cursor() as cur:
        cur.execute("SELECT VERSION()")
        print("✔ CONEXIÓN EXITOSA. Servidor:", cur.fetchone()[0])
        cur.execute("SHOW TABLES")
        tablas = [r[0] for r in cur.fetchall()]
        print("Tablas en", base + ":", ", ".join(tablas) if tablas else "(ninguna: ejecuta 2_crear_base_y_usuario.bat)")
    conn.close()
except pymysql.err.OperationalError as e:
    codigo = e.args[0]
    print(f"✘ Error {codigo}: {e.args[1]}")
    if codigo == 1045:
        print("\n→ El servidor sí respondió, pero rechazó el USUARIO o la CONTRASEÑA. Revisa, en este orden:")
        print("  1) En TiDB Cloud: Connect → 'Reset Password', copia la nueva contraseña con el botón de copiar.")
        print("  2) Pégala en el .env así, entre comillas simples y sin espacios:  DB_PASSWORD='tu_password'")
        print("  3) Copia el usuario con su botón de copiar (cuidado: l minúscula / I mayúscula, 0 / O).")
        print("  4) Usa la contraseña de la base de datos, no la de tu cuenta de TiDB Cloud.")
    elif codigo == 1049:
        print(f"\n→ La base '{base}' no existe. En el editor SQL de TiDB ejecuta: CREATE DATABASE IF NOT EXISTS {base};")
    elif codigo in (2003, 2013):
        print("\n→ No se alcanzó el servidor: revisa host/puerto (4000) y que tu IP esté en la lista permitida de TiDB.")
    sys.exit(1)
except Exception as e:
    print("✘ Error:", e)
    sys.exit(1)
