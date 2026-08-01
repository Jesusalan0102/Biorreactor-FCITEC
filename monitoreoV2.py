import matplotlib
matplotlib.use('TkAgg')
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image
import pymysql
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime
import threading
import sys
import os

COLOR_TEMP = "#E63946"
COLOR_PH = "#2A9D8F"
COLOR_OD600 = "#9B59B6"
COLOR_ON = "#2ECC71"
COLOR_OFF = "#E74C3C"
COLOR_GRAY = "#555555"

DB_HOST = 'bfn0iql8vbpvwgbmq9zk-mysql.services.clever-cloud.com'
DB_USER = 'unluguvpazazzigt'
DB_PASSWORD = '2WEzm3qBlwn7lfmSmXQB'
DB_NAME = 'bfn0iql8vbpvwgbmq9zk'
DB_PORT = 3306
CLAVE_MAESTRA = '1270345'

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

        # KPIs
        kpi_frame = ctk.CTkFrame(self, fg_color="#1a1a2e")
        kpi_frame.pack(fill="x", padx=20, pady=10)

        self.ui_temp = self.crear_kpi_panel(kpi_frame, "TEMPERATURA °C", "0.0", COLOR_TEMP)
        self.ui_ph = self.crear_kpi_panel(kpi_frame, "pH", "0.00", COLOR_PH)
        self.ui_od600 = self.crear_kpi_panel(kpi_frame, "OD600", "0.000", COLOR_OD600)

        # LEDs - Ahora con 10 elementos (rele1 a rele6 + sistema + 3 bombas explícitas)
        leds_frame = ctk.CTkFrame(self, fg_color="#0f3460")
        leds_frame.pack(fill="x", padx=20, pady=5)

        self.leds_ref = []
        labels = [
            "Rele1 (Calefacción)", "Rele2 (pH)", "Rele3 (IPTG)", "Rele4 (Cosecha)",
            "Rele5 (Agitador)", "Rele6 (Aireación)", "Sistema",
            "Bomba pH", "Bomba IPTG", "Bomba Cosecha"
        ]
        for label in labels:
            f = ctk.CTkFrame(leds_frame, fg_color="transparent")
            f.pack(side="left", padx=12)
            led_canvas = tk.Canvas(f, width=30, height=30, bg="#0f3460", highlightthickness=0)
            led_canvas.pack(pady=5)
            led = led_canvas.create_oval(5, 5, 25, 25, fill=COLOR_GRAY)
            ctk.CTkLabel(f, text=label, font=("Arial", 11), text_color="white").pack()
            self.leds_ref.append((led_canvas, led))

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

    def crear_kpi_panel(self, master, label_text, valor_inicial, color):
        frame = ctk.CTkFrame(master, width=300, height=100, corner_radius=15, fg_color="#0f3460")
        frame.pack(side="left", padx=20)
        ctk.CTkLabel(frame, text=label_text, font=("Arial", 16), text_color="white").pack(pady=10)
        lbl_valor = ctk.CTkLabel(frame, text=valor_inicial, font=("Arial", 48, "bold"), text_color=color)
        lbl_valor.pack(pady=10)

        return lbl_valor

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
            self.ui_temp.configure(text="0.0")
            self.ui_ph.configure(text="0.00")
            self.ui_od600.configure(text="0.000")
            self.ax_temp.clear()
            self.ax_ph.clear()
            self.ax_od.clear()
            self.canvas.draw_idle()
            for i in range(10):
                self.leds_ref[i][0].itemconfig(self.leds_ref[i][1], fill=COLOR_GRAY)
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
            self.ui_temp.configure(text=f"{u[0]:.1f}" if u[0] is not None else "0.0")
            self.ui_ph.configure(text=f"{u[1]:.2f}" if u[1] is not None else "0.00")
            self.ui_od600.configure(text=f"{u[2]:.3f}" if u[2] is not None else "0.000")

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

            # Estados: rele1 a rele6 + sistema + 3 bombas (10 en total)
            estados = [
                u[8],   # rele1
                u[9],   # rele2 (pH)
                u[10],  # rele3 (IPTG)
                u[11],  # rele4 (Cosecha)
                u[12],  # rele5 (Agitador)
                u[13],  # rele6 (Aireación)
                u[7],   # sistema_funcionando
                u[4],   # bomba_ph_on
                u[5],   # bomba_iptg_on
                u[6]    # bomba_cosecha_on
            ]
            for i in range(10):
                color = COLOR_ON if estados[i] else COLOR_OFF
                self.leds_ref[i][0].itemconfig(self.leds_ref[i][1], fill=color)

        else:
            self.ui_temp.configure(text="0.0")
            self.ui_ph.configure(text="0.00")
            self.ui_od600.configure(text="0.000")
            self.ax_temp.clear()
            self.ax_ph.clear()
            self.ax_od.clear()
            self.canvas.draw_idle()
            for i in range(10):
                self.leds_ref[i][0].itemconfig(self.leds_ref[i][1], fill=COLOR_GRAY)

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