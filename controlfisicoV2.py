import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
from PIL import Image
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import serial
import serial.tools.list_ports
import threading
import time
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import pymysql
import bcrypt
from dotenv import load_dotenv

TZ_TIJUANA = ZoneInfo("America/Tijuana")

load_dotenv()

# Configuración base de datos (Clever Cloud) - se cargan desde variables de
# entorno / archivo .env, NUNCA hardcodeadas en el código fuente.
DB_HOST = os.environ.get("DB_HOST", "")
DB_USER = os.environ.get("DB_USER", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
CLAVE_MAESTRA = os.environ.get("CLAVE_MAESTRA", "")

if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, CLAVE_MAESTRA]):
    print("[ADVERTENCIA] Faltan variables de entorno de base de datos o CLAVE_MAESTRA. "
          "Crea un archivo .env junto a este script (ver .env.example).")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# --- Paleta unificada con el SCADA web (misma identidad visual) ---
COLOR_FONDO = "#0d1b2a"
COLOR_FONDO_GRAD = "#142d5a"
COLOR_PANEL = "#0f3460"
COLOR_TARJETA = "#16233a"
COLOR_AZUL = "#1A73E8"
COLOR_AZUL_HOVER = "#1557B0"
COLOR_AZUL_OSCURO = "#0D47A1"
COLOR_VERDE = "#2ECC71"
COLOR_VERDE_HOVER = "#27ae60"
COLOR_ROJO = "#E74C3C"
COLOR_ROJO_HOVER = "#c0392b"
COLOR_AMARILLO = "#F4B400"
COLOR_TEXTO = "#EAF2FB"
COLOR_TEXTO_SUAVE = "#9fc0e8"
FUENTE = "Segoe UI"

# --- Paleta "industrial" para el Dashboard de control (look de HMI/SCADA físico) ---
COLOR_ACERO = "#15181f"          # panel principal, como chasis metálico
COLOR_ACERO_CLARO = "#1f2430"    # paneles secundarios / tarjetas de instrumento
COLOR_ACERO_BORDE = "#3a4152"    # bordes tipo remache/metal
COLOR_AMARILLO_PELIGRO = "#FFC107"
COLOR_NEGRO_PELIGRO = "#111111"
COLOR_LED_ON = "#39FF14"         # verde neón encendido
COLOR_LED_OFF = "#454b58"        # gris apagado
COLOR_LED_ALERTA = "#FF3B30"
COLOR_LED_ALERTA_OFF = "#5a2a26"
COLOR_DIGITAL_FONDO = "#050705"
COLOR_DIGITAL_TEXTO = "#39FF14"
FUENTE_DIGITAL = "Consolas"


class ModalBase(ctk.CTkToplevel):
    """Base para reemplazar messagebox/simpledialog con algo que combine
    con el resto de la app (tarjeta oscura redondeada, sin chrome de Windows)."""
    def __init__(self, parent, titulo):
        super().__init__(parent)
        self.title("")
        self.configure(fg_color=COLOR_FONDO)
        self.overrideredirect(True)  # sin barra de título nativa de Windows
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.result = None

        self.card = ctk.CTkFrame(self, fg_color=COLOR_TARJETA, corner_radius=20,
                                  border_width=2, border_color=COLOR_AZUL)
        self.card.pack(padx=2, pady=2, fill="both", expand=True)

        ctk.CTkLabel(self.card, text=titulo, font=(FUENTE, 17, "bold"),
                     text_color=COLOR_TEXTO).pack(pady=(22, 4), padx=30)

        self.bind("<Escape>", lambda e: self._cerrar())

    def _centrar(self, ancho=380, alto=220):
        self.update_idletasks()
        parent = self.master
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x = px + (pw - ancho) // 2
        y = py + (ph - alto) // 2
        self.geometry(f"{ancho}x{alto}+{x}+{y}")

    def _cerrar(self):
        self.grab_release()
        self.destroy()


class ModalMensaje(ModalBase):
    """Reemplaza messagebox.showinfo / showerror / showwarning."""
    COLORES = {"info": COLOR_AZUL, "exito": COLOR_VERDE, "error": COLOR_ROJO, "aviso": COLOR_AMARILLO}
    ICONOS = {"info": "ℹ", "exito": "✓", "error": "✕", "aviso": "⚠"}

    def __init__(self, parent, titulo, mensaje, tipo="info"):
        super().__init__(parent, "")
        color = self.COLORES.get(tipo, COLOR_AZUL)
        self.card.configure(border_color=color)

        ctk.CTkLabel(self.card, text=self.ICONOS.get(tipo, "ℹ"), font=(FUENTE, 30, "bold"),
                     text_color=color).pack(pady=(18, 0))
        ctk.CTkLabel(self.card, text=titulo, font=(FUENTE, 16, "bold"),
                     text_color=COLOR_TEXTO).pack(pady=(6, 4), padx=30)
        ctk.CTkLabel(self.card, text=mensaje, font=(FUENTE, 13), text_color=COLOR_TEXTO_SUAVE,
                     wraplength=320, justify="center").pack(pady=(0, 18), padx=30)
        ctk.CTkButton(self.card, text="Aceptar", fg_color=color, hover_color=color,
                      corner_radius=12, width=140, command=self._cerrar).pack(pady=(0, 22))

        self._centrar(380, 240)
        self.grab_set()
        self.wait_window()


class ModalConfirmar(ModalBase):
    """Reemplaza messagebox.askyesno."""
    def __init__(self, parent, titulo, mensaje):
        super().__init__(parent, "")
        self.card.configure(border_color=COLOR_ROJO)

        ctk.CTkLabel(self.card, text="⚠", font=(FUENTE, 30, "bold"),
                     text_color=COLOR_ROJO).pack(pady=(18, 0))
        ctk.CTkLabel(self.card, text=titulo, font=(FUENTE, 16, "bold"),
                     text_color=COLOR_TEXTO).pack(pady=(6, 4), padx=30)
        ctk.CTkLabel(self.card, text=mensaje, font=(FUENTE, 13), text_color=COLOR_TEXTO_SUAVE,
                     wraplength=320, justify="center").pack(pady=(0, 18), padx=30)

        botones = ctk.CTkFrame(self.card, fg_color="transparent")
        botones.pack(pady=(0, 22))
        ctk.CTkButton(botones, text="Cancelar", fg_color=COLOR_PANEL, hover_color="#1c3a66",
                      corner_radius=12, width=110, command=self._no).pack(side="left", padx=8)
        ctk.CTkButton(botones, text="Confirmar", fg_color=COLOR_ROJO, hover_color=COLOR_ROJO_HOVER,
                      corner_radius=12, width=110, command=self._si).pack(side="left", padx=8)

        self._centrar(380, 260)
        self.grab_set()
        self.wait_window()

    def _si(self):
        self.result = True
        self._cerrar()

    def _no(self):
        self.result = False
        self._cerrar()


class ModalTexto(ModalBase):
    """Reemplaza simpledialog.askstring."""
    def __init__(self, parent, titulo, mensaje, show=None):
        super().__init__(parent, "")
        self.card.configure(border_color=COLOR_AZUL)

        ctk.CTkLabel(self.card, text=titulo, font=(FUENTE, 16, "bold"),
                     text_color=COLOR_TEXTO).pack(pady=(20, 4), padx=30)
        ctk.CTkLabel(self.card, text=mensaje, font=(FUENTE, 12), text_color=COLOR_TEXTO_SUAVE,
                     wraplength=320, justify="center").pack(pady=(0, 10), padx=30)

        self.entry = ctk.CTkEntry(self.card, width=280, height=42, corner_radius=12,
                                   fg_color=COLOR_FONDO, border_color=COLOR_AZUL,
                                   font=(FUENTE, 14), show=show or "")
        self.entry.pack(pady=(0, 18))
        self.entry.bind("<Return>", lambda e: self._ok())

        botones = ctk.CTkFrame(self.card, fg_color="transparent")
        botones.pack(pady=(0, 22))
        ctk.CTkButton(botones, text="Cancelar", fg_color=COLOR_PANEL, hover_color="#1c3a66",
                      corner_radius=12, width=110, command=self._cancelar).pack(side="left", padx=8)
        ctk.CTkButton(botones, text="Aceptar", fg_color=COLOR_AZUL, hover_color=COLOR_AZUL_HOVER,
                      corner_radius=12, width=110, command=self._ok).pack(side="left", padx=8)

        self._centrar(380, 280)
        self.entry.focus()
        self.grab_set()
        self.wait_window()

    def _ok(self):
        self.result = self.entry.get()
        self._cerrar()

    def _cancelar(self):
        self.result = None
        self._cerrar()


def mostrar_info(parent, titulo, mensaje):
    ModalMensaje(parent, titulo, mensaje, tipo="info")


def mostrar_exito(parent, titulo, mensaje):
    ModalMensaje(parent, titulo, mensaje, tipo="exito")


def mostrar_error(parent, titulo, mensaje):
    ModalMensaje(parent, titulo, mensaje, tipo="error")


def mostrar_aviso(parent, titulo, mensaje):
    ModalMensaje(parent, titulo, mensaje, tipo="aviso")


def confirmar(parent, titulo, mensaje):
    return bool(ModalConfirmar(parent, titulo, mensaje).result)


def pedir_texto(parent, titulo, mensaje, show=None):
    return ModalTexto(parent, titulo, mensaje, show=show).result


def estilizar_treeview_oscuro():
    """ttk.Treeview no sigue el tema de CustomTkinter por defecto y se ve
    con estilo Windows clásico; lo forzamos a la paleta oscura del SCADA."""
    estilo = ttk.Style()
    estilo.theme_use("clam")
    estilo.configure(
        "Oscuro.Treeview",
        background=COLOR_TARJETA,
        fieldbackground=COLOR_TARJETA,
        foreground=COLOR_TEXTO,
        rowheight=32,
        borderwidth=0,
        font=(FUENTE, 12),
    )
    estilo.configure(
        "Oscuro.Treeview.Heading",
        background=COLOR_PANEL,
        foreground=COLOR_TEXTO_SUAVE,
        borderwidth=0,
        font=(FUENTE, 12, "bold"),
    )
    estilo.map(
        "Oscuro.Treeview",
        background=[("selected", COLOR_AZUL)],
        foreground=[("selected", "white")],
    )
    estilo.layout("Oscuro.Treeview", [("Oscuro.Treeview.treearea", {"sticky": "nswe"})])


def verificar_password(pwd_ingresada, pwd_guardada):
    """Verifica con bcrypt; si la columna aún no está migrada (texto plano), compara directo."""
    try:
        return bcrypt.checkpw(pwd_ingresada.encode("utf-8"), pwd_guardada.encode("utf-8"))
    except (ValueError, AttributeError):
        return pwd_ingresada == pwd_guardada


def conectar_db():
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            connect_timeout=8
        )
        print("¡CONEXIÓN ÉXITO con PyMySQL!")
        return conn
    except Exception as e:
        print("ERROR en PyMySQL:", str(e))
        return None


def asegurar_tabla_calibracion():
    """Crea la tabla de calibración si no existe. La BD es la fuente de
    verdad de la calibración; el Arduino solo aplica lo último que se le
    envía (ver sincronizar_calibracion_inicial)."""
    conn = conectar_db()
    if not conn:
        print("[BD] No se pudo verificar/crear tabla calibracion_sensores")
        return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS calibracion_sensores (
                id INT AUTO_INCREMENT PRIMARY KEY,
                sensor VARCHAR(20) NOT NULL,
                slope FLOAT NOT NULL,
                intercept FLOAT NOT NULL,
                fecha_calibracion DATETIME NOT NULL,
                usuario_id INT NULL,
                notas VARCHAR(255) NULL
            )
        """)
        conn.commit()
    except Exception as e:
        print(f"[ERROR BD] No se pudo crear tabla calibracion_sensores: {e}")
    finally:
        conn.close()


class LoginApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Control Bioreactor")
        self.configure(fg_color=COLOR_FONDO)
        self.update_idletasks()
        w = self.winfo_screenwidth()
        h = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+0+0")

        estilizar_treeview_oscuro()

        # Fondo con gradiente simulado (canvas), igual que el login web
        self.fondo = tk.Canvas(self, highlightthickness=0, bd=0)
        self.fondo.place(x=0, y=0, relwidth=1, relheight=1)
        self._pintar_gradiente()
        self.bind("<Configure>", lambda e: self._pintar_gradiente())

        # --- Tarjeta central ---
        self.tarjeta = ctk.CTkFrame(self, fg_color=COLOR_TARJETA, corner_radius=28,
                                     border_width=2, border_color=COLOR_AZUL, width=460)
        self.tarjeta.place(relx=0.5, rely=0.5, anchor="center")

        try:
            logo_pil = Image.open("logo.png")
            logo_pil = logo_pil.resize((260, 150))
            self.logo = ctk.CTkImage(light_image=logo_pil, dark_image=logo_pil, size=(260, 150))
            ctk.CTkLabel(self.tarjeta, image=self.logo, text="").pack(pady=(28, 4))
        except Exception as e:
            print(f"No se pudo cargar logo: {e}")
            ctk.CTkLabel(self.tarjeta, text="🧪 BIOREACTOR", font=(FUENTE, 26, "bold"),
                         text_color=COLOR_AZUL).pack(pady=(36, 4))

        ctk.CTkLabel(self.tarjeta, text="CONTROL FÍSICO", font=(FUENTE, 22, "bold"),
                     text_color=COLOR_TEXTO).pack(pady=(0, 22))

        tabview = ctk.CTkTabview(
            self.tarjeta, width=380, height=300, corner_radius=18,
            fg_color=COLOR_FONDO, segmented_button_fg_color=COLOR_PANEL,
            segmented_button_selected_color=COLOR_AZUL,
            segmented_button_selected_hover_color=COLOR_AZUL_HOVER,
            segmented_button_unselected_color=COLOR_PANEL,
            text_color=COLOR_TEXTO,
        )
        tabview.pack(padx=30, pady=(0, 30))

        tab_login = tabview.add("Iniciar Sesión")
        tab_admin = tabview.add("Administrar")

        # --- Tab login ---
        ctk.CTkLabel(tab_login, text="USUARIO", font=(FUENTE, 11, "bold"),
                     text_color=COLOR_TEXTO_SUAVE, anchor="w").pack(fill="x", padx=6, pady=(18, 2))
        self.username_entry = ctk.CTkEntry(tab_login, width=320, height=42, corner_radius=12,
                                            fg_color=COLOR_TARJETA, border_color=COLOR_AZUL,
                                            font=(FUENTE, 14))
        self.username_entry.pack(padx=6)

        ctk.CTkLabel(tab_login, text="CONTRASEÑA", font=(FUENTE, 11, "bold"),
                     text_color=COLOR_TEXTO_SUAVE, anchor="w").pack(fill="x", padx=6, pady=(16, 2))
        self.password_entry = ctk.CTkEntry(tab_login, width=320, height=42, corner_radius=12,
                                            fg_color=COLOR_TARJETA, border_color=COLOR_AZUL,
                                            font=(FUENTE, 14), show="•")
        self.password_entry.pack(padx=6)
        self.password_entry.bind("<Return>", lambda e: self.verificar_login())

        ctk.CTkButton(tab_login, text="INICIAR SESIÓN", height=46, corner_radius=14,
                      fg_color=COLOR_AZUL, hover_color=COLOR_AZUL_HOVER,
                      font=(FUENTE, 14, "bold"), command=self.verificar_login).pack(pady=28, padx=6, fill="x")

        # --- Tab admin ---
        ctk.CTkLabel(tab_admin, text="CLAVE MAESTRA", font=(FUENTE, 11, "bold"),
                     text_color=COLOR_TEXTO_SUAVE, anchor="w").pack(fill="x", padx=6, pady=(18, 2))
        self.clave_entry = ctk.CTkEntry(tab_admin, width=320, height=42, corner_radius=12,
                                         fg_color=COLOR_TARJETA, border_color=COLOR_AZUL,
                                         font=(FUENTE, 14), show="•")
        self.clave_entry.pack(padx=6)
        self.clave_entry.bind("<Return>", lambda e: self.activar_admin())

        ctk.CTkButton(tab_admin, text="ACTIVAR ADMINISTRACIÓN", height=46, corner_radius=14,
                      fg_color=COLOR_PANEL, hover_color="#1c3a66",
                      font=(FUENTE, 14, "bold"), command=self.activar_admin).pack(pady=28, padx=6, fill="x")

        # --- Panel de administración (fuera del tabview, pantalla completa cuando se activa) ---
        self.admin_frame = ctk.CTkFrame(self, fg_color=COLOR_TARJETA, corner_radius=24,
                                         border_width=2, border_color=COLOR_AZUL)

    def _pintar_gradiente(self):
        """Dibuja un degradado vertical azul-oscuro → azul-noche, igual al fondo web."""
        self.fondo.delete("grad")
        alto = max(self.winfo_height(), 1)
        ancho = max(self.winfo_width(), 1)
        pasos = 60
        c1 = (0x0a, 0x14, 0x20)
        c2 = (0x14, 0x2d, 0x5a)
        for i in range(pasos):
            t = i / pasos
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)
            color = f"#{r:02x}{g:02x}{b:02x}"
            y0 = int(alto * i / pasos)
            y1 = int(alto * (i + 1) / pasos)
            self.fondo.create_rectangle(0, y0, ancho, y1, fill=color, outline=color, tags="grad")
        self.fondo.tag_lower("grad")

    def activar_admin(self):
        if self.clave_entry.get() == CLAVE_MAESTRA:
            self.tarjeta.place_forget()
            self.admin_frame.place(relx=0.5, rely=0.5, anchor="center",
                                    relwidth=0.7, relheight=0.8)
            self.listar_usuarios()
        else:
            mostrar_error(self, "Acceso denegado", "Clave maestra incorrecta")

    def cerrar_admin(self):
        self.admin_frame.place_forget()
        self.clave_entry.delete(0, "end")
        self.tarjeta.place(relx=0.5, rely=0.5, anchor="center")

    def listar_usuarios(self):
        # Limpiar contenido previo del frame
        for widget in self.admin_frame.winfo_children():
            widget.destroy()

        # --- Encabezado con título y botón de cerrar ---
        encabezado = ctk.CTkFrame(self.admin_frame, fg_color="transparent")
        encabezado.pack(fill="x", padx=24, pady=(20, 10))
        ctk.CTkLabel(encabezado, text="ADMINISTRAR USUARIOS", font=(FUENTE, 18, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left")
        ctk.CTkButton(encabezado, text="✕ Cerrar", width=90, height=32, corner_radius=10,
                      fg_color=COLOR_PANEL, hover_color="#1c3a66",
                      command=self.cerrar_admin).pack(side="right")

        conn = conectar_db()
        if not conn:
            ctk.CTkLabel(self.admin_frame, text="No se pudo conectar a la base de datos",
                         text_color=COLOR_ROJO).pack(pady=10)
            return

        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute("SELECT id, username FROM usuarios ORDER BY username")
            usuarios = cursor.fetchall()
        except Exception as e:
            ctk.CTkLabel(self.admin_frame, text=f"Error al consultar usuarios: {e}",
                         text_color=COLOR_ROJO).pack(pady=10)
            return
        finally:
            conn.close()

        # --- Tabla de usuarios (estilo oscuro) ---
        contenedor_tabla = ctk.CTkFrame(self.admin_frame, fg_color=COLOR_FONDO, corner_radius=14)
        contenedor_tabla.pack(fill="both", expand=True, padx=24, pady=(0, 12))

        tree = ttk.Treeview(contenedor_tabla, columns=("id", "username"), show="headings",
                             height=10, style="Oscuro.Treeview")
        tree.heading("id", text="ID")
        tree.heading("username", text="USUARIO")
        tree.column("id", width=70, anchor="center")
        tree.column("username", width=280, anchor="w")
        tree.pack(fill="both", expand=True, padx=10, pady=10)

        for u in usuarios:
            tree.insert("", "end", values=(u["id"], u["username"]))

        self.tree_usuarios = tree

        # --- Botonera de acciones ---
        botonera = ctk.CTkFrame(self.admin_frame, fg_color="transparent")
        botonera.pack(fill="x", padx=24, pady=(0, 22))

        ctk.CTkButton(
            botonera, text="＋  Agregar usuario", height=40, corner_radius=12,
            fg_color=COLOR_VERDE, hover_color=COLOR_VERDE_HOVER, font=(FUENTE, 13, "bold"),
            command=self.agregar_usuario
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            botonera, text="🔑  Cambiar contraseña", height=40, corner_radius=12,
            fg_color=COLOR_AZUL, hover_color=COLOR_AZUL_HOVER, font=(FUENTE, 13, "bold"),
            command=self.cambiar_password_usuario
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            botonera, text="🗑  Eliminar usuario", height=40, corner_radius=12,
            fg_color=COLOR_ROJO, hover_color=COLOR_ROJO_HOVER, font=(FUENTE, 13, "bold"),
            command=self.eliminar_usuario
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            botonera, text="↻  Refrescar", height=40, corner_radius=12,
            fg_color=COLOR_PANEL, hover_color="#1c3a66", font=(FUENTE, 13, "bold"),
            command=self.listar_usuarios
        ).pack(side="left", padx=8)

    def _usuario_seleccionado(self):
        """Devuelve (id, username) del usuario seleccionado en el Treeview, o None si no hay selección."""
        seleccion = self.tree_usuarios.selection()
        if not seleccion:
            mostrar_aviso(self, "Aviso", "Selecciona un usuario de la lista primero.")
            return None
        valores = self.tree_usuarios.item(seleccion[0], "values")
        return int(valores[0]), valores[1]

    def agregar_usuario(self):
        nuevo_user = pedir_texto(self, "Agregar usuario", "Nombre de usuario:")
        if not nuevo_user or not nuevo_user.strip():
            return
        nuevo_user = nuevo_user.strip()

        nueva_pwd = pedir_texto(self, "Agregar usuario", f"Contraseña para '{nuevo_user}':", show="•")
        if not nueva_pwd:
            return

        conn = conectar_db()
        if not conn:
            mostrar_error(self, "Error", "No se pudo conectar a la base de datos")
            return
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM usuarios WHERE username=%s", (nuevo_user,))
            if cursor.fetchone():
                mostrar_error(self, "Error", "Ese nombre de usuario ya existe")
                return
            hash_pwd = bcrypt.hashpw(nueva_pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            cursor.execute(
                "INSERT INTO usuarios (username, password) VALUES (%s, %s)", (nuevo_user, hash_pwd)
            )
            conn.commit()
            mostrar_exito(self, "Éxito", f"Usuario '{nuevo_user}' creado correctamente")
        except Exception as e:
            mostrar_error(self, "Error", f"No se pudo crear el usuario: {e}")
        finally:
            conn.close()

        self.listar_usuarios()

    def cambiar_password_usuario(self):
        seleccionado = self._usuario_seleccionado()
        if not seleccionado:
            return
        user_id, username = seleccionado

        nueva_pwd = pedir_texto(self, "Cambiar contraseña", f"Nueva contraseña para '{username}':", show="•")
        if not nueva_pwd:
            return
        confirmar_pwd = pedir_texto(self, "Cambiar contraseña", "Confirma la nueva contraseña:", show="•")
        if nueva_pwd != confirmar_pwd:
            mostrar_error(self, "Error", "Las contraseñas no coinciden")
            return

        conn = conectar_db()
        if not conn:
            mostrar_error(self, "Error", "No se pudo conectar a la base de datos")
            return
        try:
            cursor = conn.cursor()
            hash_pwd = bcrypt.hashpw(nueva_pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            cursor.execute("UPDATE usuarios SET password=%s WHERE id=%s", (hash_pwd, user_id))
            conn.commit()
            mostrar_exito(self, "Éxito", f"Contraseña de '{username}' actualizada")
        except Exception as e:
            mostrar_error(self, "Error", f"No se pudo actualizar la contraseña: {e}")
        finally:
            conn.close()

    def eliminar_usuario(self):
        seleccionado = self._usuario_seleccionado()
        if not seleccionado:
            return
        user_id, username = seleccionado

        if not confirmar(
            self, "Confirmar eliminación",
            f"¿Seguro que quieres eliminar al usuario '{username}'? Esta acción no se puede deshacer."
        ):
            return

        conn = conectar_db()
        if not conn:
            mostrar_error(self, "Error", "No se pudo conectar a la base de datos")
            return
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM usuarios WHERE id=%s", (user_id,))
            conn.commit()
            mostrar_exito(self, "Éxito", f"Usuario '{username}' eliminado")
        except Exception as e:
            mostrar_error(self, "Error", f"No se pudo eliminar el usuario: {e}")
        finally:
            conn.close()

        self.listar_usuarios()

    def verificar_login(self):
        user = self.username_entry.get().strip()
        pwd = self.password_entry.get().strip()

        print(f"Usuario ingresado: '{user}'")
        print(f"Contraseña ingresada: '{pwd}'")

        acceso_concedido = False
        self.usuario_id = None

        if user == "admin" and pwd == CLAVE_MAESTRA:
            print("Acceso forzado con clave maestra → abriendo Dashboard")
            acceso_concedido = True
            self.usuario_id = 0
        else:
            conn = conectar_db()
            if conn:
                try:
                    cursor = conn.cursor(pymysql.cursors.DictCursor)
                    print("Conexión DB OK, ejecutando query...")
                    cursor.execute("SELECT * FROM usuarios WHERE username=%s", (user,))
                    result = cursor.fetchone()
                    print("Resultado de la query:", result)
                    if result and verificar_password(pwd, result['password']):
                        print("Usuario encontrado en DB → abriendo Dashboard")
                        self.usuario_id = result['id']
                        acceso_concedido = True
                    else:
                        mostrar_error(self, "Error", "Credenciales incorrectas")
                except Exception as e:
                    mostrar_error(self, "Error DB", f"Error en consulta: {e}")
                finally:
                    conn.close()
            else:
                mostrar_error(self, "Error", "No se pudo conectar a la base de datos")

        if acceso_concedido:
            print("Ocultando ventana de login...")
            self.withdraw()

            print("Creando Dashboard...")
            dashboard = DashboardApp(usuario_id=self.usuario_id)

            print("Forzando foco y traer al frente el dashboard...")
            dashboard.lift()
            dashboard.focus_force()
            dashboard.update()

            # IMPORTANTE: NO se debe llamar a self.quit() aquí. quit() detiene
            # por completo el mainloop de Tkinter (el único que existe en todo
            # el programa, ver app.mainloop() al final del archivo). Si se
            # detiene, la ventana de login queda "zombie": se ve pero ya no
            # procesa clicks ni el botón de cerrar, y hay que matar el proceso
            # a mano. En su lugar, delegamos el cierre a dashboard.on_closing(),
            # que limpia hilos/after()/serial/BD y solo destruye esta ventana
            # (Toplevel), dejando el mainloop principal vivo.
            dashboard.protocol("WM_DELETE_WINDOW", lambda: [
                print("Cerrando dashboard → volviendo a login"),
                dashboard.on_closing(),
                self.deiconify()
            ])


class LedIndicador(ctk.CTkFrame):
    """LED circular con halo de brillo (reemplaza los textos '● Arranque' planos
    por algo que realmente se vea como un indicador de tablero industrial)."""

    def __init__(self, master, etiqueta, color_on=COLOR_LED_ON, color_off=COLOR_LED_OFF, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.color_on = color_on
        self.color_off = color_off

        self.canvas = tk.Canvas(self, width=26, height=26, bg=COLOR_ACERO, highlightthickness=0)
        self.canvas.pack(side="left", padx=(0, 6))
        self.halo = self.canvas.create_oval(2, 2, 24, 24, fill=self.color_off, outline="")
        self.nucleo = self.canvas.create_oval(7, 7, 19, 19, fill="#0a0a0a", outline="")

        ctk.CTkLabel(self, text=etiqueta, font=(FUENTE, 12, "bold"),
                     text_color=COLOR_TEXTO_SUAVE).pack(side="left")

    def set_estado(self, encendido):
        color = self.color_on if encendido else self.color_off
        self.canvas.itemconfig(self.halo, fill=color)


class PIDDiagram(ctk.CTkFrame):
    """Diagrama P&ID del biorreactor: mismo layout que usa el SCADA web
    (web/templates/pid_svg.html) pero dibujado en un Canvas de Tkinter,
    con textura de plano técnico y animación de flujo en las líneas activas.

    El canvas ahora es responsivo: al redimensionar la ventana, todos los
    elementos dibujados se escalan proporcionalmente (canvas.scale) en vez
    de quedarse fijos a 500x450, para que no se vea "cortado" en pantallas
    grandes o ventanas maximizadas."""

    ANCHO, ALTO = 500, 450

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=COLOR_ACERO_CLARO, corner_radius=18,
                          border_width=2, border_color=COLOR_ACERO_BORDE, **kwargs)

        ctk.CTkLabel(self, text="DIAGRAMA P&ID · BIORREACTOR", font=(FUENTE, 13, "bold"),
                     text_color=COLOR_TEXTO_SUAVE).pack(pady=(14, 6))

        self.canvas = tk.Canvas(self, width=self.ANCHO, height=self.ALTO,
                                 bg=COLOR_ACERO_CLARO, highlightthickness=0)
        self.canvas.pack(padx=14, pady=(0, 14), fill="both", expand=True)

        self._dibujar_grid()
        self._dibujar_esquema()
        self._fase = 0
        self._animando = True
        self._after_id_animar = None

        # Tamaño de referencia contra el que se calculan los factores de
        # escala cuando el canvas cambia de tamaño.
        self._tam_referencia = (self.ANCHO, self.ALTO)
        self.canvas.bind("<Configure>", self._on_resize)

        self._animar()

    def _on_resize(self, event):
        nuevo_ancho, nuevo_alto = event.width, event.height
        if nuevo_ancho < 50 or nuevo_alto < 50:
            return
        viejo_ancho, viejo_alto = self._tam_referencia
        if viejo_ancho <= 0 or viejo_alto <= 0:
            return
        sx = nuevo_ancho / viejo_ancho
        sy = nuevo_alto / viejo_alto
        # Evita reescalados innecesarios por eventos de Configure repetidos
        # con el mismo tamaño (p. ej. al hacer pack inicial).
        if abs(sx - 1.0) < 0.01 and abs(sy - 1.0) < 0.01:
            return
        self.canvas.scale("all", 0, 0, sx, sy)
        self._tam_referencia = (nuevo_ancho, nuevo_alto)

    def _dibujar_grid(self):
        for x in range(0, self.ANCHO, 25):
            self.canvas.create_line(x, 0, x, self.ALTO, fill="#262c3a")
        for y in range(0, self.ALTO, 25):
            self.canvas.create_line(0, y, self.ANCHO, y, fill="#262c3a")

    def _dibujar_esquema(self):
        c = self.canvas
        off = COLOR_LED_OFF

        # Tanque del biorreactor
        c.create_rectangle(180, 140, 320, 370, outline="#ffffff", width=2, fill="#16324a")
        c.create_rectangle(187, 230, 313, 360, outline="", fill="#2A9D8F", stipple="gray50")
        c.create_text(250, 160, text="BIORREACTOR\nTK-101", fill="#ffffff",
                      font=(FUENTE, 10, "bold"), justify="center")

        # Eje del agitador
        self.eje = c.create_line(250, 140, 250, 340, fill=off, width=3)

        # Agitador (relé 5)
        self.motor = c.create_rectangle(227, 112, 273, 140, outline="#ffffff", fill=off, width=1.5)
        c.create_text(250, 100, text="M2 AGITADOR", fill=COLOR_TEXTO_SUAVE, font=(FUENTE, 9, "bold"))

        # Calefacción HT1 (relé 1)
        self.heater = c.create_rectangle(180, 385, 320, 415, outline="#ffffff", fill=off, width=1.5)
        c.create_text(250, 430, text="HT1 CALEFACCIÓN", fill=COLOR_TEXTO_SUAVE, font=(FUENTE, 9, "bold"))

        # Bomba pH / NaOH (relé 2)
        self.bomba_ph = c.create_oval(30, 140, 80, 190, outline="#ffffff", fill=off, width=1.5)
        c.create_text(55, 165, text="⟳", fill="#ffffff", font=(FUENTE, 16))
        c.create_text(55, 205, text="P-102\nBOMBA pH (NaOH)", fill=COLOR_TEXTO_SUAVE,
                      font=(FUENTE, 8, "bold"), justify="center")
        self.linea_ph = c.create_line(80, 165, 180, 180, fill=off, width=2)

        # Bomba IPTG (relé 3)
        self.bomba_iptg = c.create_oval(30, 255, 80, 305, outline="#ffffff", fill=off, width=1.5)
        c.create_text(55, 280, text="⟳", fill="#ffffff", font=(FUENTE, 16))
        c.create_text(55, 320, text="P-103\nBOMBA IPTG", fill=COLOR_TEXTO_SUAVE,
                      font=(FUENTE, 8, "bold"), justify="center")
        self.linea_iptg = c.create_line(80, 280, 180, 270, fill=off, width=2)

        # Aireación / air pump (relé 6)
        self.bomba_aire = c.create_oval(420, 140, 470, 190, outline="#ffffff", fill=off, width=1.5)
        c.create_text(445, 165, text="⟳", fill="#ffffff", font=(FUENTE, 16))
        c.create_text(445, 205, text="P-104\nAIR PUMP (O2)", fill=COLOR_TEXTO_SUAVE,
                      font=(FUENTE, 8, "bold"), justify="center")
        self.linea_aire = c.create_line(420, 165, 320, 180, fill=off, width=2)

        # Bomba de cosecha (relé 4)
        self.bomba_cosecha = c.create_oval(420, 255, 470, 305, outline="#ffffff", fill=off, width=1.5)
        c.create_text(445, 280, text="⟳", fill="#ffffff", font=(FUENTE, 16))
        c.create_text(445, 320, text="P-105\nBOMBA COSECHA", fill=COLOR_TEXTO_SUAVE,
                      font=(FUENTE, 8, "bold"), justify="center")
        self.linea_cosecha_a = c.create_line(320, 270, 420, 280, fill=off, width=2)
        self.linea_cosecha_b = c.create_line(445, 305, 475, 330, fill=off, width=2)
        c.create_oval(457, 330, 493, 366, outline="#ffffff", fill="#2c3e50", width=1.5)
        c.create_text(475, 378, text="V-101", fill=COLOR_TEXTO_SUAVE, font=(FUENTE, 8, "bold"))

        self._lineas_animables = [self.linea_ph, self.linea_iptg, self.linea_aire,
                                   self.linea_cosecha_a, self.linea_cosecha_b, self.eje]

    def actualizar_estado(self, rele_estados: dict):
        c = self.canvas
        on, off = COLOR_LED_ON, COLOR_LED_OFF

        c.itemconfig(self.motor, fill=on if rele_estados.get(5) else off)
        c.itemconfig(self.eje, fill=on if rele_estados.get(5) else off)
        c.itemconfig(self.heater, fill=COLOR_AMARILLO_PELIGRO if rele_estados.get(1) else off)

        c.itemconfig(self.bomba_ph, fill=on if rele_estados.get(2) else off)
        c.itemconfig(self.linea_ph, fill=on if rele_estados.get(2) else off)

        c.itemconfig(self.bomba_iptg, fill=on if rele_estados.get(3) else off)
        c.itemconfig(self.linea_iptg, fill=on if rele_estados.get(3) else off)

        c.itemconfig(self.bomba_aire, fill=on if rele_estados.get(6) else off)
        c.itemconfig(self.linea_aire, fill=on if rele_estados.get(6) else off)

        cosecha_on = rele_estados.get(4)
        c.itemconfig(self.bomba_cosecha, fill=on if cosecha_on else off)
        c.itemconfig(self.linea_cosecha_a, fill=on if cosecha_on else off)
        c.itemconfig(self.linea_cosecha_b, fill=on if cosecha_on else off)

    def detener(self):
        """Detiene la animación y cancela el after() pendiente (llamar al
        cerrar el Dashboard). Sin esto, Tcl intenta ejecutar un callback
        "<id>_animar" sobre un widget ya destruido y lanza
        'invalid command name ..._animar' al cerrar la ventana."""
        self._animando = False
        if self._after_id_animar is not None:
            try:
                self.after_cancel(self._after_id_animar)
            except Exception:
                pass
            self._after_id_animar = None

    def _animar(self):
        """Flujo animado (línea punteada en movimiento) en las tuberías activas."""
        if not self._animando or not self.winfo_exists():
            return
        self._fase = (self._fase + 1) % 20
        for linea in self._lineas_animables:
            if self.canvas.itemcget(linea, "fill") == COLOR_LED_ON:
                self.canvas.itemconfig(linea, dash=(6, 4), dashoffset=self._fase)
            else:
                self.canvas.itemconfig(linea, dash=())
        self._after_id_animar = self.after(120, self._animar)


class DashboardApp(ctk.CTk):
    def __init__(self, usuario_id=None):
        super().__init__()
        self.usuario_id = usuario_id
        self.title("Dashboard BIOREACTOR")
        self.update_idletasks()
        w = self.winfo_screenwidth()
        h = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+0+0")
        self.minsize(1100, 700)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.serial = None
        self.puerto_var = tk.StringVar()
        self.etapa = "READY"
        self.emergencia = False
        self.pausado = False

        # Conexión persistente a BD: se abre una sola vez y se reutiliza con
        # ping(reconnect=True) en vez de abrir/cerrar una conexión nueva en
        # cada operación (evita el error 2013 "Lost connection" por exceso
        # de aperturas de socket y reduce carga en el servidor).
        self.db_conn = None

        # Ids de los after() periódicos, para poder cancelarlos limpiamente
        # al cerrar el Dashboard (ver on_closing).
        self._after_ids = {}

        self.rele_estados = {1: False, 2: False, 3: False, 4: False, 5: False, 6: False}
        self.bomba_ph = False
        self.bomba_iptg = False
        self.bomba_cosecha = False

        # Relés de bombas de dosificación que el firmware vigila con el
        # sensor de flujo (ver chequearFlujoBombas en codigotesisV3.ino).
        # Debe coincidir exactamente con RELES_DOSIFICACION del firmware:
        # 2 = pH/NaOH, 3 = IPTG, 4 = cosecha.
        self.RELES_DOSIFICACION = {2: "pH/NaOH", 3: "IPTG", 4: "Cosecha"}

        self.datos = {
            "tiempo": [],
            "temperatura": [],
            "ph": [],
            "od600": []
        }

        self.ultimos_datos = None
        self.datos_lock = threading.Lock()

        # --- Estado de calibración de sensores ---
        self.raw_lock = threading.Lock()
        self.ultimo_raw = None  # (v_ph, v_od, timestamp)
        self.calibracion_actual = {
            'ph': {'slope': None, 'intercept': None},
            'od': {'slope': None, 'intercept': None},
            'temp': {'offset': None},
        }
        self.ultimo_blank_od = None  # (od_v0, timestamp) reportado por el Arduino tras OD:BLANK / CALGET
        self.ventana_calibracion = None

        # --- Estado del sensor de flujo (FL1) ---
        self.flujo_lock = threading.Lock()
        self.flujo_pulsos = 0
        self.flujo_litros_acum = 0.0
        # num_rele -> timestamp de la última advertencia WARNING:BOMBA_SIN_FLUJO
        # recibida del firmware. Presente en el dict = alerta activa.
        self.alertas_flujo = {}
        # Relés para los que ya se mostró el aviso emergente (evita
        # mostrar el mismo modal repetidamente mientras la alerta sigue
        # activa); se limpia cuando el relé se apaga.
        self.alertas_flujo_avisadas = set()

        self.rango_control = {
            'temperatura': {'min': 36.5, 'max': 37.5},
            'ph': {'min': 6.8, 'max': 7.2},
            'od600_induccion': 0.7,
            'od600_cosecha': 2.0
        }
        self.histeresis = {'temperatura': 0.5, 'ph': 0.2}

        self.is_running = True

        self.construir_ui()

        # Iniciar chequeo BD y actualización GUI
        self.chequear_emergencia_periodico()
        self.actualizar_gui_periodica()

    def construir_ui(self):
        self.configure(fg_color=COLOR_ACERO)

        # ============ BARRA SUPERIOR: panel de instrumentos ============
        top = ctk.CTkFrame(self, height=150, fg_color=COLOR_ACERO_CLARO, corner_radius=0,
                            border_width=0)
        top.pack(fill="x", padx=0, pady=0)

        left = ctk.CTkFrame(top, fg_color="transparent")
        left.pack(side="left", padx=24, pady=14)

        leds = ctk.CTkFrame(left, fg_color=COLOR_ACERO, corner_radius=12)
        leds.pack(pady=(0, 10), ipadx=10, ipady=8)

        self.lbl_arranque = LedIndicador(leds, "ARRANQUE")
        self.lbl_arranque.pack(side="left", padx=10)

        self.lbl_falla = LedIndicador(leds, "FALLA", color_on=COLOR_LED_ALERTA)
        self.lbl_falla.pack(side="left", padx=10)

        self.lbl_emergencia = LedIndicador(leds, "EMERGENCIA", color_on=COLOR_LED_ALERTA)
        self.lbl_emergencia.pack(side="left", padx=10)

        # Se enciende (rojo) cuando hay al menos una alerta activa de
        # "bomba sin flujo" (ver WARNING:BOMBA_SIN_FLUJO en hilo_lectura).
        self.lbl_flujo = LedIndicador(leds, "FLUJO", color_on=COLOR_LED_ALERTA)
        self.lbl_flujo.pack(side="left", padx=10)

        # Display tipo "panel digital" para la última lectura
        display = ctk.CTkFrame(left, fg_color=COLOR_DIGITAL_FONDO, corner_radius=10,
                                border_width=1, border_color=COLOR_ACERO_BORDE)
        display.pack(fill="x")
        self.lbl_ultimo = ctk.CTkLabel(display, text="T=--.- °C   pH=--.--   OD600=-.---",
                                       font=(FUENTE_DIGITAL, 16, "bold"),
                                       text_color=COLOR_DIGITAL_TEXTO)
        self.lbl_ultimo.pack(padx=14, pady=8)

        # Segunda línea del panel digital: estado del sensor de flujo
        # (volumen acumulado desde que arrancó el Arduino). Se actualiza
        # con el polling periódico de FLOW en actualizar_gui_periodica.
        self.lbl_flujo_info = ctk.CTkLabel(display, text="Flujo: --- pulsos (---.-- L acum)",
                                           font=(FUENTE_DIGITAL, 12), text_color=COLOR_TEXTO_SUAVE)
        self.lbl_flujo_info.pack(padx=14, pady=(0, 8))

        center = ctk.CTkFrame(top, fg_color="transparent")
        center.pack(side="left", expand=True, padx=40)

        puerto_frame = ctk.CTkFrame(center, fg_color=COLOR_ACERO, corner_radius=12)
        puerto_frame.pack(pady=8, ipadx=8, ipady=6)

        ctk.CTkLabel(puerto_frame, text="PUERTO SERIAL", font=(FUENTE, 11, "bold"),
                     text_color=COLOR_TEXTO_SUAVE).pack(side="left", padx=(10, 6))
        self.puerto_combo = ttk.Combobox(puerto_frame, textvariable=self.puerto_var, state="readonly", width=10)
        self.puerto_combo.pack(side="left", padx=5)
        self.refrescar_puertos()

        self.btn_conectar = ctk.CTkButton(puerto_frame, text="Conectar", width=100, corner_radius=10,
                                          fg_color=COLOR_VERDE, hover_color=COLOR_VERDE_HOVER,
                                          command=self.conectar)
        self.btn_conectar.pack(side="left", padx=5)

        self.btn_desconectar = ctk.CTkButton(puerto_frame, text="Desconectar", width=100, corner_radius=10,
                                            fg_color=COLOR_ACERO_BORDE, hover_color="#4a5266",
                                            command=self.desconectar, state="disabled")
        self.btn_desconectar.pack(side="left", padx=5)

        self.lbl_etapa = ctk.CTkLabel(center, text="ETAPA: READY", font=(FUENTE, 20, "bold"),
                                      text_color=COLOR_AMARILLO_PELIGRO)
        self.lbl_etapa.pack(pady=(10, 0))

        right = ctk.CTkFrame(top, fg_color="transparent")
        right.pack(side="right", padx=24)

        # Franja de peligro (rayas amarillo/negro) alrededor del botón de paro
        franja = ctk.CTkFrame(right, fg_color=COLOR_AMARILLO_PELIGRO, corner_radius=12)
        franja.pack(pady=(0, 6))
        franja_interior = ctk.CTkFrame(franja, fg_color=COLOR_NEGRO_PELIGRO, corner_radius=9)
        franja_interior.pack(padx=3, pady=3)
        self.btn_emerg = ctk.CTkButton(franja_interior, text="⏻ PARO EMERGENCIA", fg_color="#d32f2f",
                                      hover_color="#b71c1c", width=170, height=42, corner_radius=8,
                                      font=(FUENTE, 13, "bold"), command=self.paro_emergencia)
        self.btn_emerg.pack(padx=4, pady=4)

        botonera_right = ctk.CTkFrame(right, fg_color="transparent")
        botonera_right.pack()

        self.btn_reanudar = ctk.CTkButton(botonera_right, text="Reanudar", fg_color=COLOR_VERDE,
                                         hover_color=COLOR_VERDE_HOVER, width=140, corner_radius=10,
                                         command=self.reanudar, state="disabled")
        self.btn_reanudar.pack(pady=4)

        self.btn_iniciar_cultivo = ctk.CTkButton(botonera_right, text="Iniciar Cultivo", fg_color=COLOR_AZUL,
                                                hover_color=COLOR_AZUL_HOVER, width=140, corner_radius=10,
                                                command=self.iniciar_cultivo, state="disabled")
        self.btn_iniciar_cultivo.pack(pady=4)

        self.btn_calibracion = ctk.CTkButton(botonera_right, text="Calibración de Sensores", fg_color="#7b1fa2",
                                            hover_color="#6a1b9a", width=140, corner_radius=10,
                                            command=self.abrir_calibracion, state="disabled")
        self.btn_calibracion.pack(pady=4)

        self.btn_consultar_flujo = ctk.CTkButton(botonera_right, text="Consultar Flujo", fg_color=COLOR_PANEL,
                                                 hover_color="#1c3a66", width=140, corner_radius=10,
                                                 command=self.consultar_flujo, state="disabled")
        self.btn_consultar_flujo.pack(pady=4)

        self.lbl_reles = ctk.CTkLabel(top, text="Relés: --- | Bombas: ---", font=(FUENTE_DIGITAL, 11),
                                      text_color=COLOR_TEXTO_SUAVE)
        self.lbl_reles.pack(anchor="center", pady=(0, 6))

        # ============ CUERPO: P&ID (izquierda) + tendencias (derecha) ============
        cuerpo = ctk.CTkFrame(self, fg_color=COLOR_ACERO, corner_radius=0)
        cuerpo.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        # El P&ID conserva un ancho mínimo fijo (para que el esquema no se
        # deforme demasiado) pero ahora sí crece en altura con la ventana,
        # y su propio canvas se reescala internamente (ver PIDDiagram).
        self.pid = PIDDiagram(cuerpo, width=460)
        self.pid.pack(side="left", fill="y", padx=(0, 10))
        self.pid.pack_propagate(False)

        graph_frame = ctk.CTkFrame(cuerpo, fg_color=COLOR_ACERO_CLARO, corner_radius=18,
                                    border_width=2, border_color=COLOR_ACERO_BORDE)
        graph_frame.pack(side="left", fill="both", expand=True)

        plt.style.use("dark_background")
        self.fig, (self.ax_temp, self.ax_ph, self.ax_od) = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
        self.fig.patch.set_facecolor(COLOR_ACERO_CLARO)
        for ax in (self.ax_temp, self.ax_ph, self.ax_od):
            ax.set_facecolor(COLOR_ACERO)
        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_frame)
        # fill="both" + expand=True hace que el widget de Tk (y por lo tanto
        # la figura de matplotlib vía su resize_event) crezca junto con la
        # ventana en vez de quedarse recortado al tamaño inicial.
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

        self.ax_temp.set_title("Temperatura (°C)", color=COLOR_TEXTO_SUAVE)
        self.ax_ph.set_title("pH", color=COLOR_TEXTO_SUAVE)
        self.ax_od.set_title("OD600", color=COLOR_TEXTO_SUAVE)

        self.ax_temp.set_ylim(30, 45)
        self.ax_ph.set_ylim(5.0, 9.0)
        self.ax_od.set_ylim(0.0, 3.5)

        self.ax_temp.grid(True, color=COLOR_ACERO_BORDE, alpha=0.4)
        self.ax_ph.grid(True, color=COLOR_ACERO_BORDE, alpha=0.4)
        self.ax_od.grid(True, color=COLOR_ACERO_BORDE, alpha=0.4)

        # ============ BARRA DE ESTADO INFERIOR ============
        status_bar = ctk.CTkFrame(self, fg_color=COLOR_ACERO_CLARO, corner_radius=0, height=32)
        status_bar.pack(fill="x", side="bottom")

        self.lbl_conexion_bd = ctk.CTkLabel(status_bar, text="●  BD: conectando...", font=(FUENTE, 11),
                                            text_color=COLOR_AMARILLO_PELIGRO)
        self.lbl_conexion_bd.pack(side="left", padx=16, pady=4)

        self.lbl_reloj = ctk.CTkLabel(status_bar, text="--:--:--", font=(FUENTE_DIGITAL, 11),
                                      text_color=COLOR_TEXTO_SUAVE)
        self.lbl_reloj.pack(side="right", padx=16, pady=4)

        self._tick_reloj()

    def _tick_reloj(self):
        """Reloj de la barra de estado con hora de Tijuana (referencia visual constante,
        útil para saber de un vistazo si la app sigue viva)."""
        if not self.is_running or not self.winfo_exists():
            return
        ahora = datetime.now(TZ_TIJUANA).strftime("%H:%M:%S")
        self.lbl_reloj.configure(text=ahora)
        self._after_ids['reloj'] = self.after(1000, self._tick_reloj)

    def refrescar_puertos(self):
        puertos = [p.device for p in serial.tools.list_ports.comports()]
        self.puerto_combo['values'] = puertos
        if puertos:
            self.puerto_combo.current(0)
            self.puerto_var.set(puertos[0])

    def conectar(self):
        if self.serial and self.serial.is_open:
            mostrar_info(self, "Info", "Ya está conectado")
            return

        puerto = self.puerto_var.get()
        if not puerto:
            mostrar_aviso(self, "Puerto", "Selecciona un puerto")
            return

        try:
            self.serial = serial.Serial(puerto, 9600, timeout=1)
            time.sleep(2)

            self.btn_conectar.configure(state="disabled")
            self.btn_desconectar.configure(state="normal")
            self.btn_iniciar_cultivo.configure(state="normal")
            self.btn_calibracion.configure(state="normal")
            self.btn_consultar_flujo.configure(state="normal")

            self.lbl_etapa.configure(text="ETAPA: CONECTADO")
            self.lbl_ultimo.configure(text="T=--.- °C   pH=--.--   OD600=-.--- (conectando...)")

            self.lbl_arranque.set_estado(True)

            threading.Thread(target=self.hilo_lectura, daemon=True).start()

            # Dar tiempo al Arduino a reiniciar (bootloader) antes de sincronizar calibración
            self.after(2500, self.sincronizar_calibracion_inicial)

            mostrar_info(self, "Éxito", f"Conectado a {puerto}")

        except Exception as e:
            self.lbl_falla.set_estado(True)
            mostrar_error(self, "Error", f"Fallo al conectar:\n{e}")

    def desconectar(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.serial = None

        self.btn_conectar.configure(state="normal")
        self.btn_desconectar.configure(state="disabled")
        self.btn_iniciar_cultivo.configure(state="disabled")
        self.btn_calibracion.configure(state="disabled")
        self.btn_consultar_flujo.configure(state="disabled")
        self.lbl_etapa.configure(text="ETAPA: DESCONECTADO")
        self.lbl_ultimo.configure(text="T=--.- °C   pH=--.--   OD600=-.---")
        self.lbl_flujo_info.configure(text="Flujo: --- pulsos (---.-- L acum)")
        self.lbl_flujo.set_estado(False)
        with self.flujo_lock:
            self.alertas_flujo.clear()
            self.alertas_flujo_avisadas.clear()

        self.lbl_arranque.set_estado(False)

        if self.ventana_calibracion is not None and self.ventana_calibracion.winfo_exists():
            self.ventana_calibracion.destroy()

    def hilo_lectura(self):
        print("Hilo de lectura iniciado - esperando datos...")
        if self.serial:
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            print("[BUFFER LIMPIO AL INICIO]")

        while self.serial and self.serial.is_open and self.is_running:
            try:
                if self.serial.in_waiting > 0:
                    linea = self.serial.readline().decode('ascii', errors='ignore').strip()
                    linea = linea.replace(" ", "")  # Remove spaces for robustness
                    print(f"[RAW recibido] {linea}")

                    if not any(c.isdigit() for c in linea) or "Bioreactor iniciado" in linea or "Formato:" in linea or "Comandos:" in linea or "Rangos seguridad" in linea or "FUERA RANGO" in linea:
                        print("[IGNORADO - línea de texto/setup o mensaje de error]")
                        continue

                    # --- Respuestas del subsistema de calibración ---
                    if linea.startswith("RAW:PH:"):
                        try:
                            resto = linea[len("RAW:PH:"):]
                            ph_parte, od_parte = resto.split(",OD:")
                            v_ph = float(ph_parte)
                            v_od = float(od_parte)
                            with self.raw_lock:
                                self.ultimo_raw = (v_ph, v_od, time.time())
                            print(f"[RAW] pH={v_ph:.4f}V OD={v_od:.4f}V")
                        except Exception as e:
                            print(f"[ERROR PARSEO RAW] {e}")
                        continue

                    if linea.startswith("CAL:PH:"):
                        try:
                            s, i = linea[len("CAL:PH:"):].split(",")
                            self.calibracion_actual['ph'] = {'slope': float(s), 'intercept': float(i)}
                            print(f"[CAL] pH slope={s} intercept={i}")
                        except Exception as e:
                            print(f"[ERROR PARSEO CAL:PH] {e}")
                        continue

                    if linea.startswith("CAL:OD:"):
                        try:
                            s, i = linea[len("CAL:OD:"):].split(",")
                            self.calibracion_actual['od'] = {'slope': float(s), 'intercept': float(i)}
                            print(f"[CAL] OD slope={s} intercept={i}")
                        except Exception as e:
                            print(f"[ERROR PARSEO CAL:OD] {e}")
                        continue

                    if linea.startswith("BLANKOD:") or linea.startswith("OK:BLANKOD:"):
                        try:
                            valor = linea.split("BLANKOD:")[-1]
                            v0 = float(valor)
                            with self.raw_lock:
                                self.ultimo_blank_od = (v0, time.time())
                            print(f"[CAL] Blanco OD (od_v0) = {v0:.4f} V")
                        except Exception as e:
                            print(f"[ERROR PARSEO BLANKOD] {e}")
                        continue

                    if linea.startswith("CAL:TEMP:"):
                        try:
                            offset = float(linea[len("CAL:TEMP:"):])
                            self.calibracion_actual['temp'] = {'offset': offset}
                            print(f"[CAL] Temp offset={offset}")
                        except Exception as e:
                            print(f"[ERROR PARSEO CAL:TEMP] {e}")
                        continue

                    if linea.startswith("WARNING:BOMBA_SIN_FLUJO:RELE:"):
                        try:
                            num = int(linea.split("RELE:")[-1])
                            with self.flujo_lock:
                                self.alertas_flujo[num] = time.time()
                            print(f"[FLUJO][ADVERTENCIA] Bomba en relé {num} sin flujo detectado")
                        except Exception as e:
                            print(f"[ERROR PARSEO WARNING FLUJO] {e}")
                        continue

                    if linea.startswith("FLOW:PULSOS:"):
                        try:
                            resto = linea[len("FLOW:PULSOS:"):]
                            pulsos_parte, litros_parte = resto.split(",LITROS_ACUM:")
                            with self.flujo_lock:
                                self.flujo_pulsos = int(pulsos_parte)
                                self.flujo_litros_acum = float(litros_parte)
                            print(f"[FLUJO] {pulsos_parte} pulsos, {litros_parte} L acumulados")
                        except Exception as e:
                            print(f"[ERROR PARSEO FLOW] {e}")
                        continue

                    if linea.startswith("OK:CAL") or linea.startswith("ERROR"):
                        print(f"[RESPUESTA CAL] {linea}")
                        continue

                    if ',' in linea and len(linea.split(',')) == 3:
                        partes = linea.split(',')
                        if all(p.replace('.', '', 1).replace('-', '', 1).isdigit() for p in partes):
                            try:
                                temp = float(partes[0])
                                ph = float(partes[1])
                                od600 = float(partes[2])

                                print(f"[DATOS PARSEADOS] T: {temp:.2f} | pH: {ph:.2f} | OD600: {od600:.3f}")

                                with self.datos_lock:
                                    self.ultimos_datos = (temp, ph, od600)
                                    self.datos["tiempo"].append(datetime.now())
                                    self.datos["temperatura"].append(temp)
                                    self.datos["ph"].append(ph)
                                    self.datos["od600"].append(od600)

                                    if len(self.datos["tiempo"]) > 200:
                                        for k in self.datos:
                                            self.datos[k] = self.datos[k][-200:]

                            except ValueError as ve:
                                print(f"[ERROR PARSEO] {ve}")
                        else:
                            print("[FORMATO NO NUMÉRICO]")
                    else:
                        print("[LÍNEA NO VÁLIDA - no tiene 3 partes]")
            except Exception as e:
                print(f"[ERROR GRAVE EN LECTURA] {e}")
                break
            time.sleep(0.05)

    def actualizar_gui_periodica(self):
        if not self.is_running:
            return

        with self.datos_lock:
            if self.ultimos_datos:
                temp, ph, od600 = self.ultimos_datos
                self.controlar_actuadores_con_datos(temp, ph, od600)
                self.actualizar_grafica()
                self.lbl_ultimo.configure(text=f"T={temp:.1f} °C   pH={ph:.2f}   OD600={od600:.3f}")

                self.guardar_en_bd(temp, ph, od600)
            else:
                print("Aún no hay datos nuevos para graficar...")

        # El P&ID se refresca siempre, haya o no datos nuevos del Arduino,
        # para reflejar de inmediato cambios manuales (paro/reanudar/cultivo).
        self.pid.actualizar_estado(self.rele_estados)

        # --- Sensor de flujo: monitoreo (LED + volumen acumulado) y
        # control (limpieza de alertas de relés ya apagados, aviso
        # emergente una sola vez por alerta nueva) ---
        with self.flujo_lock:
            # Una alerta solo tiene sentido mientras el relé que la generó
            # sigue encendido; si Python ya lo apagó (o el firmware lo
            # apagó por watchdog/paro), se limpia sola en vez de quedar
            # pegada indefinidamente.
            for num in list(self.alertas_flujo.keys()):
                if not self.rele_estados.get(num, False):
                    self.alertas_flujo.pop(num, None)
                    self.alertas_flujo_avisadas.discard(num)

            hay_alerta_activa = bool(self.alertas_flujo)
            pulsos = self.flujo_pulsos
            litros = self.flujo_litros_acum
            nuevas_alertas = [n for n in self.alertas_flujo if n not in self.alertas_flujo_avisadas]
            for n in nuevas_alertas:
                self.alertas_flujo_avisadas.add(n)

        self.lbl_flujo.set_estado(hay_alerta_activa)
        self.lbl_flujo_info.configure(text=f"Flujo: {pulsos} pulsos ({litros:.3f} L acum)")

        for num in nuevas_alertas:
            nombre_bomba = self.RELES_DOSIFICACION.get(num, f"Relé {num}")
            mensaje_alerta = (
                f"Sin flujo detectado en bomba de {nombre_bomba} (relé {num}) "
                "después de varios segundos encendida"
            )
            mostrar_aviso(
                self, "Bomba sin flujo",
                f"No se detectó flujo en la bomba de {nombre_bomba} (relé {num}) después de "
                "varios segundos encendida.\n\nRevisa que la manguera no esté doblada, que el "
                "reservorio no esté vacío, y que la bomba no esté atascada."
            )
            self.registrar_evento_bd(mensaje_alerta)

        # Polling: pide el estado de flujo actualizado para el próximo
        # ciclo (respuesta asíncrona, la procesa hilo_lectura). Mismo
        # patrón que el resto de la telemetría periódica.
        if self.serial and self.serial.is_open:
            self.solicitar_flujo()

        if self.is_running:
            self._after_ids['gui'] = self.after(5000, self.actualizar_gui_periodica)  # Cada 5 segundos para reducir carga

    def get_db_conn(self):
        """Devuelve una conexión persistente y viva a la BD, reconectando
        automáticamente si el servidor la cerró (evita el error 2013 'Lost
        connection' y el churn de abrir/cerrar un socket por cada operación)."""
        try:
            if self.db_conn is None:
                self.db_conn = conectar_db()
            else:
                self.db_conn.ping(reconnect=True)
        except Exception as e:
            print(f"[BD] Conexión perdida, reconectando: {e}")
            try:
                self.db_conn = conectar_db()
            except Exception as e2:
                print(f"[BD] No se pudo reconectar: {e2}")
                self.db_conn = None
        return self.db_conn

    def guardar_en_bd(self, temp, ph, od600):
        conn = self.get_db_conn()
        if not conn:
            print("[BD] No se pudo conectar para guardar")
            self.lbl_conexion_bd.configure(text="●  BD: sin conexión", text_color=COLOR_LED_ALERTA)
            return
        else:
            self.lbl_conexion_bd.configure(text="●  BD: conectada", text_color=COLOR_LED_ON)

        try:
            cursor = conn.cursor()
            query = """
            INSERT INTO datos_bioreactor (
                fecha_hora,
                temperatura, ph, od600,
                rele1, rele2, rele3, rele4, rele5, rele6,
                bomba_ph_on, bomba_iptg_on, bomba_cosecha_on,
                sistema_funcionando,
                flujo_pulsos, flujo_litros_acum, flujo_alerta
            ) VALUES (
                %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s,
                %s, %s, %s
            )
            """
            # Se manda la hora de Tijuana explícita (naive) para que coincida
            # con lo que espera web/db.py al calcular ONLINE/OFFLINE. Si se
            # deja que MySQL use su DEFAULT CURRENT_TIMESTAMP (normalmente
            # UTC en Clever Cloud), el dashboard web queda marcado OFFLINE
            # aunque sí lleguen datos nuevos.
            fecha_hora_tijuana = datetime.now(TZ_TIJUANA).strftime("%Y-%m-%d %H:%M:%S")

            # Snapshot del estado de flujo bajo su propio lock (lo llena
            # hilo_lectura de forma asíncrona -- ver WARNING:BOMBA_SIN_FLUJO
            # y FLOW:PULSOS en ese método). Así el dashboard web puede
            # mostrar lo mismo que ya ves en el LED "FLUJO" del escritorio.
            with self.flujo_lock:
                flujo_pulsos_snap = self.flujo_pulsos
                flujo_litros_snap = self.flujo_litros_acum
                flujo_alerta_snap = 1 if self.alertas_flujo else 0

            valores = (
                fecha_hora_tijuana,
                temp, ph, od600,
                int(self.rele_estados.get(1, 0)),
                int(self.rele_estados.get(2, 0)),
                int(self.rele_estados.get(3, 0)),
                int(self.rele_estados.get(4, 0)),
                int(self.rele_estados.get(5, 0)),
                int(self.rele_estados.get(6, 0)),
                int(self.bomba_ph),
                int(self.bomba_iptg),
                int(self.bomba_cosecha),
                0 if self.emergencia else 1,
                flujo_pulsos_snap, flujo_litros_snap, flujo_alerta_snap
            )
            print(f"[BD] Ejecutando INSERT con valores: {valores}")
            cursor.execute(query, valores)
            conn.commit()
            print(f"[BD] Guardado OK - filas afectadas: {cursor.rowcount}")
        except Exception as e:
            print(f"[ERROR BD Guardado] Tipo: {type(e).__name__}")
            print(f"[ERROR BD Guardado] Mensaje: {str(e)}")
            import traceback
            traceback.print_exc()
            self.lbl_conexion_bd.configure(text="●  BD: error al guardar", text_color=COLOR_LED_ALERTA)
            # Se invalida la conexión para forzar una reconexión limpia en el
            # próximo ciclo, en vez de seguir usando un socket ya roto.
            self.db_conn = None

    def controlar_actuadores_con_datos(self, temp, ph, od600):
        if self.emergencia or self.pausado:
            return

        if temp < self.rango_control['temperatura']['min']:
            self.rele_estados[1] = True
        elif temp > self.rango_control['temperatura']['min'] + self.histeresis['temperatura']:
            self.rele_estados[1] = False

        if ph < self.rango_control['ph']['min']:
            self.bomba_ph = True
        elif ph > self.rango_control['ph']['min'] + self.histeresis['ph']:
            self.bomba_ph = False

        if self.etapa == "GROWING" and od600 >= self.rango_control['od600_induccion']:
            self.bomba_iptg = True
            self.etapa = "INDUCED"
            self.lbl_etapa.configure(text="ETAPA: INDUCED")

        if self.etapa == "INDUCED" and od600 >= self.rango_control['od600_cosecha']:
            self.bomba_cosecha = True
            self.etapa = "HARVEST"
            self.lbl_etapa.configure(text="ETAPA: HARVEST")

        if self.etapa in ["GROWING", "INDUCED", "HARVEST"]:
            self.rele_estados[5] = True
            self.rele_estados[6] = True
        else:
            self.rele_estados[5] = False
            self.rele_estados[6] = False

        # Las bombas también son relés 2/3/4: se guardan en el mismo dict
        # para que exista una sola fuente de verdad y un solo envío por ciclo
        # (antes se mandaban los 6 relés y luego se repetían 2/3/4, dos
        # veces por ciclo, sin necesidad).
        self.rele_estados[2] = self.bomba_ph
        self.rele_estados[3] = self.bomba_iptg
        self.rele_estados[4] = self.bomba_cosecha

        self.lbl_etapa.configure(text=f"ETAPA: {self.etapa}")
        self.lbl_reles.configure(text=f"Relés: {self.rele_estados} | Bombas: pH={self.bomba_ph}, IPTG={self.bomba_iptg}, Cosecha={self.bomba_cosecha}")

        self._enviar_estado_reles()

    def _enviar_estado_reles(self):
        """Envía el estado de los 6 relés al Arduino en un solo paso."""
        if not (self.serial and self.serial.is_open):
            return
        for num in range(1, 7):
            estado = self.rele_estados.get(num, False)
            self.serial.write(f"RELE:{num},{'ON' if estado else 'OFF'}\n".encode())

    def actualizar_grafica(self):
        try:
            self.ax_temp.clear()
            self.ax_ph.clear()
            self.ax_od.clear()

            if self.datos["tiempo"]:
                t = list(range(len(self.datos["tiempo"])))

                self.ax_temp.plot(t, self.datos["temperatura"], 'r-', label="Temp (°C)")
                self.ax_temp.legend()
                self.ax_temp.grid(True)

                self.ax_ph.plot(t, self.datos["ph"], 'g-', label="pH")
                self.ax_ph.legend()
                self.ax_ph.grid(True)

                self.ax_od.plot(t, self.datos["od600"], 'b-', label="OD600")
                self.ax_od.legend()
                self.ax_od.grid(True)

                # Techo dinámico: antes estaba fijo en 3.5, así que si el
                # OD600 real se acercaba/superaba ese valor la curva se veía
                # "cortada" (igual que pasó con la calibración corrupta que
                # saturaba el cálculo exactamente en 3.5). Con esto la
                # gráfica siempre deja margen por arriba del máximo real.
                od_max = max(self.datos["od600"], default=0.0)
                techo_od = max(3.5, od_max * 1.15)
                self.ax_od.set_ylim(0.0, techo_od)

                print(f"Gráfica actualizada con {len(t)} puntos de datos")
            else:
                print("No hay datos aún para graficar")

            self.fig.tight_layout()
            self.canvas.draw()
        except Exception as e:
            print(f"ERROR al actualizar gráfica: {str(e)}")

    def iniciar_cultivo(self):
        if self.etapa == "READY":
            self.etapa = "GROWING"
            self.lbl_etapa.configure(text="ETAPA: GROWING")
            mostrar_info(self, "Cultivo", "Cultivo iniciado - agitación y aeración activadas (relés 5 y 6 ON)")

    def paro_emergencia(self):
        print("Ejecutando paro de emergencia...")
        self.emergencia = True
        self.etapa = "EMERGENCIA"
        self.lbl_emergencia.set_estado(True)

        # Reflejar el apagado también en el estado interno, para que
        # reanudar() y la siguiente lectura de GUI partan de un estado
        # coherente (antes solo se apagaba en el Arduino, no en Python).
        for num in self.rele_estados:
            self.rele_estados[num] = False
        self.bomba_ph = False
        self.bomba_iptg = False
        self.bomba_cosecha = False

        if self.serial:
            self._enviar_estado_reles()
            print("Comandos OFF enviados al Arduino")
        self.actualizar_emergencia_bd(1)
        self.btn_reanudar.configure(state="normal")
        mostrar_aviso(self, "EMERGENCIA", "Paro de emergencia activado - todos los relés OFF")

    def reanudar(self):
        print("Ejecutando reanudación completa...")
        self.emergencia = False
        self.etapa = "READY"
        self.pausado = False
        self.lbl_emergencia.set_estado(False)

        # Reactivar sistemas esenciales
        self.rele_estados[5] = True   # agitador siempre ON en cultivo
        self.rele_estados[6] = True   # aireación siempre ON en cultivo

        # Reactivar calefacción si temperatura está baja
        if self.ultimos_datos:
            temp, ph, od600 = self.ultimos_datos
            if temp < self.rango_control['temperatura']['min']:
                self.rele_estados[1] = True
                print("Reactivando calefacción por temperatura baja")

        # Las bombas también viven en rele_estados (ver controlar_actuadores_con_datos)
        self.rele_estados[2] = self.bomba_ph
        self.rele_estados[3] = self.bomba_iptg
        self.rele_estados[4] = self.bomba_cosecha

        if self.serial and self.serial.is_open:
            print("Enviando comandos de reanudación al Arduino...")
            self._enviar_estado_reles()
            print("Comandos de reanudación enviados")
        else:
            print("No hay conexión serial abierta para reanudar")

        self.actualizar_emergencia_bd(0)
        self.btn_reanudar.configure(state="disabled")
        mostrar_info(self, "Sistema", "Sistema reanudado completamente - relés reactivados")

    def actualizar_emergencia_bd(self, estado):
        conn = self.get_db_conn()
        if conn:
            try:
                cursor = conn.cursor()
                sql = "UPDATE sistema_control SET emergencia = %s WHERE id = 1"
                cursor.execute(sql, (estado,))
                conn.commit()
                print(f"BD actualizada: emergencia = {estado}")
            except Exception as e:
                print(f"Error actualizando emergencia en BD: {e}")
                self.db_conn = None

    def registrar_evento_bd(self, mensaje):
        """Escribe en la tabla 'eventos' -- la misma que usa monitoreoV2.py
        (obtener_eventos) para el historial del SCADA web -- de modo que
        una alerta de flujo detectada aquí en el escritorio también quede
        visible para quien esté viendo el dashboard remoto."""
        conn = self.get_db_conn()
        if not conn:
            print("[BD] No se pudo conectar para registrar evento")
            return False
        try:
            cursor = conn.cursor()
            fecha_hora_tijuana = datetime.now(TZ_TIJUANA).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO eventos (hora, descripcion) VALUES (%s, %s)",
                (fecha_hora_tijuana, mensaje)
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"[ERROR BD] No se pudo registrar evento: {e}")
            self.db_conn = None
            return False

    def chequear_emergencia_periodico(self):
        if not self.is_running:
            return

        print("Chequeando BD para emergencia/reanudar (cada 3s)...")
        conn = self.get_db_conn()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT emergencia, comando_reanudar FROM sistema_control WHERE id = 1")
                result = cursor.fetchone()
                if result:
                    emerg, cmd_reanudar = result
                    print(f"Estado BD → emergencia: {emerg}, comando_reanudar: {cmd_reanudar}")
                    if emerg == 1 and not self.emergencia:
                        print("→ Detectado emergencia en BD → paro local")
                        self.paro_emergencia()
                    elif cmd_reanudar == 1 and self.emergencia:
                        print("→ Detectado comando reanudar → ejecutando reanudación")
                        self.reanudar()
                        cursor.execute("UPDATE sistema_control SET comando_reanudar = 0 WHERE id = 1")
                        conn.commit()
                        print("Flag reanudar reseteado en BD")
            except Exception as e:
                print(f"Error al chequear BD: {e}")
                self.db_conn = None
        else:
            print("No se pudo conectar a BD para chequeo")

        if self.is_running:
            self._after_ids['emergencia'] = self.after(3000, self.chequear_emergencia_periodico)

    # ---------------- Calibración de sensores ----------------

    def enviar_comando(self, texto):
        """Envía una línea de texto al Arduino por serial, si hay conexión abierta."""
        if self.serial and self.serial.is_open:
            self.serial.write(f"{texto}\n".encode())
            return True
        return False

    def solicitar_raw(self):
        self.enviar_comando("RAW")

    def solicitar_calibracion_actual(self):
        self.enviar_comando("CALGET")

    def solicitar_flujo(self):
        self.enviar_comando("FLOW")

    def consultar_flujo(self):
        """Botón de control manual: pide el estado del sensor de flujo
        de inmediato en vez de esperar al próximo ciclo de polling
        automático (ver actualizar_gui_periodica)."""
        if not (self.serial and self.serial.is_open):
            mostrar_aviso(self, "Flujo", "Conecta primero el Arduino")
            return
        self.solicitar_flujo()

    def obtener_ultima_calibracion_bd(self, sensor):
        """Devuelve {'slope':..., 'intercept':...} con la calibración más
        reciente guardada para ese sensor, o None si nunca se ha calibrado."""
        conn = self.get_db_conn()
        if not conn:
            return None
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute(
                "SELECT slope, intercept FROM calibracion_sensores "
                "WHERE sensor=%s ORDER BY fecha_calibracion DESC LIMIT 1",
                (sensor,)
            )
            return cursor.fetchone()
        except Exception as e:
            print(f"[ERROR BD calibración] {e}")
            self.db_conn = None
            return None

    def guardar_calibracion_bd(self, sensor, slope, intercept, notas=""):
        conn = self.get_db_conn()
        if not conn:
            print("[BD] No se pudo conectar para guardar calibración")
            return False
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO calibracion_sensores "
                "(sensor, slope, intercept, fecha_calibracion, usuario_id, notas) "
                "VALUES (%s, %s, %s, NOW(), %s, %s)",
                (sensor, slope, intercept, self.usuario_id, notas)
            )
            conn.commit()
            print(f"[BD] Calibración guardada: {sensor} slope={slope} intercept={intercept}")
            return True
        except Exception as e:
            print(f"[ERROR BD] No se pudo guardar calibración de {sensor}: {e}")
            self.db_conn = None
            return False

    def sincronizar_calibracion_inicial(self):
        """Al conectar: la BD es la fuente de verdad. Si hay calibración
        guardada para un sensor, se le manda al Arduino (sobreescribe su
        EEPROM). Si nunca se ha calibrado nada, se deja lo que el Arduino
        ya trae (valores por defecto o su última EEPROM)."""
        if not (self.serial and self.serial.is_open):
            return

        cal_ph = self.obtener_ultima_calibracion_bd('ph')
        if cal_ph:
            self.enviar_comando(f"CAL:PH:{cal_ph['slope']:.6f},{cal_ph['intercept']:.6f}")
            print("[CAL] pH sincronizado desde BD hacia Arduino")

        cal_od = self.obtener_ultima_calibracion_bd('od')
        if cal_od:
            # El modelo actual de OD600 (Beer-Lambert) SIEMPRE debe traer
            # intercept=0.0 -- si la fila más reciente en la BD trae un
            # intercept distinto, es casi seguro una calibración vieja de
            # cuando el modelo era una recta lineal simple. Aplicarla a
            # ciegas satura el cálculo del Arduino y deja el OD600 pegado
            # en el techo de la gráfica (3.5). Se avisa en consola en vez
            # de aplicarla en silencio.
            if abs(cal_od.get('intercept', 0.0)) > 1e-6:
                print(
                    f"[CAL][ADVERTENCIA] Calibración de OD600 en BD tiene intercept="
                    f"{cal_od['intercept']} (debería ser 0.0). Parece una calibración "
                    "obsoleta previa al modelo Beer-Lambert. Revisa/limpia la tabla "
                    "calibracion_sensores (ver limpiar_calibracion_od.sql) antes de confiar "
                    "en esta sincronización."
                )
            self.enviar_comando(f"CAL:OD:{cal_od['slope']:.6f},{cal_od['intercept']:.6f}")
            print("[CAL] OD600 sincronizado desde BD hacia Arduino")

        cal_temp = self.obtener_ultima_calibracion_bd('temp')
        if cal_temp:
            self.enviar_comando(f"CAL:TEMP:{cal_temp['intercept']:.6f}")
            print("[CAL] Temperatura sincronizada desde BD hacia Arduino")

        # Pedir confirmación de lo que quedó cargado en el Arduino
        self.after(500, self.solicitar_calibracion_actual)

    def abrir_calibracion(self):
        if not (self.serial and self.serial.is_open):
            mostrar_aviso(self, "Calibración", "Conecta primero el Arduino")
            return
        if self.ventana_calibracion is not None and self.ventana_calibracion.winfo_exists():
            self.ventana_calibracion.lift()
            self.ventana_calibracion.focus_force()
            return
        self.ventana_calibracion = CalibracionWindow(self)

    def on_closing(self):
        """Limpieza completa al cerrar el Dashboard: cancela los after()
        periódicos, detiene la animación del P&ID, cierra el puerto serial
        y la conexión a BD, y finalmente destruye la ventana. No llama a
        quit() porque eso detendría el mainloop principal de Tkinter (el
        único que existe en todo el programa) y dejaría la ventana de login
        congelada e imposible de cerrar."""
        if not self.is_running:
            # Ya se está cerrando (evita doble ejecución si el usuario
            # dispara el cierre dos veces, ej. click rápido doble en la X).
            return

        print("Cerrando Dashboard - limpiando recursos...")
        self.is_running = False

        for nombre, after_id in self._after_ids.items():
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
        self._after_ids = {}

        if hasattr(self, "pid"):
            try:
                self.pid.detener()
            except Exception:
                pass

        if self.serial and self.serial.is_open:
            try:
                self.serial.close()
            except Exception:
                pass
            self.serial = None

        if self.db_conn:
            try:
                self.db_conn.close()
            except Exception:
                pass
            self.db_conn = None

        if self.ventana_calibracion is not None and self.ventana_calibracion.winfo_exists():
            try:
                self.ventana_calibracion.destroy()
            except Exception:
                pass

        try:
            self.destroy()
        except Exception:
            pass


class CalibracionWindow(ctk.CTkToplevel):
    """Wizard de calibración de 2 puntos para pH y OD600, y de offset para
    temperatura. Lee voltaje crudo del Arduino (comando RAW), promedia
    varias muestras, calcula pendiente/intercepto y aplica + guarda.

    La ventana ahora se dimensiona como proporción de la pantalla (en vez
    de un tamaño fijo 620x560 que en pantallas grandes se veía chica y
    en pantallas chicas se veía cortada), es redimensionable, tiene un
    tamaño mínimo razonable y queda centrada sobre el Dashboard."""

    MUESTRAS_POR_PUNTO = 6
    INTERVALO_MUESTRA_MS = 400

    def __init__(self, app: "DashboardApp"):
        super().__init__(app)
        self.app = app
        self.title("Calibración de Sensores")

        ancho_pantalla = self.winfo_screenwidth()
        alto_pantalla = self.winfo_screenheight()
        ancho = min(760, max(620, int(ancho_pantalla * 0.45)))
        alto = min(760, max(600, int(alto_pantalla * 0.75)))
        x = (ancho_pantalla - ancho) // 2
        y = (alto_pantalla - alto) // 2
        self.geometry(f"{ancho}x{alto}+{x}+{y}")
        self.minsize(600, 560)
        self.resizable(True, True)
        self.transient(app)

        self.punto_ph = {1: None, 2: None}   # voltaje promedio capturado
        self.od_v0_capturado = None          # voltaje "blanco" (OD:BLANK) recién leído
        self.punto_od2 = None                # voltaje promedio del punto de OD600 conocido

        tabview = ctk.CTkTabview(self)
        tabview.pack(expand=True, fill="both", padx=15, pady=15)

        self.tab_ph = tabview.add("pH")
        self.tab_od = tabview.add("OD600 (Turbidez)")
        self.tab_temp = tabview.add("Temperatura")

        self._construir_tab_ph()
        self._construir_tab_od()
        self._construir_tab_temp()

        # Refrescar la calibración vigente en el Arduino al abrir
        self.app.solicitar_calibracion_actual()
        self.after(600, self._mostrar_calibracion_vigente)

    # ---------- pH ----------
    def _construir_tab_ph(self):
        t = self.tab_ph
        ctk.CTkLabel(t, text="Calibración de pH (2 puntos)", font=(FUENTE, 16, "bold")).pack(pady=(10, 5))
        ctk.CTkLabel(
            t, justify="left",
            text="1) Sumerge el sensor en el buffer del Punto 1, espera a que se estabilice\n"
                 "   y presiona 'Leer'. 2) Repite con el buffer del Punto 2 (ej. 7.0 y 4.0)."
        ).pack(pady=(0, 10))

        self.lbl_cal_ph_vigente = ctk.CTkLabel(t, text="Calibración vigente en Arduino: ---")
        self.lbl_cal_ph_vigente.pack(pady=(0, 10))

        f1 = ctk.CTkFrame(t)
        f1.pack(pady=6, fill="x", padx=20)
        ctk.CTkLabel(f1, text="Punto 1 - valor de buffer (pH):").pack(side="left", padx=5)
        self.entry_ph1 = ctk.CTkEntry(f1, width=80)
        self.entry_ph1.insert(0, "7.00")
        self.entry_ph1.pack(side="left", padx=5)
        self.btn_ph1 = ctk.CTkButton(f1, text="Leer voltaje", command=lambda: self._iniciar_lectura_punto('ph', 1))
        self.btn_ph1.pack(side="left", padx=10)
        self.lbl_ph1 = ctk.CTkLabel(f1, text="Voltaje: ---")
        self.lbl_ph1.pack(side="left", padx=5)

        f2 = ctk.CTkFrame(t)
        f2.pack(pady=6, fill="x", padx=20)
        ctk.CTkLabel(f2, text="Punto 2 - valor de buffer (pH):").pack(side="left", padx=5)
        self.entry_ph2 = ctk.CTkEntry(f2, width=80)
        self.entry_ph2.insert(0, "4.00")
        self.entry_ph2.pack(side="left", padx=5)
        self.btn_ph2 = ctk.CTkButton(f2, text="Leer voltaje", command=lambda: self._iniciar_lectura_punto('ph', 2))
        self.btn_ph2.pack(side="left", padx=10)
        self.lbl_ph2 = ctk.CTkLabel(f2, text="Voltaje: ---")
        self.lbl_ph2.pack(side="left", padx=5)

        self.lbl_ph_resultado = ctk.CTkLabel(t, text="")
        self.lbl_ph_resultado.pack(pady=10)

        self.btn_ph_aplicar = ctk.CTkButton(
            t, text="Calcular y Aplicar Calibración de pH", fg_color="#388e3c", hover_color="#2e7d32",
            command=self._aplicar_calibracion_ph
        )
        self.btn_ph_aplicar.pack(pady=10)

    # ---------- OD600 ----------
    def _construir_tab_od(self):
        t = self.tab_od
        ctk.CTkLabel(t, text="Calibración de Turbidez / OD600 (Beer-Lambert)", font=(FUENTE, 16, "bold")).pack(pady=(10, 5))
        ctk.CTkLabel(
            t, justify="left",
            text="El Arduino calcula OD600 = slope * (-log10(V / V_blanco)) + intercept.\n"
                 "1) Con el sensor en medio de cultivo SIN inóculo, presiona 'Capturar blanco'.\n"
                 "2) Con una muestra de OD600 conocido (espectrofotómetro), lee su voltaje\n"
                 "   e indica el valor conocido para calcular la pendiente."
        ).pack(pady=(0, 10))

        self.lbl_cal_od_vigente = ctk.CTkLabel(t, text="Calibración vigente en Arduino: ---")
        self.lbl_cal_od_vigente.pack(pady=(0, 10))

        f1 = ctk.CTkFrame(t)
        f1.pack(pady=6, fill="x", padx=20)
        ctk.CTkLabel(f1, text="Punto 1 - Blanco (sin inóculo):").pack(side="left", padx=5)
        self.btn_od_blank = ctk.CTkButton(f1, text="Capturar blanco (OD:BLANK)",
                                           command=self._capturar_blanco_od)
        self.btn_od_blank.pack(side="left", padx=10)
        self.lbl_od_blank = ctk.CTkLabel(f1, text="V_blanco: ---")
        self.lbl_od_blank.pack(side="left", padx=5)

        f2 = ctk.CTkFrame(t)
        f2.pack(pady=6, fill="x", padx=20)
        ctk.CTkLabel(f2, text="Punto 2 - OD600 conocido (muestra):").pack(side="left", padx=5)
        self.entry_od2 = ctk.CTkEntry(f2, width=80)
        self.entry_od2.insert(0, "1.00")
        self.entry_od2.pack(side="left", padx=5)
        self.btn_od2 = ctk.CTkButton(f2, text="Leer voltaje", command=self._leer_punto_od2)
        self.btn_od2.pack(side="left", padx=10)
        self.lbl_od2 = ctk.CTkLabel(f2, text="Voltaje: ---")
        self.lbl_od2.pack(side="left", padx=5)

        self.lbl_od_resultado = ctk.CTkLabel(t, text="")
        self.lbl_od_resultado.pack(pady=10)

        self.btn_od_aplicar = ctk.CTkButton(
            t, text="Calcular y Aplicar Calibración de OD600", fg_color="#388e3c", hover_color="#2e7d32",
            command=self._aplicar_calibracion_od
        )
        self.btn_od_aplicar.pack(pady=10)

    # ---------- Temperatura ----------
    def _construir_tab_temp(self):
        t = self.tab_temp
        ctk.CTkLabel(t, text="Calibración de Temperatura (offset)", font=(FUENTE, 16, "bold")).pack(pady=(10, 5))
        ctk.CTkLabel(
            t, justify="left",
            text="Coloca un termómetro de referencia junto al DS18B20, espera a que\n"
                 "ambas lecturas se estabilicen e ingresa la temperatura de referencia."
        ).pack(pady=(0, 10))

        self.lbl_cal_temp_vigente = ctk.CTkLabel(t, text="Offset vigente en Arduino: ---")
        self.lbl_cal_temp_vigente.pack(pady=(0, 10))

        self.lbl_temp_actual = ctk.CTkLabel(t, text="Lectura actual del sensor: ---")
        self.lbl_temp_actual.pack(pady=5)

        f1 = ctk.CTkFrame(t)
        f1.pack(pady=10)
        ctk.CTkLabel(f1, text="Temperatura de referencia (°C):").pack(side="left", padx=5)
        self.entry_temp_ref = ctk.CTkEntry(f1, width=80)
        self.entry_temp_ref.pack(side="left", padx=5)

        self.btn_temp_aplicar = ctk.CTkButton(
            t, text="Calcular y Aplicar Offset de Temperatura", fg_color="#388e3c", hover_color="#2e7d32",
            command=self._aplicar_calibracion_temp
        )
        self.btn_temp_aplicar.pack(pady=15)

        self._refrescar_temp_actual()

    def _refrescar_temp_actual(self):
        if not self.winfo_exists():
            return
        with self.app.datos_lock:
            if self.app.ultimos_datos:
                temp = self.app.ultimos_datos[0]
                self.lbl_temp_actual.configure(text=f"Lectura actual del sensor: {temp:.2f} °C")
        self.after(1000, self._refrescar_temp_actual)

    # ---------- Lectura de voltaje crudo (promedio de N muestras) ----------
    def _iniciar_lectura_punto(self, tipo, punto):
        botones = {
            ('ph', 1): self.btn_ph1, ('ph', 2): self.btn_ph2,
        }
        labels = {
            ('ph', 1): self.lbl_ph1, ('ph', 2): self.lbl_ph2,
        }
        botones[(tipo, punto)].configure(state="disabled")
        labels[(tipo, punto)].configure(text="Leyendo...")
        self._muestras_actuales = []
        self._colectar_muestra(tipo, punto, self.MUESTRAS_POR_PUNTO)

    def _colectar_muestra(self, tipo, punto, restantes):
        self.app.solicitar_raw()
        self.after(self.INTERVALO_MUESTRA_MS, lambda: self._revisar_muestra(tipo, punto, restantes))

    def _revisar_muestra(self, tipo, punto, restantes):
        with self.app.raw_lock:
            raw = self.app.ultimo_raw
        if raw:
            v_ph, v_od, ts = raw
            if time.time() - ts < 1.5:  # dato fresco
                valor = v_ph if tipo == 'ph' else v_od
                self._muestras_actuales.append(valor)

        if restantes > 1:
            self._colectar_muestra(tipo, punto, restantes - 1)
        else:
            self._finalizar_lectura_punto(tipo, punto)

    def _finalizar_lectura_punto(self, tipo, punto):
        botones = {
            ('ph', 1): self.btn_ph1, ('ph', 2): self.btn_ph2,
        }
        labels = {
            ('ph', 1): self.lbl_ph1, ('ph', 2): self.lbl_ph2,
        }
        botones[(tipo, punto)].configure(state="normal")

        if not self._muestras_actuales:
            labels[(tipo, punto)].configure(text="Voltaje: SIN DATOS")
            mostrar_aviso(self, "Calibración", "No se recibió respuesta del Arduino. Verifica la conexión.")
            return

        promedio = sum(self._muestras_actuales) / len(self._muestras_actuales)
        labels[(tipo, punto)].configure(text=f"Voltaje: {promedio:.4f} V")

        if tipo == 'ph':
            self.punto_ph[punto] = promedio

    # ---------- OD600: captura de blanco y punto de muestra ----------
    def _capturar_blanco_od(self):
        """Pide al Arduino que capture V0 físicamente (comando OD:BLANK), en
        vez de tomar un voltaje 'blanco' y meterlo en una recta lineal como
        si fuera pH. od_v0 vive en el Arduino/EEPROM; aquí solo esperamos
        la confirmación para reflejarla en la UI."""
        self.btn_od_blank.configure(state="disabled")
        self.lbl_od_blank.configure(text="Capturando...")
        with self.app.raw_lock:
            self.app.ultimo_blank_od = None
        self.app.enviar_comando("OD:BLANK")
        self.after(700, self._revisar_blanco_od)

    def _revisar_blanco_od(self):
        self.btn_od_blank.configure(state="normal")
        with self.app.raw_lock:
            blank = self.app.ultimo_blank_od
        if not blank:
            self.lbl_od_blank.configure(text="V_blanco: SIN RESPUESTA")
            mostrar_aviso(self, "Calibración OD600", "No se recibió confirmación del blanco. Verifica la conexión.")
            return
        v0, ts = blank
        self.od_v0_capturado = v0
        self.lbl_od_blank.configure(text=f"V_blanco: {v0:.4f} V")

    def _leer_punto_od2(self):
        if self.od_v0_capturado is None:
            mostrar_aviso(self, "Calibración OD600", "Primero captura el blanco (Punto 1).")
            return
        self.btn_od2.configure(state="disabled")
        self.lbl_od2.configure(text="Leyendo...")
        self._muestras_od2 = []
        self._colectar_muestra_od2(self.MUESTRAS_POR_PUNTO)

    def _colectar_muestra_od2(self, restantes):
        self.app.solicitar_raw()
        self.after(self.INTERVALO_MUESTRA_MS, lambda: self._revisar_muestra_od2(restantes))

    def _revisar_muestra_od2(self, restantes):
        with self.app.raw_lock:
            raw = self.app.ultimo_raw
        if raw:
            v_ph, v_od, ts = raw
            if time.time() - ts < 1.5:
                self._muestras_od2.append(v_od)

        if restantes > 1:
            self._colectar_muestra_od2(restantes - 1)
        else:
            self.btn_od2.configure(state="normal")
            if not self._muestras_od2:
                self.lbl_od2.configure(text="Voltaje: SIN DATOS")
                mostrar_aviso(self, "Calibración OD600", "No se recibió respuesta del Arduino. Verifica la conexión.")
                return
            self.punto_od2 = sum(self._muestras_od2) / len(self._muestras_od2)
            self.lbl_od2.configure(text=f"Voltaje: {self.punto_od2:.4f} V")

    # ---------- Cálculo y aplicación ----------
    def _calcular_recta(self, v1, y1, v2, y2):
        if v1 == v2:
            return None
        slope = (y2 - y1) / (v2 - v1)
        intercept = y1 - slope * v1
        return slope, intercept

    # Separación mínima de voltaje considerada "señal real" (por debajo de
    # esto, el ADC de 10 bits (~4.9 mV/cuenta) solo está viendo ruido y
    # cualquier pendiente calculada será inestable/sin sentido).
    VOLTAJE_MIN_SEPARACION = 0.05

    # Un |slope| mayor a esto es prácticamente imposible en un circuito
    # real, tanto para pH (ADC 0-5V mapeado a pH 0-14: slope típico de
    # orden bajo, ±2 a ±10) como para OD600 (modelo Beer-Lambert). Un
    # slope disparado significa que los dos puntos de calibración eran
    # casi indistinguibles entre sí (voltajes casi idénticos en pH, o
    # razón V/V_blanco casi 1 en OD600), y produce una lectura siempre
    # recortada en un extremo (0/14 en pH, el techo de seguridad en
    # OD600) sin ningún error visible. Esto fue justo lo que causó que
    # ambos sensores se quedaran "pegados". Mismo umbral que usa el
    # firmware para rechazar CAL:PH/CAL:OD (ver SLOPE_SOSPECHOSO en
    # codigotesisV3.ino) -- se bloquea aquí también, sin opción de
    # forzarlo, porque el Arduino lo rechazaría de todas formas.
    SLOPE_SOSPECHOSO = 50.0

    def _aplicar_calibracion_ph(self):
        if self.punto_ph[1] is None or self.punto_ph[2] is None:
            mostrar_aviso(self, "Calibración pH", "Lee ambos puntos antes de calcular.")
            return

        if abs(self.punto_ph[1] - self.punto_ph[2]) < self.VOLTAJE_MIN_SEPARACION:
            mostrar_error(
                self, "Calibración pH",
                f"Los dos voltajes leídos son casi idénticos "
                f"({self.punto_ph[1]:.4f} V vs {self.punto_ph[2]:.4f} V, diferencia < "
                f"{self.VOLTAJE_MIN_SEPARACION*1000:.0f} mV).\n\n"
                "Con esa diferencia el cálculo solo ajusta ruido del ADC y produce una "
                "pendiente inestable. Verifica que el sensor esté realmente en el buffer "
                "correcto (o que no esté desconectado/flotando) antes de continuar."
            )
            return
        try:
            y1 = float(self.entry_ph1.get())
            y2 = float(self.entry_ph2.get())
        except ValueError:
            mostrar_error(self, "Calibración pH", "Los valores de buffer deben ser numéricos.")
            return

        recta = self._calcular_recta(self.punto_ph[1], y1, self.punto_ph[2], y2)
        if recta is None:
            mostrar_error(self, "Calibración pH", "Los dos voltajes leídos son iguales, no se puede calcular la recta.")
            return
        slope, intercept = recta

        if abs(slope) > self.SLOPE_SOSPECHOSO:
            # Bloqueo duro, sin opción de "aplicar de todas formas": el
            # firmware ahora rechaza este mismo umbral en CAL:PH (ver
            # codigotesisV3.ino, SLOPE_SOSPECHOSO), así que dejar que la
            # app diga "aplicado correctamente" aquí sería engañoso -- el
            # Arduino lo rechazaría en silencio y la calibración anterior
            # seguiría vigente sin que el usuario se entere.
            mostrar_error(
                self, "Slope de pH inusualmente grande",
                f"El slope calculado es {slope:.2f} (voltajes: {self.punto_ph[1]:.4f} V vs "
                f"{self.punto_ph[2]:.4f} V para buffers {y1}/{y2}).\n\n"
                "Un slope tan grande normalmente significa que los dos voltajes leídos son "
                "casi idénticos (a veces por una sola cuenta del ADC), y esto va a dejar el "
                "pH siempre pegado en 0 o en 14 sin importar la lectura real del sensor. El "
                "Arduino rechazaría este valor de todas formas.\n\n"
                "Verifica que el sensor esté realmente sumergido en cada buffer, que se haya "
                "enjuagado entre uno y otro, y que la lectura se haya estabilizado antes de "
                "presionar 'Leer'. Luego vuelve a leer ambos puntos e intenta de nuevo."
            )
            return

        self.lbl_ph_resultado.configure(text=f"slope={slope:.6f}  intercept={intercept:.6f}")

        if not self.app.enviar_comando(f"CAL:PH:{slope:.6f},{intercept:.6f}"):
            mostrar_error(self, "Calibración pH", "No se pudo enviar al Arduino (¿sigue conectado?).")
            return

        ok = self.app.guardar_calibracion_bd('ph', slope, intercept, notas=f"buffers {y1}/{y2}")
        if ok:
            mostrar_info(self, "Calibración pH", "Calibración de pH aplicada y guardada correctamente.")
        else:
            mostrar_aviso(self, "Calibración pH", "Se aplicó en el Arduino, pero no se pudo guardar en la BD.")

        self.after(500, self._mostrar_calibracion_vigente)

    def _aplicar_calibracion_od(self):
        """OD600 en el firmware se calcula con el modelo de Beer-Lambert:
            OD600 = od_slope * ( -log10(V / od_v0) ) + od_intercept
        NO como una recta lineal V->OD (ese era el bug: el wizard anterior
        ajustaba una recta v->OD igual que pH, pero el Arduino nunca
        consume esa recta así, y además nunca recibía el comando OD:BLANK,
        por lo que od_v0 se quedaba en 0 y OD600 siempre salía 0.000).

        Aquí: el Punto 1 (blanco) define od_v0 directamente en el Arduino
        (ver _capturar_blanco_od). El Punto 2 (muestra de OD600 conocido)
        se usa para resolver la pendiente, fijando intercept=0 -- que es lo
        físicamente correcto: en V=V0 (blanco), -log10(1)=0, así que
        OD600 debe dar 0 en el blanco.
        """
        import math

        if self.od_v0_capturado is None:
            mostrar_aviso(self, "Calibración OD600", "Captura primero el blanco (Punto 1).")
            return
        if self.punto_od2 is None:
            mostrar_aviso(self, "Calibración OD600", "Lee el voltaje del Punto 2 antes de calcular.")
            return

        v0 = self.od_v0_capturado
        v2 = self.punto_od2

        if abs(v2 - v0) < self.VOLTAJE_MIN_SEPARACION:
            mostrar_error(
                self, "Calibración OD600",
                f"El voltaje de la muestra ({v2:.4f} V) es casi idéntico al blanco "
                f"({v0:.4f} V); la diferencia es menor a {self.VOLTAJE_MIN_SEPARACION*1000:.0f} mV.\n\n"
                "Eso es ruido del ADC, no una señal real de turbidez: revisa que la muestra "
                "realmente tenga biomasa y que el sensor óptico esté bien alineado/limpio "
                "antes de calibrar."
            )
            return

        try:
            od2_conocido = float(self.entry_od2.get())
        except ValueError:
            mostrar_error(self, "Calibración OD600", "El valor de OD600 de la muestra debe ser numérico.")
            return

        if od2_conocido <= 0:
            mostrar_error(self, "Calibración OD600", "El OD600 conocido del Punto 2 debe ser mayor que 0.")
            return

        ratio = v2 / v0
        if ratio <= 0:
            mostrar_error(self, "Calibración OD600", "Voltaje inválido para calcular el logaritmo (¿sensor desconectado?).")
            return

        log_ratio = -math.log10(ratio)
        if abs(log_ratio) < 1e-3:
            mostrar_error(self, "Calibración OD600", "La razón V/V_blanco es prácticamente 1; no hay señal suficiente para calibrar.")
            return

        slope = od2_conocido / log_ratio
        intercept = 0.0

        # Igual que con pH: la separación de voltaje NO es suficiente para
        # detectar una calibración inestable, porque el modelo es
        # logarítmico. Dos voltajes que pasan el filtro de separación
        # mínima (VOLTAJE_MIN_SEPARACION) aún pueden dar una razón V/V0
        # muy cercana a 1 si V_blanco es grande, produciendo un slope
        # disparado que satura el OD600 en el techo de seguridad del
        # firmware (esto fue justo lo que causó que la gráfica se quedara
        # pegada en el techo otra vez).
        #
        # Bloqueo duro, sin opción de "aplicar de todas formas": el
        # firmware ahora rechaza este mismo umbral en CAL:OD (ver
        # codigotesisV3.ino, SLOPE_SOSPECHOSO), así que forzarlo aquí
        # solo terminaría en un rechazo silencioso del lado del Arduino.
        if abs(slope) > self.SLOPE_SOSPECHOSO:
            mostrar_error(
                self, "Slope de OD600 inusualmente grande",
                f"El slope calculado es {slope:.2f} (V_blanco={v0:.4f} V, muestra={v2:.4f} V, "
                f"OD600 conocido={od2_conocido}).\n\n"
                "Un slope tan grande normalmente significa que la razón V/V_blanco es casi 1, "
                "es decir que el sensor casi no detectó diferencia de turbidez entre el blanco "
                "y la muestra. Esto va a dejar el OD600 pegado en el techo de seguridad del "
                "firmware sin importar la lectura real. El Arduino rechazaría este valor de "
                "todas formas.\n\n"
                "Verifica que la muestra realmente tenga biomasa suficiente y que el sensor "
                "óptico esté limpio y bien alineado. Luego captura el blanco de nuevo e "
                "intenta la calibración otra vez."
            )
            return

        self.lbl_od_resultado.configure(
            text=f"V_blanco={v0:.4f}V  slope={slope:.6f}  intercept={intercept:.6f}"
        )

        # 1) Blanco ya fue enviado al Arduino con OD:BLANK (queda en EEPROM).
        # 2) Ahora enviamos slope/intercept.
        if not self.app.enviar_comando(f"CAL:OD:{slope:.6f},{intercept:.6f}"):
            mostrar_error(self, "Calibración OD600", "No se pudo enviar al Arduino (¿sigue conectado?).")
            return

        ok = self.app.guardar_calibracion_bd(
            'od', slope, intercept,
            notas=f"V_blanco={v0:.4f}V, punto2 OD={od2_conocido} @ {v2:.4f}V"
        )
        if ok:
            mostrar_info(self, "Calibración OD600", "Calibración de OD600 aplicada y guardada correctamente.")
        else:
            mostrar_aviso(self, "Calibración OD600", "Se aplicó en el Arduino, pero no se pudo guardar en la BD.")

        self.after(500, self._mostrar_calibracion_vigente)

    # Un offset de temperatura mayor a esto casi siempre indica un problema
    # de hardware (sensor flotando/mal contacto/dirección ROM incorrecta)
    # y no una desviación real de fábrica del DS18B20 (que suele ser <1°C).
    OFFSET_TEMP_SOSPECHOSO = 10.0

    def _aplicar_calibracion_temp(self):
        with self.app.datos_lock:
            actual = self.app.ultimos_datos[0] if self.app.ultimos_datos else None
        if actual is None:
            mostrar_aviso(self, "Calibración Temperatura", "Aún no hay lectura de temperatura del sensor.")
            return
        try:
            referencia = float(self.entry_temp_ref.get())
        except ValueError:
            mostrar_error(self, "Calibración Temperatura", "Ingresa la temperatura de referencia (numérica).")
            return

        # El offset ya incluido en 'actual' se retira antes de calcular el nuevo,
        # para no acumular offsets sobre offsets.
        offset_previo = self.app.calibracion_actual.get('temp', {}).get('offset') or 0.0
        lectura_sin_offset = actual - offset_previo
        nuevo_offset = referencia - lectura_sin_offset

        if abs(nuevo_offset) > self.OFFSET_TEMP_SOSPECHOSO:
            if not confirmar(
                self, "Offset inusualmente grande",
                f"El offset calculado es {nuevo_offset:.2f} °C (referencia={referencia:.2f} °C, "
                f"lectura cruda del sensor≈{lectura_sin_offset:.2f} °C).\n\n"
                "Un DS18B20 real casi nunca se desvía más de 1-2°C de fábrica. Un offset así "
                "de grande normalmente indica un problema de hardware (mal contacto, dirección "
                "ROM equivocada, cable suelto) más que una calibración legítima.\n\n"
                "¿Quieres aplicarlo de todas formas?"
            ):
                return

        if not self.app.enviar_comando(f"CAL:TEMP:{nuevo_offset:.4f}"):
            mostrar_error(self, "Calibración Temperatura", "No se pudo enviar al Arduino (¿sigue conectado?).")
            return

        # Se guarda con slope=1.0 fijo (no se usa) para mantener el esquema uniforme de la tabla
        ok = self.app.guardar_calibracion_bd('temp', 1.0, nuevo_offset, notas=f"ref={referencia}")
        if ok:
            mostrar_info(self, "Calibración Temperatura", f"Offset aplicado: {nuevo_offset:.4f} °C")
        else:
            mostrar_aviso(self, "Calibración Temperatura", "Se aplicó en el Arduino, pero no se pudo guardar en la BD.")

        self.after(500, self._mostrar_calibracion_vigente)

    def _mostrar_calibracion_vigente(self):
        if not self.winfo_exists():
            return
        cal = self.app.calibracion_actual
        ph = cal.get('ph', {})
        od = cal.get('od', {})
        temp = cal.get('temp', {})

        if ph.get('slope') is not None:
            self.lbl_cal_ph_vigente.configure(
                text=f"Calibración vigente en Arduino: slope={ph['slope']:.6f}  intercept={ph['intercept']:.6f}")
        if od.get('slope') is not None:
            self.lbl_cal_od_vigente.configure(
                text=f"Calibración vigente en Arduino: slope={od['slope']:.6f}  intercept={od['intercept']:.6f}")
        if temp.get('offset') is not None:
            self.lbl_cal_temp_vigente.configure(
                text=f"Offset vigente en Arduino: {temp['offset']:.4f} °C")


if __name__ == "__main__":
    asegurar_tabla_calibracion()
    app = LoginApp()
    app.mainloop()
