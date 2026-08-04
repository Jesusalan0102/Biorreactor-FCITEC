import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, ttk
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
from dotenv import load_dotenv
import bcrypt

TZ_TIJUANA = ZoneInfo("America/Tijuana")

load_dotenv()

# Configuración base de datos (Clever Cloud) - vía variables de entorno (.env local)
DB_HOST = os.environ.get('DB_HOST', '')
DB_USER = os.environ.get('DB_USER', '')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
DB_NAME = os.environ.get('DB_NAME', '')
DB_PORT = int(os.environ.get('DB_PORT', '3306'))
CLAVE_MAESTRA = os.environ.get('CLAVE_MAESTRA', '')

if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
    print("[ADVERTENCIA] Faltan variables de entorno de base de datos. "
          "Crea un archivo .env junto a este script (ver .env.example).")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def conectar_db():
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            connect_timeout=30
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
        self.title("Login - Control Bioreactor")
        self.update_idletasks()
        w = self.winfo_screenwidth()
        h = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+0+0")

        try:
            logo_pil = Image.open("logo.png")
            logo_pil = logo_pil.resize((500, 300))
            self.logo = ctk.CTkImage(light_image=logo_pil, dark_image=logo_pil, size=(500, 300))
        except Exception as e:
            print(f"No se pudo cargar logo: {e}")
            self.logo = None

        if self.logo:
            ctk.CTkLabel(self, image=self.logo, text="").pack(pady=20)

        tabview = ctk.CTkTabview(self)
        tabview.pack(expand=True, fill="both", padx=20, pady=20)

        tab_login = tabview.add("Iniciar Sesión")
        tab_admin = tabview.add("Administrar Usuarios")

        ctk.CTkLabel(tab_login, text="Usuario", font=("Arial", 14)).pack(pady=10)
        self.username_entry = ctk.CTkEntry(tab_login, width=300)
        self.username_entry.pack(pady=5)

        ctk.CTkLabel(tab_login, text="Contraseña", font=("Arial", 14)).pack(pady=10)
        self.password_entry = ctk.CTkEntry(tab_login, width=300, show="*")
        self.password_entry.pack(pady=5)

        ctk.CTkButton(tab_login, text="Iniciar Sesión", command=self.verificar_login).pack(pady=30)

        ctk.CTkLabel(tab_admin, text="Clave Maestra", font=("Arial", 14)).pack(pady=10)
        self.clave_entry = ctk.CTkEntry(tab_admin, width=300, show="*")
        self.clave_entry.pack(pady=5)

        ctk.CTkButton(tab_admin, text="Activar Administración", command=self.activar_admin).pack(pady=20)

        self.admin_frame = ctk.CTkFrame(tab_admin)
        self.admin_frame.pack(fill="both", expand=True)
        self.admin_frame.pack_forget()

    def activar_admin(self):
        if self.clave_entry.get() == CLAVE_MAESTRA:
            self.construir_admin_frame()
            self.admin_frame.pack(fill="both", expand=True)
            messagebox.showinfo("Acceso", "Administración activada")
        else:
            messagebox.showerror("Error", "Clave incorrecta")

    def construir_admin_frame(self):
        """Arma el panel de administración de usuarios (lista + registrar + eliminar).
        Se reconstruye cada vez que se activa, para no duplicar widgets."""
        for w in self.admin_frame.winfo_children():
            w.destroy()

        ctk.CTkLabel(self.admin_frame, text="Usuarios registrados",
                     font=("Arial", 16, "bold")).pack(pady=(10, 5))

        self.lista_usuarios_frame = ctk.CTkScrollableFrame(self.admin_frame, height=200)
        self.lista_usuarios_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.refrescar_lista_usuarios()

        ctk.CTkLabel(self.admin_frame, text="Registrar nuevo usuario",
                     font=("Arial", 14, "bold")).pack(pady=(20, 5))

        form = ctk.CTkFrame(self.admin_frame)
        form.pack(pady=5)
        ctk.CTkLabel(form, text="Usuario:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.nuevo_user_entry = ctk.CTkEntry(form, width=200)
        self.nuevo_user_entry.grid(row=0, column=1, padx=5, pady=5)
        ctk.CTkLabel(form, text="Contraseña:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.nuevo_pass_entry = ctk.CTkEntry(form, width=200, show="*")
        self.nuevo_pass_entry.grid(row=1, column=1, padx=5, pady=5)
        ctk.CTkButton(form, text="Registrar usuario",
                      command=self.registrar_usuario).grid(row=2, column=0, columnspan=2, pady=10)

    def refrescar_lista_usuarios(self):
        for w in self.lista_usuarios_frame.winfo_children():
            w.destroy()

        conn = conectar_db()
        if not conn:
            ctk.CTkLabel(self.lista_usuarios_frame, text="No se pudo conectar a la BD").pack(pady=10)
            return
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute("SELECT id, username FROM usuarios ORDER BY username")
            usuarios = cursor.fetchall()
        except Exception as e:
            ctk.CTkLabel(self.lista_usuarios_frame, text=f"Error: {e}").pack(pady=10)
            return
        finally:
            conn.close()

        if not usuarios:
            ctk.CTkLabel(self.lista_usuarios_frame, text="No hay usuarios registrados").pack(pady=10)
            return

        for u in usuarios:
            fila = ctk.CTkFrame(self.lista_usuarios_frame)
            fila.pack(fill="x", pady=2, padx=2)
            ctk.CTkLabel(fila, text=u["username"], width=200, anchor="w").pack(side="left", padx=5)
            ctk.CTkButton(
                fila, text="Eliminar", width=80, fg_color="#C0392B", hover_color="#922B21",
                command=lambda uid=u["id"], uname=u["username"]: self.eliminar_usuario(uid, uname)
            ).pack(side="right", padx=5)

    def registrar_usuario(self):
        user = self.nuevo_user_entry.get().strip()
        pwd = self.nuevo_pass_entry.get().strip()
        if not user or not pwd:
            messagebox.showerror("Error", "Usuario y contraseña son obligatorios")
            return

        conn = conectar_db()
        if not conn:
            messagebox.showerror("Error", "No se pudo conectar a la base de datos")
            return
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM usuarios WHERE username=%s", (user,))
            if cursor.fetchone():
                messagebox.showerror("Error", f"El usuario '{user}' ya existe")
                return
            hash_pwd = bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            cursor.execute("INSERT INTO usuarios (username, password) VALUES (%s, %s)", (user, hash_pwd))
            conn.commit()
            messagebox.showinfo("Éxito", f"Usuario '{user}' registrado correctamente")
            self.nuevo_user_entry.delete(0, "end")
            self.nuevo_pass_entry.delete(0, "end")
            self.refrescar_lista_usuarios()
        except Exception as e:
            messagebox.showerror("Error DB", f"No se pudo registrar: {e}")
        finally:
            conn.close()

    def eliminar_usuario(self, user_id, username):
        if not messagebox.askyesno(
            "Confirmar",
            f"¿Eliminar al usuario '{username}'? Esta acción no se puede deshacer."
        ):
            return

        conn = conectar_db()
        if not conn:
            messagebox.showerror("Error", "No se pudo conectar a la base de datos")
            return
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM usuarios WHERE id=%s", (user_id,))
            conn.commit()
            messagebox.showinfo("Éxito", f"Usuario '{username}' eliminado")
            self.refrescar_lista_usuarios()
        except Exception as e:
            messagebox.showerror("Error DB", f"No se pudo eliminar: {e}")
        finally:
            conn.close()

    def verificar_login(self):
        user = self.username_entry.get().strip()
        pwd = self.password_entry.get().strip()
        
        print(f"Usuario ingresado: '{user}'")
        
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
                    cursor.execute("SELECT id, password FROM usuarios WHERE username=%s", (user,))
                    result = cursor.fetchone()
                    if result:
                        stored = result["password"] or ""
                        pwd_bytes = pwd.encode("utf-8")
                        valido = False
                        if stored.startswith(("$2a$", "$2b$", "$2y$")):
                            valido = bcrypt.checkpw(pwd_bytes, stored.encode("utf-8"))
                        elif stored == pwd:
                            # Fila vieja en texto plano: validar una vez y migrar a hash
                            nuevo_hash = bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")
                            cursor.execute(
                                "UPDATE usuarios SET password=%s WHERE id=%s",
                                (nuevo_hash, result["id"]),
                            )
                            conn.commit()
                            valido = True

                        if valido:
                            print("Usuario encontrado en DB → abriendo Dashboard")
                            self.usuario_id = result['id']
                            acceso_concedido = True
                        else:
                            messagebox.showerror("Error", "Credenciales incorrectas")
                    else:
                        messagebox.showerror("Error", "Credenciales incorrectas (no encontrado en DB)")
                except Exception as e:
                    messagebox.showerror("Error DB", f"Error en consulta: {e}")
                finally:
                    conn.close()
            else:
                messagebox.showerror("Error", "No se pudo conectar a la base de datos")

        if acceso_concedido:
            print("Ocultando ventana de login...")
            self.withdraw()
            
            print("Creando Dashboard...")
            dashboard = DashboardApp(usuario_id=self.usuario_id)
            
            print("Forzando foco y traer al frente el dashboard...")
            dashboard.lift()
            dashboard.focus_force()
            dashboard.update()
            
            dashboard.protocol("WM_DELETE_WINDOW", lambda: [
                print("Cerrando dashboard → volviendo a login"),
                dashboard.destroy(),
                self.deiconify(),
                self.quit()
            ])


class DashboardApp(ctk.CTk):
    def __init__(self, usuario_id=None):
        super().__init__()
        self.usuario_id = usuario_id
        self.title("Dashboard BIOREACTOR")
        self.update_idletasks()
        w = self.winfo_screenwidth()
        h = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+0+0")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.serial = None
        self.puerto_var = tk.StringVar()
        self.etapa = "READY"
        self.emergencia = False
        self.pausado = False

        self.rele_estados = {1: False, 2: False, 3: False, 4: False, 5: False, 6: False}
        self.bomba_ph = False
        self.bomba_iptg = False
        self.bomba_cosecha = False

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
        self.ventana_calibracion = None

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
        top = ctk.CTkFrame(self, height=140)
        top.pack(fill="x", padx=0, pady=0)

        left = ctk.CTkFrame(top)
        left.pack(side="left", padx=20, pady=10)

        leds = ctk.CTkFrame(left)
        leds.pack()

        self.lbl_arranque = ctk.CTkLabel(leds, text="● Arranque", text_color="gray", font=("Arial", 13))
        self.lbl_arranque.pack(side="left", padx=6)

        self.lbl_falla = ctk.CTkLabel(leds, text="● Falla", text_color="gray", font=("Arial", 13))
        self.lbl_falla.pack(side="left", padx=6)

        self.lbl_emergencia = ctk.CTkLabel(leds, text="● Emergencia", text_color="gray", font=("Arial", 13))
        self.lbl_emergencia.pack(side="left", padx=6)

        self.lbl_ultimo = ctk.CTkLabel(left, text="Última lectura: ---", 
                                       font=("Arial", 15, "bold"), text_color="#00eeff")
        self.lbl_ultimo.pack(anchor="w", pady=8)

        center = ctk.CTkFrame(top)
        center.pack(side="left", expand=True, padx=40)

        puerto_frame = ctk.CTkFrame(center)
        puerto_frame.pack(pady=8)

        ctk.CTkLabel(puerto_frame, text="Puerto:").pack(side="left", padx=5)
        self.puerto_combo = ttk.Combobox(puerto_frame, textvariable=self.puerto_var, state="readonly", width=10)
        self.puerto_combo.pack(side="left", padx=5)
        self.refrescar_puertos()

        self.btn_conectar = ctk.CTkButton(puerto_frame, text="Conectar", width=100, command=self.conectar)
        self.btn_conectar.pack(side="left", padx=5)

        self.btn_desconectar = ctk.CTkButton(puerto_frame, text="Desconectar", width=100, 
                                            command=self.desconectar, state="disabled")
        self.btn_desconectar.pack(side="left", padx=5)

        right = ctk.CTkFrame(top)
        right.pack(side="right", padx=20)

        self.btn_emerg = ctk.CTkButton(right, text="PARO EMERGENCIA", fg_color="#d32f2f", 
                                      hover_color="#b71c1c", width=140, command=self.paro_emergencia)
        self.btn_emerg.pack(pady=5)

        self.btn_reanudar = ctk.CTkButton(right, text="Reanudar", fg_color="#388e3c", 
                                         hover_color="#2e7d32", width=140, command=self.reanudar, state="disabled")
        self.btn_reanudar.pack(pady=5)

        self.btn_iniciar_cultivo = ctk.CTkButton(right, text="Iniciar Cultivo", fg_color="#1976d2", 
                                                hover_color="#1565c0", width=140, command=self.iniciar_cultivo, state="disabled")
        self.btn_iniciar_cultivo.pack(pady=5)

        self.btn_calibracion = ctk.CTkButton(right, text="Calibración de Sensores", fg_color="#7b1fa2",
                                            hover_color="#6a1b9a", width=140, command=self.abrir_calibracion,
                                            state="disabled")
        self.btn_calibracion.pack(pady=5)

        self.lbl_etapa = ctk.CTkLabel(right, text="ETAPA: READY", font=("Arial", 22, "bold"), text_color="#ffeb3b")
        self.lbl_etapa.pack(pady=12)

        self.lbl_reles = ctk.CTkLabel(top, text="Relés: --- | Bombas: ---", font=("Arial", 12))
        self.lbl_reles.pack(anchor="center", pady=5)

        graph_frame = ctk.CTkFrame(self)
        graph_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.fig, (self.ax_temp, self.ax_ph, self.ax_od) = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)

        self.ax_temp.set_title("Temperatura (°C)")
        self.ax_ph.set_title("pH")
        self.ax_od.set_title("OD600")

        self.ax_temp.set_ylim(30, 45)
        self.ax_ph.set_ylim(5.0, 9.0)
        self.ax_od.set_ylim(0.0, 3.5)

        self.ax_temp.grid(True)
        self.ax_ph.grid(True)
        self.ax_od.grid(True)

    def refrescar_puertos(self):
        puertos = [p.device for p in serial.tools.list_ports.comports()]
        self.puerto_combo['values'] = puertos
        if puertos:
            self.puerto_combo.current(0)
            self.puerto_var.set(puertos[0])

    def conectar(self):
        if self.serial and self.serial.is_open:
            messagebox.showinfo("Info", "Ya está conectado")
            return

        puerto = self.puerto_var.get()
        if not puerto:
            messagebox.showwarning("Puerto", "Selecciona un puerto")
            return

        try:
            self.serial = serial.Serial(puerto, 9600, timeout=1)
            time.sleep(2)

            self.btn_conectar.configure(state="disabled")
            self.btn_desconectar.configure(state="normal")
            self.btn_iniciar_cultivo.configure(state="normal")
            self.btn_calibracion.configure(state="normal")

            self.lbl_etapa.configure(text="ETAPA: CONECTADO")
            self.lbl_ultimo.configure(text="Última lectura: --- (conectando...)")

            self.lbl_arranque.configure(text_color="green")

            threading.Thread(target=self.hilo_lectura, daemon=True).start()

            # Dar tiempo al Arduino a reiniciar (bootloader) antes de sincronizar calibración
            self.after(2500, self.sincronizar_calibracion_inicial)

            messagebox.showinfo("Éxito", f"Conectado a {puerto}")

        except Exception as e:
            self.lbl_falla.configure(text_color="red")
            messagebox.showerror("Error", f"Fallo al conectar:\n{e}")

    def desconectar(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.serial = None

        self.btn_conectar.configure(state="normal")
        self.btn_desconectar.configure(state="disabled")
        self.btn_iniciar_cultivo.configure(state="disabled")
        self.btn_calibracion.configure(state="disabled")
        self.lbl_etapa.configure(text="ETAPA: DESCONECTADO")
        self.lbl_ultimo.configure(text="Última lectura: ---")

        self.lbl_arranque.configure(text_color="gray")

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

                    if linea.startswith("CAL:TEMP:"):
                        try:
                            offset = float(linea[len("CAL:TEMP:"):])
                            self.calibracion_actual['temp'] = {'offset': offset}
                            print(f"[CAL] Temp offset={offset}")
                        except Exception as e:
                            print(f"[ERROR PARSEO CAL:TEMP] {e}")
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
                self.lbl_ultimo.configure(text=f"Última lectura: T={temp:.1f} (°C) | pH={ph:.2f} | OD600={od600:.3f}")

                self.guardar_en_bd(temp, ph, od600)
            else:
                print("Aún no hay datos nuevos para graficar...")

        if self.is_running:
            self.after(5000, self.actualizar_gui_periodica)  # Cada 5 segundos para reducir carga

    def guardar_en_bd(self, temp, ph, od600):
        conn = conectar_db()
        if not conn:
            print("[BD] No se pudo conectar para guardar")
            return

        try:
            cursor = conn.cursor()
            query = """
            INSERT INTO datos_bioreactor (
                fecha_hora,
                temperatura, ph, od600,
                rele1, rele2, rele3, rele4, rele5, rele6,
                bomba_ph_on, bomba_iptg_on, bomba_cosecha_on,
                sistema_funcionando
            ) VALUES (
                %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s
            )
            """
            # Se manda la hora de Tijuana explícita (naive) para que coincida
            # con lo que espera web/db.py al calcular ONLINE/OFFLINE. Si se
            # deja que MySQL use su DEFAULT CURRENT_TIMESTAMP (normalmente
            # UTC en Clever Cloud), el dashboard web queda marcado OFFLINE
            # aunque sí lleguen datos nuevos.
            fecha_hora_tijuana = datetime.now(TZ_TIJUANA).strftime("%Y-%m-%d %H:%M:%S")
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
                0 if self.emergencia else 1
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
            messagebox.showerror("Error DB", f"Error al guardar datos:\n{str(e)}")
        finally:
            conn.close()

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
            messagebox.showinfo("Cultivo", "Cultivo iniciado - agitación y aeración activadas (relés 5 y 6 ON)")

    def paro_emergencia(self):
        print("Ejecutando paro de emergencia...")
        self.emergencia = True
        self.etapa = "EMERGENCIA"
        self.lbl_emergencia.configure(text_color="red")

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
        messagebox.showwarning("EMERGENCIA", "Paro de emergencia activado - todos los relés OFF")

    def reanudar(self):
        print("Ejecutando reanudación completa...")
        self.emergencia = False
        self.etapa = "READY"
        self.pausado = False
        self.lbl_emergencia.configure(text_color="gray")

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
        messagebox.showinfo("Sistema", "Sistema reanudado completamente - relés reactivados")

    def actualizar_emergencia_bd(self, estado):
        conn = conectar_db()
        if conn:
            try:
                cursor = conn.cursor()
                sql = "UPDATE sistema_control SET emergencia = %s, comando_reanudar = 0 WHERE id = 1"
                cursor.execute(sql, (estado,))
                conn.commit()
                print(f"BD actualizada: emergencia = {estado}")
            except Exception as e:
                print(f"Error actualizando emergencia en BD: {e}")
            finally:
                conn.close()

    def chequear_emergencia_periodico(self):
        print("Chequeando BD para emergencia/reanudar (cada 3s)...")
        conn = conectar_db()
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
            finally:
                conn.close()
        else:
            print("No se pudo conectar a BD para chequeo")

        if self.is_running:
            self.after(3000, self.chequear_emergencia_periodico)

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

    def obtener_ultima_calibracion_bd(self, sensor):
        """Devuelve {'slope':..., 'intercept':...} con la calibración más
        reciente guardada para ese sensor, o None si nunca se ha calibrado."""
        conn = conectar_db()
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
            return None
        finally:
            conn.close()

    def guardar_calibracion_bd(self, sensor, slope, intercept, notas=""):
        conn = conectar_db()
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
            return False
        finally:
            conn.close()

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
            messagebox.showwarning("Calibración", "Conecta primero el Arduino")
            return
        if self.ventana_calibracion is not None and self.ventana_calibracion.winfo_exists():
            self.ventana_calibracion.lift()
            self.ventana_calibracion.focus_force()
            return
        self.ventana_calibracion = CalibracionWindow(self)

    def on_closing(self):
        self.is_running = False
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.destroy()


class CalibracionWindow(ctk.CTkToplevel):
    """Wizard de calibración de 2 puntos para pH y OD600, y de offset para
    temperatura. Lee voltaje crudo del Arduino (comando RAW), promedia
    varias muestras, calcula pendiente/intercepto y aplica + guarda."""

    MUESTRAS_POR_PUNTO = 6
    INTERVALO_MUESTRA_MS = 400

    def __init__(self, app: "DashboardApp"):
        super().__init__(app)
        self.app = app
        self.title("Calibración de Sensores")
        self.geometry("620x560")
        self.transient(app)

        self.punto_ph = {1: None, 2: None}   # voltaje promedio capturado
        self.punto_od = {1: None, 2: None}

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
        ctk.CTkLabel(t, text="Calibración de pH (2 puntos)", font=("Arial", 16, "bold")).pack(pady=(10, 5))
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
        ctk.CTkLabel(t, text="Calibración de Turbidez / OD600 (2 puntos)", font=("Arial", 16, "bold")).pack(pady=(10, 5))
        ctk.CTkLabel(
            t, justify="left",
            text="1) Punto 1 = 'blanco': sensor en medio de cultivo SIN inóculo (OD600 = 0).\n"
                 "2) Punto 2 = muestra con OD600 conocido (medido en espectrofotómetro externo)."
        ).pack(pady=(0, 10))

        self.lbl_cal_od_vigente = ctk.CTkLabel(t, text="Calibración vigente en Arduino: ---")
        self.lbl_cal_od_vigente.pack(pady=(0, 10))

        f1 = ctk.CTkFrame(t)
        f1.pack(pady=6, fill="x", padx=20)
        ctk.CTkLabel(f1, text="Punto 1 - OD600 conocido (blanco):").pack(side="left", padx=5)
        self.entry_od1 = ctk.CTkEntry(f1, width=80)
        self.entry_od1.insert(0, "0.00")
        self.entry_od1.pack(side="left", padx=5)
        self.btn_od1 = ctk.CTkButton(f1, text="Leer voltaje", command=lambda: self._iniciar_lectura_punto('od', 1))
        self.btn_od1.pack(side="left", padx=10)
        self.lbl_od1 = ctk.CTkLabel(f1, text="Voltaje: ---")
        self.lbl_od1.pack(side="left", padx=5)

        f2 = ctk.CTkFrame(t)
        f2.pack(pady=6, fill="x", padx=20)
        ctk.CTkLabel(f2, text="Punto 2 - OD600 conocido (muestra):").pack(side="left", padx=5)
        self.entry_od2 = ctk.CTkEntry(f2, width=80)
        self.entry_od2.insert(0, "1.00")
        self.entry_od2.pack(side="left", padx=5)
        self.btn_od2 = ctk.CTkButton(f2, text="Leer voltaje", command=lambda: self._iniciar_lectura_punto('od', 2))
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
        ctk.CTkLabel(t, text="Calibración de Temperatura (offset)", font=("Arial", 16, "bold")).pack(pady=(10, 5))
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
            ('od', 1): self.btn_od1, ('od', 2): self.btn_od2,
        }
        labels = {
            ('ph', 1): self.lbl_ph1, ('ph', 2): self.lbl_ph2,
            ('od', 1): self.lbl_od1, ('od', 2): self.lbl_od2,
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
            ('od', 1): self.btn_od1, ('od', 2): self.btn_od2,
        }
        labels = {
            ('ph', 1): self.lbl_ph1, ('ph', 2): self.lbl_ph2,
            ('od', 1): self.lbl_od1, ('od', 2): self.lbl_od2,
        }
        botones[(tipo, punto)].configure(state="normal")

        if not self._muestras_actuales:
            labels[(tipo, punto)].configure(text="Voltaje: SIN DATOS")
            messagebox.showwarning("Calibración", "No se recibió respuesta del Arduino. Verifica la conexión.")
            return

        promedio = sum(self._muestras_actuales) / len(self._muestras_actuales)
        labels[(tipo, punto)].configure(text=f"Voltaje: {promedio:.4f} V")

        if tipo == 'ph':
            self.punto_ph[punto] = promedio
        else:
            self.punto_od[punto] = promedio

    # ---------- Cálculo y aplicación ----------
    def _calcular_recta(self, v1, y1, v2, y2):
        if v1 == v2:
            return None
        slope = (y2 - y1) / (v2 - v1)
        intercept = y1 - slope * v1
        return slope, intercept

    def _aplicar_calibracion_ph(self):
        if self.punto_ph[1] is None or self.punto_ph[2] is None:
            messagebox.showwarning("Calibración pH", "Lee ambos puntos antes de calcular.")
            return
        try:
            y1 = float(self.entry_ph1.get())
            y2 = float(self.entry_ph2.get())
        except ValueError:
            messagebox.showerror("Calibración pH", "Los valores de buffer deben ser numéricos.")
            return

        recta = self._calcular_recta(self.punto_ph[1], y1, self.punto_ph[2], y2)
        if recta is None:
            messagebox.showerror("Calibración pH", "Los dos voltajes leídos son iguales, no se puede calcular la recta.")
            return
        slope, intercept = recta

        self.lbl_ph_resultado.configure(text=f"slope={slope:.6f}  intercept={intercept:.6f}")

        if not self.app.enviar_comando(f"CAL:PH:{slope:.6f},{intercept:.6f}"):
            messagebox.showerror("Calibración pH", "No se pudo enviar al Arduino (¿sigue conectado?).")
            return

        ok = self.app.guardar_calibracion_bd('ph', slope, intercept, notas=f"buffers {y1}/{y2}")
        if ok:
            messagebox.showinfo("Calibración pH", "Calibración de pH aplicada y guardada correctamente.")
        else:
            messagebox.showwarning("Calibración pH", "Se aplicó en el Arduino, pero no se pudo guardar en la BD.")

        self.after(500, self._mostrar_calibracion_vigente)

    def _aplicar_calibracion_od(self):
        if self.punto_od[1] is None or self.punto_od[2] is None:
            messagebox.showwarning("Calibración OD600", "Lee ambos puntos antes de calcular.")
            return
        try:
            y1 = float(self.entry_od1.get())
            y2 = float(self.entry_od2.get())
        except ValueError:
            messagebox.showerror("Calibración OD600", "Los valores de OD600 deben ser numéricos.")
            return

        recta = self._calcular_recta(self.punto_od[1], y1, self.punto_od[2], y2)
        if recta is None:
            messagebox.showerror("Calibración OD600", "Los dos voltajes leídos son iguales, no se puede calcular la recta.")
            return
        slope, intercept = recta

        self.lbl_od_resultado.configure(text=f"slope={slope:.6f}  intercept={intercept:.6f}")

        if not self.app.enviar_comando(f"CAL:OD:{slope:.6f},{intercept:.6f}"):
            messagebox.showerror("Calibración OD600", "No se pudo enviar al Arduino (¿sigue conectado?).")
            return

        ok = self.app.guardar_calibracion_bd('od', slope, intercept, notas=f"puntos OD {y1}/{y2}")
        if ok:
            messagebox.showinfo("Calibración OD600", "Calibración de OD600 aplicada y guardada correctamente.")
        else:
            messagebox.showwarning("Calibración OD600", "Se aplicó en el Arduino, pero no se pudo guardar en la BD.")

        self.after(500, self._mostrar_calibracion_vigente)

    def _aplicar_calibracion_temp(self):
        with self.app.datos_lock:
            actual = self.app.ultimos_datos[0] if self.app.ultimos_datos else None
        if actual is None:
            messagebox.showwarning("Calibración Temperatura", "Aún no hay lectura de temperatura del sensor.")
            return
        try:
            referencia = float(self.entry_temp_ref.get())
        except ValueError:
            messagebox.showerror("Calibración Temperatura", "Ingresa la temperatura de referencia (numérica).")
            return

        # El offset ya incluido en 'actual' se retira antes de calcular el nuevo,
        # para no acumular offsets sobre offsets.
        offset_previo = self.app.calibracion_actual.get('temp', {}).get('offset') or 0.0
        lectura_sin_offset = actual - offset_previo
        nuevo_offset = referencia - lectura_sin_offset

        if not self.app.enviar_comando(f"CAL:TEMP:{nuevo_offset:.4f}"):
            messagebox.showerror("Calibración Temperatura", "No se pudo enviar al Arduino (¿sigue conectado?).")
            return

        # Se guarda con slope=1.0 fijo (no se usa) para mantener el esquema uniforme de la tabla
        ok = self.app.guardar_calibracion_bd('temp', 1.0, nuevo_offset, notas=f"ref={referencia}")
        if ok:
            messagebox.showinfo("Calibración Temperatura", f"Offset aplicado: {nuevo_offset:.4f} °C")
        else:
            messagebox.showwarning("Calibración Temperatura", "Se aplicó en el Arduino, pero no se pudo guardar en la BD.")

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
