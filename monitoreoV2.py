import matplotlib
matplotlib.use('TkAgg')
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image
import pymysql
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime
import threading
import sys
import os
import math
from dotenv import load_dotenv

load_dotenv()

COLOR_TEMP = "#E63946"
COLOR_PH = "#2A9D8F"
COLOR_OD600 = "#9B59B6"
COLOR_ON = "#2ECC71"
COLOR_OFF = "#E74C3C"
COLOR_GRAY = "#555555"
COLOR_FONDO_PANEL = "#0f3460"
COLOR_ALERTA = "#E74C3C"
COLOR_ADVERTENCIA = "#F4B400"

# Escalas y rangos seguros de los gauges (deben coincidir con
# rango_control de controlfisicoV2.py, que es quien realmente controla).
RANGO_TEMP = (20.0, 45.0)
RANGO_TEMP_SEGURO = (36.5, 37.5)
RANGO_PH = (0.0, 14.0)
RANGO_PH_SEGURO = (6.8, 7.2)
RANGO_OD = (0.0, 3.5)
OD_INDUCCION = 0.7
OD_COSECHA = 2.0

# Mapa relé -> elemento del diagrama de proceso (P&ID)
# rele1=Calefacción, rele2=Bomba pH(OH), rele3=Bomba IPTG,
# rele4=Bomba Cosecha, rele5=Agitador, rele6=Aireación
# (mismo mapeo que usa controlfisicoV2.py / codigotesisV2.ino)

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

class SCADA_Bioreactor_Final(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SCADA BIOREACTOR v2026")
        
        self.after(0, lambda: self.state('zoomed'))
        self.attributes("-fullscreen", True)
        self.is_fullscreen = True
        
        self.bind("<F11>", self.toggle_fullscreen)
        self.bind("<Escape>", self.exit_fullscreen)
        
        self.monitoreo_activo = False
        self.hilo_en_curso = False
        self.estados_previos = {"r1": None, "r2": None, "r3": None, "r4": None, "r5": None, "r6": None,
                                "bph": None, "biptg": None, "bcos": None}
        self.estado_emergencia_anterior = None

        self.mostrar_login()

    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.attributes("-fullscreen", self.is_fullscreen)

    def exit_fullscreen(self, event=None):
        self.is_fullscreen = False
        self.attributes("-fullscreen", False)

    def conectar_db(self):
        try:
            conn = pymysql.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                port=DB_PORT,
                connect_timeout=30
            )
            print("¡CONEXIÓN ÉXITO con PyMySQL en monitoreo!")
            return conn
        except Exception as e:
            print(f"ERROR al conectar en monitoreo: {str(e)}")
            return None

    def mostrar_login(self):
        self.monitoreo_activo = False
        for w in self.winfo_children(): w.destroy()
        
        canvas_bg = tk.Canvas(self, highlightthickness=0)
        canvas_bg.place(x=0, y=0, relwidth=1, relheight=1)
        self.update()
        w_win, h_win = self.winfo_width(), self.winfo_height()
        for i in range(h_win):
            r, g, b = int(10 + i*10/h_win), int(20 + i*15/h_win), int(45 + i*20/h_win)
            color = f'#{max(0,r):02x}{max(0,g):02x}{max(0,b):02x}'
            canvas_bg.create_line(0, i, w_win, i, fill=color)

        card = ctk.CTkFrame(self, width=500, height=650, corner_radius=35, fg_color="white", border_width=3, border_color="#1A73E8")
        card.place(relx=0.5, rely=0.5, anchor="center")

        f_insignias = ctk.CTkFrame(card, fg_color="transparent")
        f_insignias.pack(pady=(35, 5))
        ctk.CTkLabel(f_insignias, text="☣", font=("Segoe UI", 45), text_color="#F4B400").pack(side="left", padx=15)
        ctk.CTkLabel(f_insignias, text="🧪", font=("Segoe UI", 45), text_color="#1A73E8").pack(side="left", padx=15)

        ctk.CTkLabel(card, text="SCADA LOGIN", font=("Segoe UI", 30, "bold"), text_color="#0D47A1").pack(pady=5)
        self.ent_user = self.crear_input_login(card, "ID DE OPERADOR / USUARIO")
        self.ent_pass = self.crear_input_login(card, "CÓDIGO DE ACCESO / CLAVE", secret=True)

        ctk.CTkButton(card, text="ACCEDER AL LABORATORIO", height=65, width=380, corner_radius=15, 
                      fg_color="#1A73E8", hover_color="#1557B0", font=("Segoe UI", 16, "bold"), 
                      command=self.validar_login).pack(pady=40)

    def crear_input_login(self, master, label_text, secret=False):
        frame = ctk.CTkFrame(master, fg_color="transparent")
        frame.pack(pady=12)
        ctk.CTkLabel(frame, text=label_text, font=("Segoe UI", 12, "bold"), text_color="#1A73E8").pack(anchor="w", padx=10)
        entry = ctk.CTkEntry(frame, width=380, height=55, corner_radius=12, fg_color="#F0F4F8", border_color="#1A73E8", border_width=2, text_color="black", font=("Segoe UI", 16))
        if secret: entry.configure(show="*")
        entry.pack()
        return entry

    def validar_login(self):
        user, pwd = self.ent_user.get().strip(), self.ent_pass.get().strip()
        if pwd == CLAVE_MAESTRA: 
            self.abrir_dashboard()
            return
        
        conn = self.conectar_db()
        if conn:
            try:
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                cursor.execute("SELECT * FROM usuarios WHERE username = %s AND password = %s", (user, pwd))
                if cursor.fetchone(): 
                    print("Login exitoso en monitoreo")
                    cursor.close()
                    conn.close()
                    self.abrir_dashboard()
                else: 
                    cursor.close()
                    conn.close()
                    messagebox.showerror("Error", "Credenciales incorrectas")
            except Exception as e:
                print(f"Error en consulta de login: {e}")
                messagebox.showerror("Error DB", f"Error en consulta: {e}")
            finally:
                if conn.open:
                    conn.close()
        else:
            messagebox.showerror("Conexión", "No se pudo alcanzar la base de datos")

    def abrir_dashboard(self):
        self.monitoreo_activo = True
        for w in self.winfo_children(): w.destroy()
        self.configure(fg_color="#0d1b2a")  # Fondo azul oscuro

        # Barra superior
        header = ctk.CTkFrame(self, height=60, corner_radius=0, fg_color="#1a1a2e")
        header.pack(fill="x")

        ctk.CTkLabel(header, text="DASHBOARD SCADA v2026", font=("Arial", 20, "bold"), text_color="white").pack(side="left", padx=20, pady=10)

        self.btn_paro = ctk.CTkButton(header, text="PARO DE EMERGENCIA", fg_color="#d32f2f", hover_color="#b71c1c",
                                      font=("Arial", 14, "bold"), command=self.activar_paro)
        self.btn_paro.pack(side="right", padx=10, pady=10)

        self.btn_reanudar = ctk.CTkButton(header, text="REANUDAR SISTEMA", fg_color="#388e3c", hover_color="#2e7d32",
                                          font=("Arial", 14, "bold"), command=self.reanudar_sistema_remoto)
        self.btn_reanudar.pack(side="right", padx=10, pady=10)

        ctk.CTkButton(header, text="Modo Ventana (F11)", fg_color="#555", hover_color="#444",
                      font=("Arial", 12), command=self.toggle_fullscreen).pack(side="right", padx=10, pady=10)

        self.btn_cerrar = ctk.CTkButton(header, text="CERRAR SESIÓN", fg_color="#777", hover_color="#666",
                                        font=("Arial", 12), command=self.mostrar_login)
        self.btn_cerrar.pack(side="right", padx=10, pady=10)

        self.lbl_status = ctk.CTkLabel(header, text="● OFFLINE", font=("Arial", 16, "bold"), text_color="red")
        self.lbl_status.pack(side="right", padx=30, pady=10)

        # ---------- Vista general: diagrama de proceso (P&ID) + gauges ----------
        overview_frame = ctk.CTkFrame(self, fg_color="#1a1a2e")
        overview_frame.pack(fill="x", padx=20, pady=10)

        pid_frame = ctk.CTkFrame(overview_frame, fg_color=COLOR_FONDO_PANEL, corner_radius=15)
        pid_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ctk.CTkLabel(pid_frame, text="DIAGRAMA DE PROCESO", font=("Arial", 13, "bold"),
                     text_color="white").pack(pady=(8, 0))

        self.fig_pid, self.ax_pid = plt.subplots(figsize=(6.5, 3.6))
        self.fig_pid.patch.set_facecolor(COLOR_FONDO_PANEL)
        self.ax_pid.set_facecolor(COLOR_FONDO_PANEL)
        self.fig_pid.subplots_adjust(left=0.01, right=0.99, top=0.98, bottom=0.02)
        self.canvas_pid = FigureCanvasTkAgg(self.fig_pid, master=pid_frame)
        self.canvas_pid.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

        gauges_frame = ctk.CTkFrame(overview_frame, fg_color=COLOR_FONDO_PANEL, corner_radius=15)
        gauges_frame.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(gauges_frame, text="VARIABLES DEL PROCESO", font=("Arial", 13, "bold"),
                     text_color="white").pack(pady=(8, 0))

        self.fig_gauges, (self.ax_gauge_temp, self.ax_gauge_ph, self.ax_gauge_od) = \
            plt.subplots(1, 3, figsize=(6.5, 3.6))
        self.fig_gauges.patch.set_facecolor(COLOR_FONDO_PANEL)
        for ax in (self.ax_gauge_temp, self.ax_gauge_ph, self.ax_gauge_od):
            ax.set_facecolor(COLOR_FONDO_PANEL)
        self.fig_gauges.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.02, wspace=0.15)
        self.canvas_gauges = FigureCanvasTkAgg(self.fig_gauges, master=gauges_frame)
        self.canvas_gauges.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

        # Dibujo inicial en estado "sin datos" (todo apagado/gris)
        self.dibujar_pid_completo(None)
        self.actualizar_gauges(RANGO_TEMP[0], RANGO_PH[0], RANGO_OD[0])

        # Gráficas
        graph_frame = ctk.CTkFrame(self, fg_color="#0f3460")
        graph_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.fig, (self.ax_temp, self.ax_ph, self.ax_od) = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
        self.fig.patch.set_facecolor('#0f3460')
        for ax in [self.ax_temp, self.ax_ph, self.ax_od]:
            ax.set_facecolor('#0f3460')
            ax.tick_params(colors="white")
            ax.grid(True, color="#555")

        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # Eventos
        eventos_frame = ctk.CTkFrame(self, fg_color="#0f3460")
        eventos_frame.pack(fill="x", padx=20, pady=10, side="bottom")

        ctk.CTkLabel(eventos_frame, text="REGISTRO DE EVENTOS", font=("Arial", 16, "bold"), text_color="white").pack(pady=5)

        columns = ("hora", "descripcion")
        self.tree = ttk.Treeview(eventos_frame, columns=columns, show="headings", height=4)
        self.tree.heading("hora", text="Hora")
        self.tree.heading("descripcion", text="Descripción")
        self.tree.pack(fill="x")

        scrollbar = ttk.Scrollbar(eventos_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.iniciar_ciclo()

    # ---------------------------------------------------------------
    # Gauges circulares (velocímetro) para Temperatura / pH / OD600
    # ---------------------------------------------------------------
    def dibujar_gauge(self, ax, valor, minimo, maximo, zonas, titulo, unidad, texto_valor=None):
        """Dibuja un gauge tipo velocímetro (semicírculo 180°->0°) en el eje
        dado. `zonas` es una lista de tuplas (z_min, z_max, color) que
        colorean el arco de fondo (p.ej. rojo/verde/rojo para rangos
        seguros, o azul/ámbar/verde para etapas de proceso como OD600)."""
        ax.clear()
        ax.set_xlim(-1.15, 1.15)
        ax.set_ylim(-0.35, 1.15)
        ax.set_aspect('equal')
        ax.axis('off')

        def valor_a_angulo(v):
            v = max(minimo, min(maximo, v))
            frac = (v - minimo) / (maximo - minimo) if maximo > minimo else 0
            return 180.0 - frac * 180.0  # 180°=mínimo (izq), 0°=máximo (der)

        # Arco de fondo por zonas de color
        for z_min, z_max, color in zonas:
            z_min_c = max(minimo, z_min)
            z_max_c = min(maximo, z_max)
            if z_max_c <= z_min_c:
                continue
            theta1 = valor_a_angulo(z_max_c)
            theta2 = valor_a_angulo(z_min_c)
            ax.add_patch(mpatches.Wedge((0, 0), 1.0, theta1, theta2, width=0.28,
                                         facecolor=color, edgecolor=COLOR_FONDO_PANEL, linewidth=1))

        # Aguja
        ang = math.radians(valor_a_angulo(valor))
        ax.plot([0, 0.82 * math.cos(ang)], [0, 0.82 * math.sin(ang)],
                color="white", linewidth=3, solid_capstyle="round")
        ax.add_patch(mpatches.Circle((0, 0), 0.055, facecolor="white", edgecolor=COLOR_FONDO_PANEL))

        texto = texto_valor if texto_valor is not None else f"{valor:.2f} {unidad}"
        ax.text(0, -0.22, texto, ha="center", va="center", fontsize=14,
                fontweight="bold", color="white")
        ax.text(0, 1.08, titulo, ha="center", va="bottom", fontsize=11,
                fontweight="bold", color="white")

    def actualizar_gauges(self, temp, ph, od600):
        zonas_temp = [
            (RANGO_TEMP[0], RANGO_TEMP_SEGURO[0], COLOR_ALERTA),
            (RANGO_TEMP_SEGURO[0], RANGO_TEMP_SEGURO[1], COLOR_ON),
            (RANGO_TEMP_SEGURO[1], RANGO_TEMP[1], COLOR_ALERTA),
        ]
        zonas_ph = [
            (RANGO_PH[0], RANGO_PH_SEGURO[0], COLOR_ALERTA),
            (RANGO_PH_SEGURO[0], RANGO_PH_SEGURO[1], COLOR_ON),
            (RANGO_PH_SEGURO[1], RANGO_PH[1], COLOR_ALERTA),
        ]
        # Para OD600 no hay "rango seguro": son etapas del proceso.
        zonas_od = [
            (RANGO_OD[0], OD_INDUCCION, "#3498DB"),      # Creciendo
            (OD_INDUCCION, OD_COSECHA, COLOR_ADVERTENCIA),  # Inducido
            (OD_COSECHA, RANGO_OD[1], COLOR_ON),          # Listo para cosecha
        ]

        self.dibujar_gauge(self.ax_gauge_temp, temp, *RANGO_TEMP, zonas_temp,
                            "TEMPERATURA", "°C", texto_valor=f"{temp:.1f} °C")
        self.dibujar_gauge(self.ax_gauge_ph, ph, *RANGO_PH, zonas_ph,
                            "pH", "", texto_valor=f"{ph:.2f}")
        self.dibujar_gauge(self.ax_gauge_od, od600, *RANGO_OD, zonas_od,
                            "OD600", "", texto_valor=f"{od600:.3f}")

        self.canvas_gauges.draw_idle()

    # ---------------------------------------------------------------
    # Diagrama de proceso (P&ID) animado según el estado de los relés
    # ---------------------------------------------------------------
    def dibujar_pid_completo(self, estados_reles):
        """estados_reles: dict con claves 'rele1'..'rele6' (bool) o None si
        no hay datos (todo se dibuja apagado/gris)."""
        if estados_reles is None:
            estados_reles = {f"rele{i}": False for i in range(1, 7)}

        def color_estado(clave):
            return COLOR_ON if estados_reles.get(clave, False) else COLOR_GRAY

        ax = self.ax_pid
        ax.clear()
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 9)
        ax.set_aspect('equal')
        ax.axis('off')

        # --- Tanque del biorreactor ---
        tanque = mpatches.FancyBboxPatch((3.6, 1.6), 2.8, 4.6,
                                          boxstyle="round,pad=0.05,rounding_size=0.25",
                                          facecolor="#16324a", edgecolor="white", linewidth=1.5)
        ax.add_patch(tanque)
        # Nivel de cultivo (decorativo)
        ax.add_patch(mpatches.Rectangle((3.75, 1.8), 2.5, 2.6,
                                         facecolor="#2A9D8F", alpha=0.45, edgecolor=None))
        ax.text(5.0, 6.55, "Biorreactor", ha="center", fontsize=9, color="white")

        # --- Agitador / motor M2 (rele5) ---
        color_motor = color_estado("rele5")
        ax.add_patch(mpatches.Rectangle((4.55, 6.2), 0.9, 0.55, facecolor=color_motor, edgecolor="white"))
        ax.text(5.0, 6.85, "M2 Agitador", ha="center", fontsize=8, color="white")
        # Eje del agitador dentro del tanque
        ax.plot([5.0, 5.0], [6.2, 2.2], color=color_motor, linewidth=2)

        # --- Calefacción / hot plate HT1 (rele1), debajo del tanque ---
        color_heater = color_estado("rele1")
        ax.add_patch(mpatches.FancyBboxPatch((3.6, 0.7), 2.8, 0.6,
                                              boxstyle="round,pad=0.02,rounding_size=0.1",
                                              facecolor=color_heater, edgecolor="white"))
        ax.text(5.0, 1.0, "HT1 Calefacción", ha="center", va="center", fontsize=8, color="black")

        # --- Bomba pH / OH Pump (rele2), izquierda-arriba ---
        self._dibujar_bomba(ax, 1.1, 5.7, color_estado("rele2"), "Bomba pH\n(NaOH)")
        ax.plot([1.6, 3.6], [5.7, 5.4], color=color_estado("rele2"), linewidth=2)

        # --- Bomba IPTG (rele3), izquierda-abajo ---
        self._dibujar_bomba(ax, 1.1, 3.4, color_estado("rele3"), "Bomba\nIPTG")
        ax.plot([1.6, 3.6], [3.4, 3.6], color=color_estado("rele3"), linewidth=2)

        # --- Aireación / Air Pump (rele6), derecha-arriba ---
        color_air = color_estado("rele6")
        self._dibujar_bomba(ax, 8.9, 5.7, color_air, "Air Pump\n(O2)")
        ax.plot([8.4, 6.4], [5.7, 5.4], color=color_air, linewidth=2)

        # --- Bomba de cosecha / Harvest Pump (rele4), derecha-abajo ---
        color_harvest = color_estado("rele4")
        self._dibujar_bomba(ax, 8.9, 3.4, color_harvest, "Bomba\nCosecha")
        ax.plot([6.4, 8.4], [3.6, 3.4], color=color_harvest, linewidth=2)
        # Frasco de cosecha (10°C)
        ax.add_patch(mpatches.Circle((9.5, 2.1), 0.35, facecolor="#4a90d9" if estados_reles.get("rele4") else "#2c3e50",
                                      edgecolor="white"))
        ax.plot([8.9, 9.5], [3.15, 2.45], color=color_harvest, linewidth=2)
        ax.text(9.5, 1.55, "10°C", ha="center", fontsize=7, color="white")

        self.canvas_pid.draw_idle()

    def _dibujar_bomba(self, ax, x, y, color, etiqueta):
        ax.add_patch(mpatches.Circle((x, y), 0.5, facecolor=color, edgecolor="white", linewidth=1.5))
        ax.text(x, y, "⟳", ha="center", va="center", fontsize=14, color="black" if color == COLOR_ON else "white")
        ax.text(x, y - 0.75, etiqueta, ha="center", va="top", fontsize=7.5, color="white")

    def iniciar_ciclo(self):
        if not self.monitoreo_activo:
            return
        if not self.hilo_en_curso:
            threading.Thread(target=self.tarea_descarga, daemon=True).start()
        self.after(5000, self.iniciar_ciclo)

    def tarea_descarga(self):
        self.hilo_en_curso = True
        conn = self.conectar_db()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT temperatura, ph, od600, fecha_hora, 
                           bomba_ph_on, bomba_iptg_on, bomba_cosecha_on, sistema_funcionando,
                           IFNULL(rele1, 0) AS rele1,
                           IFNULL(rele2, 0) AS rele2,
                           IFNULL(rele3, 0) AS rele3,
                           IFNULL(rele4, 0) AS rele4,
                           IFNULL(rele5, 0) AS rele5,
                           IFNULL(rele6, 0) AS rele6
                    FROM datos_bioreactor 
                    ORDER BY fecha_hora DESC LIMIT 20
                """)
                rows = cursor.fetchall()

                cursor.execute("SELECT emergencia FROM sistema_control WHERE id = 1")
                em_row = cursor.fetchone()
                em = bool(em_row[0]) if em_row is not None else False

                cursor.close()
                conn.close()

                if rows and len(rows) > 0:
                    self.after(0, lambda r=rows[::-1], em=em: self.actualizar_ui(r, em))
                else:
                    self.after(0, lambda: self.lbl_status.configure(text="● SIN DATOS", text_color="orange"))
            except Exception as e:
                print(f"Error descarga: {e}")
                self.after(0, lambda: self.lbl_status.configure(text="● ERROR BD", text_color="red"))
        else:
            self.after(0, lambda: self.lbl_status.configure(text="● ERROR BD", text_color="red"))
        self.hilo_en_curso = False

    def actualizar_ui(self, rows, emergencia):
        if not rows or len(rows) == 0:
            self.actualizar_gauges(RANGO_TEMP[0], RANGO_PH[0], RANGO_OD[0])
            self.dibujar_pid_completo(None)
            self.ax_temp.clear()
            self.ax_ph.clear()
            self.ax_od.clear()
            self.canvas.draw_idle()
            return

        u = rows[-1]
        if u[3] is not None:
            esta_vivo = (datetime.now() - u[3]).total_seconds() < 25
        else:
            esta_vivo = False

        if emergencia:
            self.btn_reanudar.configure(state="normal")
            self.lbl_status.configure(text="● EMERGENCIA", text_color="red")
        else:
            self.btn_reanudar.configure(state="normal")
            self.lbl_status.configure(text="● ONLINE" if esta_vivo else "● OFFLINE", 
                                      text_color=COLOR_ON if esta_vivo else "red")

        if esta_vivo:
            temp_actual = u[0] if u[0] is not None else 0.0
            ph_actual = u[1] if u[1] is not None else 0.0
            od_actual = u[2] if u[2] is not None else 0.0
            self.actualizar_gauges(temp_actual, ph_actual, od_actual)

            tiempos = [r[3].strftime("%H:%M") if r[3] is not None else "" for r in rows]
            self.ax_temp.clear()
            self.ax_ph.clear()
            self.ax_od.clear()

            self.ax_temp.plot(tiempos, [r[0] if r[0] is not None else 0 for r in rows], color=COLOR_TEMP, label="Temp")
            self.ax_temp.tick_params(axis='x', rotation=45, labelsize=7, colors="white")
            self.ax_temp.legend()

            self.ax_ph.plot(tiempos, [r[1] if r[1] is not None else 0 for r in rows], color=COLOR_PH, label="pH")
            self.ax_ph.tick_params(axis='x', rotation=45, labelsize=7, colors="white")
            self.ax_ph.legend()

            self.ax_od.plot(tiempos, [r[2] if r[2] is not None else 0 for r in rows], color=COLOR_OD600, label="OD600")
            self.ax_od.tick_params(axis='x', rotation=45, labelsize=7, colors="white")
            self.ax_od.legend()

            self.fig.tight_layout()
            self.canvas.draw_idle()

            # Estados de relé 1..6, alimentan el diagrama P&ID (heater, bombas, agitador, aireación)
            estados_reles = {
                "rele1": bool(u[8]),
                "rele2": bool(u[9]),
                "rele3": bool(u[10]),
                "rele4": bool(u[11]),
                "rele5": bool(u[12]),
                "rele6": bool(u[13]),
            }
            self.dibujar_pid_completo(estados_reles)

        else:
            self.actualizar_gauges(RANGO_TEMP[0], RANGO_PH[0], RANGO_OD[0])
            self.dibujar_pid_completo(None)
            self.ax_temp.clear()
            self.ax_ph.clear()
            self.ax_od.clear()
            self.canvas.draw_idle()

    def activar_paro(self):
        if messagebox.askyesno("CONFIRMACIÓN", "¿Activar PARO DE EMERGENCIA físico?"):
            threading.Thread(target=self.ejecutar_paro_db, daemon=True).start()

    def ejecutar_paro_db(self):
        conn = self.conectar_db()
        if conn:
            try:
                cursor = conn.cursor()
                sql = "UPDATE sistema_control SET emergencia = 1, rele1 = 0, rele2 = 0, rele3 = 0, rele4 = 0, rele5 = 0, rele6 = 0 WHERE id = 1"
                cursor.execute(sql)
                conn.commit()
                self.registrar_evento("!!! PARO DE EMERGENCIA ENVIADO DESDE SCADA !!!")
                self.after(0, lambda: messagebox.showinfo("Éxito", "Paro de emergencia activado en el sistema"))
            except Exception as e:
                self.after(0, lambda ex=e: messagebox.showerror("Error", f"No se pudo activar el paro: {ex}"))
            finally:
                if conn.open:
                    conn.close()
        else:
            self.after(0, lambda: messagebox.showerror("Conexión", "No se pudo conectar para activar el paro"))

    def reanudar_sistema_remoto(self):
        if not messagebox.askyesno("CONFIRMACIÓN", "¿Reanudar el sistema después del paro de emergencia?"):
            return

        conn = self.conectar_db()
        if conn:
            try:
                cursor = conn.cursor()
                sql = "UPDATE sistema_control SET emergencia = 0, comando_reanudar = 1 WHERE id = 1"
                cursor.execute(sql)
                conn.commit()
                self.registrar_evento(">>> SOLICITUD DE REANUDACIÓN ENVIADA DESDE SCADA <<<")
                self.after(0, lambda: messagebox.showinfo("Reanudación", "Comando de reanudación enviado. El PC de control lo ejecutará."))
            except Exception as e:
                self.after(0, lambda ex=e: messagebox.showerror("Error", f"No se pudo reanudar: {ex}"))
            finally:
                if conn.open:
                    conn.close()
        else:
            messagebox.showerror("Conexión", "No se pudo conectar para reanudar el sistema")

    def registrar_evento(self, mensaje):
        def tarea():
            conn = self.conectar_db()
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO eventos (hora, descripcion) VALUES (%s, %s)", 
                                   (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), mensaje))
                    conn.commit()
                    hora_gui = datetime.now().strftime("%H:%M:%S")
                    self.after(0, lambda: self.tree.insert("", 0, values=(hora_gui, mensaje)))
                except Exception as e:
                    print(f"Error al registrar evento: {e}")
                finally:
                    if conn.open:
                        conn.close()
        threading.Thread(target=tarea, daemon=True).start()

if __name__ == "__main__":
    app = SCADA_Bioreactor_Final()
    app.mainloop()
