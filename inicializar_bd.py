"""inicializar_bd.py - Crea las tablas del biorreactor en una base MySQL nueva y, si quieres,
tu primer usuario. Lee las credenciales del archivo .env (el mismo de controlfisicoV2.py).

    python inicializar_bd.py                       # crea tablas y pregunta si quieres un usuario
    python inicializar_bd.py --usuario alan        # crea/actualiza ese usuario (pide la contraseña)
"""
import argparse
import getpass
import os
import re
import sys

import bcrypt
import pymysql
from dotenv import load_dotenv

load_dotenv(override=True)
AQUI = os.path.dirname(os.path.abspath(__file__))


def conectar(con_base=True):
    kwargs = dict(host=os.getenv("DB_HOST"), user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
                  port=int(os.getenv("DB_PORT", "3306")), connect_timeout=15, charset="utf8mb4")
    if con_base:
        kwargs["database"] = os.getenv("DB_NAME")
    ca = os.getenv("DB_SSL_CA")
    if ca:
        if not os.path.isabs(ca):   # ruta relativa: se busca junto a este archivo
            ca = os.path.join(AQUI, ca)
        kwargs["ssl_ca"] = ca
    elif os.getenv("DB_SSL", "").lower() in ("1", "true", "yes", "si", "sí"):
        kwargs["ssl_verify_cert"] = True   # cifrado sin CA propia (equivale a no verificar el certificado)
    return pymysql.connect(**kwargs)


def sentencias(sql):
    sin_comentarios = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    return [s.strip() for s in re.split(r";\s*(?:\n|$)", sin_comentarios) if s.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--usuario", help="nombre del usuario a crear (o cuya contraseña se actualiza)")
    args = ap.parse_args()
    if os.getenv("DB_PASSWORD", "").startswith("PON_AQUI"):
        sys.exit("Abre el archivo .env y cambia DB_PASSWORD por la contraseña de tu base de datos.")
    faltan = [k for k in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME") if not os.getenv(k)]
    if faltan:
        sys.exit(f"Faltan variables en el .env: {', '.join(faltan)}")
    nombre = os.getenv("DB_NAME", "")
    if not re.fullmatch(r"[A-Za-z0-9_]+", nombre):
        sys.exit("DB_NAME solo puede tener letras, números y guion bajo.")
    try:
        # Se conecta sin elegir base para poder crearla si todavía no existe.
        conn = conectar(con_base=False)
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{nombre}` CHARACTER SET utf8mb4")
            cur.execute(f"USE `{nombre}`")
        conn.commit()
    except Exception as e:
        sys.exit(f"No se pudo conectar o crear la base de datos '{nombre}': {e}")
    with conn.cursor() as cur:
        with open(os.path.join(AQUI, "schema_bd.sql"), encoding="utf-8") as f:
            for s in sentencias(f.read()):
                cur.execute(s)
        conn.commit()
        # Migración para bases creadas con la versión anterior (6 relés): agrega rele7 si falta.
        for tabla in ("datos_bioreactor", "sistema_control"):
            cur.execute(f"SHOW COLUMNS FROM {tabla} LIKE 'rele7'")
            if not cur.fetchone():
                cur.execute(f"ALTER TABLE {tabla} ADD COLUMN rele7 TINYINT(1) NOT NULL DEFAULT 0")
                print(f"Migración: columna rele7 agregada a {tabla}.")
        conn.commit()
        cur.execute("SHOW TABLES")
        print("Tablas listas:", ", ".join(r[0] for r in cur.fetchall()))
        usuario = args.usuario
        if not usuario and sys.stdin.isatty():
            usuario = input("Usuario a crear (Enter para omitir): ").strip() or None
        if usuario:
            pwd = os.getenv("NUEVO_PASSWORD") or getpass.getpass(f"Contraseña para '{usuario}': ")
            if not pwd:
                sys.exit("La contraseña no puede estar vacía.")
            h = bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            cur.execute("SELECT id FROM usuarios WHERE username=%s", (usuario,))
            if cur.fetchone():
                cur.execute("UPDATE usuarios SET password=%s WHERE username=%s", (h, usuario))
                print(f"Contraseña actualizada para '{usuario}'.")
            else:
                cur.execute("INSERT INTO usuarios (username, password) VALUES (%s, %s)", (usuario, h))
                print(f"Usuario '{usuario}' creado.")
            conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
