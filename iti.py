import sys
import os
import customtkinter as ctk
from ftplib import FTP
import threading
from tkinter import filedialog
import tkinter as tk
import webbrowser

# --- CONFIGURACIÓN DE TEMA ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

STRINGS = {
    "es": {
        "app_name": "XBOX TRANSFER TOOL v1.0",
        "sidebar_title": "XBOX TRANSFER TOOL",
        "mode_disconnected": "Estado: Desconectado",
        "btn_new_conn": "🔌 Conexión",
        "btn_refresh": "🔄",
        "btn_add_queue": "📂 Agregar",
        "btn_upload_all": "🚀 Subir",
        "btn_download_sel": "📥 Bajar",
        "btn_delete_sel": "🗑️ Borrar",
        "btn_stop": "✖ DETENER",
        "btn_connect": "CONECTAR",
        "status_ready": "SISTEMA LISTO",
        "dash_prom": "PrometheOS",
        "dash_std": "Estándar", # Mantener para el mensaje de advertencia
        "games": "Juegos",
        "emus": "Emus",
        "btn_advanced": "🛠️ Avanzado",
        "adv_warn_title": "ADVERTENCIA",
        "std_dash_warn_title": "DASHBOARD ESTÁNDAR DETECTADO",
        "adv_warn_msg": "¡ADVERTENCIA!\nEstás entrando con permisos totales sobre el sistema de archivos de la Xbox.\n\nCualquier cambio erróneo puede dejar la consola inoperable.\n¿Deseas continuar?",
        "btn_rename": "✏️ Renombrar",
        "rename_title": "Renombrar",
        "rename_msg": "Nuevo nombre para:",
        "btn_terminal": "💻 Terminal",
        "btn_confirm": "CONFIRMAR",
        "btn_cancel": "CANCELAR",
        "btn_toggle_theme_light": "☀️ Modo Claro",
        "btn_toggle_theme_dark": "🌙 Modo Oscuro",
        "std_dash_warn_msg": "Se ha detectado un dashboard estándar.\nLa copia de archivos puede ser más lenta o fallar.\n\nSe recomienda conectar desde PrometheOS.\nAsegúrate de encender tu consola Xbox con modchip MODXO instalado desde el botón de reset."
    }
}

T = STRINGS["es"]
CONFIG_FILE = "last_ip.txt"

def resource_path(relative_path):
    """ Obtiene la ruta absoluta para recursos, funciona para dev y para PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class XboxFTPManager(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(T["app_name"])
        self.geometry("1200x850")
        self.configure(fg_color="#0f0f0f")
        self.configure(fg_color=self._get_main_bg_color()) # Usar color dinámico
        
        # Lógica y Estados
        self.ftp = None
        self.upload_queue = []
        self.remote_selection = {} 
        self.advanced_mode = False
        self.stop_flag = False
        self.is_busy = False # Estado para bloquear UI durante operaciones
        self.global_files_xferred = 0 # Contador global de archivos transferidos
        self.total_files_to_xfer = 0  # Total de archivos a transferir en la operación actual
        self.host_ip = ctk.StringVar(value=self.load_last_ip())
        self.nav_buttons = []
        self.current_f_size = 0
        self.bytes_xferred = 0
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0) # Sidebar no crece
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0, minsize=275) # Terminal activa por defecto

        # --- SIDEBAR COMPACTO ---
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        
        ctk.CTkLabel(self.sidebar, text=T["sidebar_title"], font=("Segoe UI", 18, "bold"), text_color="#107C10").pack(pady=(20,0))
        ctk.CTkLabel(self.sidebar, text="By YAKARA", font=("Segoe UI", 12, "italic")).pack(pady=(0, 20)) # Eliminar text_color
        self.mode_label = ctk.CTkLabel(self.sidebar, text=T["mode_disconnected"], font=("Segoe UI", 11)) # Eliminar text_color
        self.mode_label.pack()
        
        self.btn_new_conn = ctk.CTkButton(self.sidebar, text=T["btn_new_conn"], height=32, command=lambda: self.show_page("conn")) # Eliminar fg_color, hover_color
        self.btn_new_conn.pack(pady=15, padx=20)

        self.btn_advanced = ctk.CTkButton(self.sidebar, text=T["btn_advanced"], height=32, command=self.toggle_advanced_mode)
        self.btn_advanced.pack(pady=5, padx=20)

        ctk.CTkButton(self.sidebar, text="Apoya al creador", height=28, command=self.open_paypal_link).pack(side="bottom", pady=10, padx=20) # Eliminar fg_color, hover_color
        self.btn_toggle_theme = ctk.CTkButton(self.sidebar, text="", height=32, command=self.toggle_theme)
        self.btn_toggle_theme.pack(side="bottom", pady=5, padx=20)
        self.update_theme_button_text()
        self.btn_term_toggle = ctk.CTkButton(self.sidebar, text=T["btn_terminal"], height=32, fg_color="#333", command=self.toggle_terminal)
        self.btn_term_toggle.pack(side="bottom", pady=5, padx=20)

        self.parts_container = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent", label_text="PARTICIONES DISPONIBLES", label_text_color="#107C10", height=400)
        self.parts_container.pack(fill="both", expand=True, padx=5, pady=5)

        # --- PÁGINAS ---
        self.page_conn = ctk.CTkFrame(self, fg_color="transparent") # Mantener transparent para que el fondo de la app se vea
        self.page_browser = ctk.CTkFrame(self, fg_color="transparent") # Mantener transparent
        self.setup_conn_page()
        self.setup_browser_page()

        # --- FOOTER OPTIMIZADO ---
        self.status_bar = ctk.CTkFrame(self, height=100, corner_radius=0, border_width=1) # Eliminar fg_color, border_color
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        
        # Layout de 3 columnas en el footer: Info | Barras | Botón
        self.status_bar.grid_columnconfigure(1, weight=1)
        
        self.info_frame = ctk.CTkFrame(self.status_bar, fg_color="transparent")
        self.info_frame.grid(row=0, column=0, padx=20, pady=10, sticky="w") # Mantener transparent
        
        self.progress_label = ctk.CTkLabel(self.info_frame, text=T["status_ready"], font=("Segoe UI", 13, "bold"), text_color="#107C10")
        self.progress_label.pack(anchor="w")
        self.file_label = ctk.CTkLabel(self.info_frame, text="Esperando conexión...", font=("Segoe UI", 11), text_color="#888")
        self.file_label.pack(anchor="w")

        self.bars_frame = ctk.CTkFrame(self.status_bar, fg_color="transparent")
        self.bars_frame.grid(row=0, column=1, padx=20, sticky="ew") # Mantener transparent
        self.setup_progress_bars()

        self.btn_stop = ctk.CTkButton(self.status_bar, text=T["btn_stop"], width=100, height=35,
                                      fg_color="#502020", hover_color="#801010", command=self.request_stop, state="disabled")
        self.btn_stop.grid(row=0, column=2, padx=20)

        # --- TERMINAL DE PROCESOS (DERECHA) ---
        self.terminal_visible = True
        self.terminal_frame = ctk.CTkFrame(self, width=275, corner_radius=0, border_width=1)
        self.terminal_frame.grid_propagate(False) # Evita que los hijos (el texto) expandan el frame
        self.terminal_frame.grid(row=0, column=2, sticky="nsew")
        
        lbl_term = ctk.CTkLabel(self.terminal_frame, text="TERMINAL", font=("Segoe UI", 12, "bold"), text_color="#107C10")
        lbl_term.pack(pady=10)

        self.terminal_text = tk.Text(self.terminal_frame, bg="#000", fg="#DDDDDD", font=("Consolas", 10), 
                                     borderwidth=0, padx=10, pady=10, state='disabled', width=1) # width=1 es la clave
        self.terminal_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.terminal_text.tag_config("info", foreground="#DDDDDD")
        self.terminal_text.tag_config("error", foreground="#FF3131")
        self.terminal_text.tag_config("success", foreground="#39FF14")
        self.terminal_text.tag_config("warn", foreground="#FF8C00")

        self.show_page("conn")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_progress_bars(self):
        # Archivo actual
        f_box = ctk.CTkFrame(self.bars_frame, fg_color="transparent")
        f_box.pack(fill="x", pady=2) # Mantener transparent
        self.perc_file = ctk.CTkLabel(f_box, text="0%", width=40, font=("Consolas", 10))
        self.perc_file.pack(side="right")
        self.p_bar_file = ctk.CTkProgressBar(f_box, height=8, progress_color="#107C10") # Eliminar fg_color
        self.p_bar_file.set(0)
        self.p_bar_file.pack(side="left", fill="x", expand=True, padx=5)

        # Total cola
        g_box = ctk.CTkFrame(self.bars_frame, fg_color="transparent")
        g_box.pack(fill="x", pady=2) # Mantener transparent
        self.perc_gen = ctk.CTkLabel(g_box, text="0%", width=40, font=("Consolas", 10), text_color="#107C10")
        self.perc_gen.pack(side="right")
        self.p_bar_gen = ctk.CTkProgressBar(g_box, height=8, progress_color="#1db954") # Eliminar fg_color
        self.p_bar_gen.set(0)
        self.p_bar_gen.pack(side="left", fill="x", expand=True, padx=5)

    def setup_conn_page(self):
        c = ctk.CTkFrame(self.page_conn, corner_radius=12, border_width=1) # Eliminar fg_color, border_color
        c.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(c, text="IP XBOX", font=("Segoe UI", 14, "bold")).pack(pady=10)
        self.ip_entry = ctk.CTkEntry(c, textvariable=self.host_ip, width=200, justify="center") # Eliminar fg_color
        self.ip_entry.pack(pady=10, padx=40)
        ctk.CTkButton(c, text=T["btn_connect"], command=self.connect_ftp).pack(pady=20) # Eliminar fg_color, hover_color

    def setup_browser_page(self):
        # 1. EXPLORADOR XBOX (ARRIBA)
        rem_h = ctk.CTkFrame(self.page_browser, height=35, corner_radius=0, border_width=1) # Eliminar fg_color, border_color
        rem_h.pack(fill="x", pady=(20, 0), padx=1)
        self.remote_label = ctk.CTkLabel(rem_h, text="📡 DIRECTORIO REMOTO XBOX", font=("Segoe UI", 11, "bold"), text_color="#107C10")
        self.remote_label.pack(side="left", padx=15)
        
        self.btn_refresh = ctk.CTkButton(rem_h, text=T["btn_refresh"], width=40, command=self.refresh_remote_view) # Eliminar fg_color
        self.btn_refresh.pack(side="right", padx=5)
        self.btn_delete = ctk.CTkButton(rem_h, text=T["btn_delete_sel"], width=100, height=28, fg_color="#502020", hover_color="#801010", command=self.run_batch_delete)
        self.btn_rename = ctk.CTkButton(rem_h, text=T["btn_rename"], width=100, height=28, fg_color="#222", command=self.run_rename)
        self.btn_download = ctk.CTkButton(rem_h, text=T["btn_download_sel"], width=100, height=28, fg_color="#203050", hover_color="#003087", command=self.run_batch_download)

        self.remote_view = ctk.CTkScrollableFrame(self.page_browser, fg_color="#000", corner_radius=0)
        self.remote_view.pack(fill="both", expand=True, padx=1, pady=1)
        self.remote_view.configure(fg_color=self._get_remote_view_bg_color()) # Usar color dinámico

        # 2. COLA DE SUBIDA (ABAJO)
        que_h = ctk.CTkFrame(self.page_browser, height=40, corner_radius=0, border_width=1) # Eliminar fg_color, border_color
        que_h.pack(fill="x", pady=(5,0), padx=1)
        ctk.CTkLabel(que_h, text="📥 COLA DE SUBIDA", font=("Segoe UI", 11, "bold")).pack(side="left", padx=15)
        
        self.btn_add_queue = ctk.CTkButton(que_h, text=T["btn_add_queue"], width=90, height=24, command=self.add_to_queue) # Eliminar fg_color
        self.btn_add_queue.pack(side="right", padx=5)
        self.btn_upload = ctk.CTkButton(que_h, text=T["btn_upload_all"], width=90, height=24, command=self.run_upload_queue) # Eliminar fg_color, hover_color
        self.btn_upload.pack(side="right", padx=15)

        self.queue_view = ctk.CTkScrollableFrame(self.page_browser, height=180, fg_color="#000", corner_radius=0)
        self.queue_view.pack(fill="x", padx=1, pady=1)

    # --- LÓGICA CORE ---
    def show_page(self, p):
        self.page_conn.grid_forget(); self.page_browser.grid_forget()
        if p == "conn": self.page_conn.grid(row=0, column=1, sticky="nsew")
        else: self.page_browser.grid(row=0, column=1, sticky="nsew")

    def toggle_advanced_mode(self):
        """Activa o desactiva el modo avanzado con advertencia."""
        if self.is_busy: return
        if not self.advanced_mode:
            if self.custom_confirm(T["adv_warn_title"], T["adv_warn_msg"]):
                self.advanced_mode = True
                self.btn_advanced.configure(fg_color="#107C10", hover_color="#0D5C0D")
                self.log("Modo Avanzado activado. Tenga precaución.", "warn")
                self.refresh_remote_view()
        else:
            self.advanced_mode = False
            # Restaurar colores por defecto del tema
            theme_fg = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
            theme_hover = ctk.ThemeManager.theme["CTkButton"]["hover_color"]
            self.btn_advanced.configure(fg_color=theme_fg, hover_color=theme_hover)
            self.log("Modo Avanzado desactivado.")
            self.refresh_remote_view()

    def log(self, msg, level="info"):
        """Agrega un mensaje a la terminal con un color según el nivel."""
        self.after(0, lambda: self._log_main_thread(msg, level))

    def _log_main_thread(self, msg, level):
        self.terminal_text.configure(state='normal')
        self.terminal_text.insert("end", f"> {msg}\n", level)
        self.terminal_text.see("end")
        self.terminal_text.configure(state='disabled')

    def toggle_terminal(self):
        """Muestra u oculta la terminal lateral."""
        if self.is_busy: return
        if self.terminal_visible:
            self.terminal_frame.grid_forget()
            self.grid_columnconfigure(2, weight=0, minsize=0) # Reset column 2
        else:
            self.grid_columnconfigure(2, weight=0, minsize=275) # Ahora sí se respetará este tamaño
            self.terminal_frame.grid(row=0, column=2, sticky="nsew") # Place terminal frame
        self.terminal_visible = not self.terminal_visible

    def connect_ftp(self):
        try:
            self.log(f"Intentando conectar a {self.host_ip.get()}...")
            self.file_label.configure(text=f"Conectando a {self.host_ip.get()}...")
            self.ftp = FTP()
            self.ftp.connect(self.host_ip.get(), 21, timeout=5)
            self.ftp.login("xbox", "xbox")
            self.ftp.encoding = "utf-8"
            self.log("Conexión establecida con éxito.", "success")
            with open(CONFIG_FILE, "w") as f: f.write(self.host_ip.get())
            self.scan_xbox_system()
        except Exception as e:
            self.custom_msg("ERROR", f"No se pudo conectar:\n{e}")

    def scan_xbox_system(self):
        self.ftp.cwd("/")
        # Usar LIST para mayor compatibilidad con dashboards estándar (C, E, F, G...)
        # ya que NLST a veces no devuelve las letras de unidad en la raíz.
        lines = []
        try:
            self.ftp.retrlines('LIST', lines.append)
        except:
            pass

        items = []
        for line in lines:
            parts = line.split(None, 8)
            if len(parts) >= 9:
                items.append(parts[-1].lower().strip())

        # Fallback a NLST si LIST no devolvió nada
        if not items:
            try:
                items = [i.lower().lstrip('/') for i in self.ftp.nlst()]
            except:
                items = []

        is_prom = any("hdd0" in i for i in items)
        dash = T["dash_prom"] if is_prom else T["dash_std"]
        
        if not is_prom:
            self.log("Se detectó un Dashboard estándar. Rendimiento reducido.", "warn")
            # Mostrar advertencia si no es PrometheOS
            self.custom_msg(T["std_dash_warn_title"], T["std_dash_warn_msg"])
        else: self.log("PrometheOS detectado. Rendimiento óptimo.", "success")

        for w in self.parts_container.winfo_children(): w.destroy()
        for w in self.remote_view.winfo_children(): w.destroy()
        self.remote_selection = {}
        parts_found = []
        self.nav_buttons = []
        mapping = {"e":["hdd0-e","e"],"f":["hdd0-f","f"],"g":["hdd0-g","g"]}
        
        for k, paths in mapping.items():
            for p in paths:
                if p in items:
                    parts_found.append(k.upper()) # Mantener para el mensaje de éxito
                    f = ctk.CTkFrame(self.parts_container, border_width=1) # Eliminar fg_color, border_color
                    f.pack(fill="x", pady=2, padx=2)
                    ctk.CTkLabel(f, text=f"DISCO {k.upper()}", font=("Segoe UI", 10, "bold")).pack(pady=2)
                    b1 = ctk.CTkButton(f, text=T["games"], height=24, command=lambda r=f"/{p}/": self.enter_dir(r, "Games")) # Eliminar fg_color, hover_color
                    b1.pack(pady=1, padx=10)
                    self.nav_buttons.append(b1)
                    b2 = ctk.CTkButton(f, text=T["emus"], height=24, command=lambda r=f"/{p}/": self.enter_dir(r, "Emulators")) # Eliminar fg_color, hover_color
                    b2.pack(pady=(1, 5), padx=10)
                    self.nav_buttons.append(b2)
                    break
        
        self.mode_label.configure(text=f"Xbox: {dash}", text_color="#107C10")
        self.file_label.configure(text=f"Conectado a {self.host_ip.get()} ({dash})")
        self.custom_msg("ÉXITO", f"Conexión establecida.\nDashboard Actual: {dash}\nParticiones Detectadas: {', '.join(parts_found)}")
        self.show_page("browser")

    def refresh_remote_view(self):
        path = "/"
        try:
            path = self.ftp.pwd()
            self.remote_label.configure(text=f"📡 DIRECTORIO REMOTO XBOX: {path}")
        except:
            pass

        for w in self.remote_view.winfo_children(): w.destroy()
        self.remote_selection = {}
        
        # Botón para subir de nivel si no estamos en la raíz y el modo avanzado está activo
        if path != "/" and self.advanced_mode:
            row = ctk.CTkFrame(self.remote_view, height=32, corner_radius=0) # Eliminar fg_color
            row.pack(fill="x", pady=1)
            lbl = ctk.CTkLabel(row, text="📁 .. (Subir un nivel)", font=("Segoe UI", 12, "bold"), text_color="#107C10", cursor="hand2")
            lbl.pack(side="left", padx=10)
            lbl.bind("<Button-1>", lambda e: self.navigate_to_remote_dir(".."))

        try:
            lines = []
            self.ftp.retrlines('LIST', lines.append)
            
            dirs = []
            files = []
            
            for line in lines: # Clasificar carpetas y archivos
                parts = line.split(None, 8)
                if len(parts) < 9: continue
                name = parts[-1]
                if name in [".", ".."]: continue
                if line.startswith("d"):
                    dirs.append(name)
                else:
                    files.append(name)
            
            dirs.sort(); files.sort()

            # Listar Directorios/Particiones (Clickables para navegar)
            for name in dirs:
                row = ctk.CTkFrame(self.remote_view, height=32, corner_radius=0) # Eliminar fg_color
                row.pack(fill="x", pady=1)
                var = ctk.BooleanVar()
                self.remote_selection[name] = var
                # Añadir comando al checkbox para actualizar el estado del botón de renombrar
                ctk.CTkCheckBox(row, text="", variable=var, width=20, checkbox_width=16, checkbox_height=16, command=self.update_selection_buttons_state).pack(side="left", padx=10)
                lbl = ctk.CTkLabel(row, text=f"📁 {name}", font=("Segoe UI", 12), cursor="hand2")
                lbl.pack(side="left")
                lbl.bind("<Button-1>", lambda e, n=name: self.navigate_to_remote_dir(n))

            # Listar Archivos
            for name in files:
                row = ctk.CTkFrame(self.remote_view, height=32, corner_radius=0) # Eliminar fg_color
                row.pack(fill="x", pady=1)
                var = ctk.BooleanVar()
                self.remote_selection[name] = var
                # Añadir comando al checkbox para actualizar el estado del botón de renombrar
                ctk.CTkCheckBox(row, text="", variable=var, width=20, checkbox_width=16, checkbox_height=16, command=self.update_selection_buttons_state).pack(side="left", padx=10)
                ctk.CTkLabel(row, text=f"📄 {name}", font=("Segoe UI", 12)).pack(side="left")

        except Exception as e:
            self.custom_msg("ERROR", f"No se pudo listar el contenido:\n{e}")
        finally:
            self.update_selection_buttons_state() # Actualizar el estado del botón después de refrescar la vista

    def navigate_to_remote_dir(self, dir_name):
        """Cambia el directorio actual en el FTP y refresca la vista."""
        try:
            self.ftp.cwd(dir_name)
            self.refresh_remote_view()
        except Exception as e:
            self.custom_msg("ERROR", f"No se pudo entrar en la carpeta:\n{e}")

    # --- HELPERS ---
    def custom_msg(self, title, text):
        msg = ctk.CTkToplevel(self)
        msg.title(title)
        msg.geometry("500x300")
        msg.configure(fg_color="#111")
        msg.attributes("-topmost", True)
        ctk.CTkLabel(msg, text=title, font=("Segoe UI", 14, "bold"), text_color="#107C10").pack(pady=10)
        ctk.CTkLabel(msg, text=text, font=("Segoe UI", 12), wraplength=450).pack(pady=10)
        ctk.CTkButton(msg, text="ACEPTAR", width=100, command=msg.destroy).pack(pady=10)

    def custom_confirm(self, title, text):
        self.confirm_res = False
        msg = ctk.CTkToplevel(self)
        msg.title(title)
        msg.geometry("400x220")
        msg.configure(fg_color="#111")
        msg.attributes("-topmost", True)
        msg.grab_set()
        ctk.CTkLabel(msg, text=title, font=("Segoe UI", 14, "bold"), text_color="#f90").pack(pady=15)
        ctk.CTkLabel(msg, text=text, font=("Segoe UI", 12), wraplength=350).pack(pady=10)
        btns = ctk.CTkFrame(msg, fg_color="transparent")
        btns.pack(pady=20)
        def set_res(res):
            self.confirm_res = res
            msg.destroy()
        ctk.CTkButton(btns, text=T["btn_confirm"], width=100, fg_color="#204020", hover_color="#107C10", command=lambda: set_res(True)).pack(side="left", padx=10)
        ctk.CTkButton(btns, text=T["btn_cancel"], width=100, fg_color="#333", command=lambda: set_res(False)).pack(side="left", padx=10)
        self.wait_window(msg)
        return self.confirm_res

    def toggle_theme(self):
        """Alterna entre el modo claro y oscuro de la interfaz."""
        if self.is_busy: return
        current_mode = ctk.get_appearance_mode()
        if current_mode == "Dark":
            ctk.set_appearance_mode("Light")
        else:
            ctk.set_appearance_mode("Dark")
        self.update_theme_button_text()
        # Actualizar colores de elementos que no se recrean pero tienen fg_color dinámico
        self.configure(fg_color=self._get_main_bg_color())
        self.remote_view.configure(fg_color=self._get_remote_view_bg_color())
        self.queue_view.configure(fg_color=self._get_remote_view_bg_color())
        # Ajustar colores de terminal
        is_dark = ctk.get_appearance_mode() == "Dark"
        terminal_bg = "#000" if is_dark else "#FFF"
        terminal_fg = "#DDDDDD" if is_dark else "#000" # Cambiado de #222 a #000
        self.terminal_text.configure(bg=terminal_bg, fg=terminal_fg)
        self.terminal_text.tag_config("info", foreground=terminal_fg) # La etiqueta 'info' también cambia

    def update_theme_button_text(self):
        current_mode = ctk.get_appearance_mode()
        if current_mode == "Dark":
            self.btn_toggle_theme.configure(text=T["btn_toggle_theme_light"], fg_color="#505020", hover_color="#7C7C10")
        else:
            self.btn_toggle_theme.configure(text=T["btn_toggle_theme_dark"], fg_color="#203050", hover_color="#003087")

    def update_selection_buttons_state(self):
        """Actualiza la visibilidad y el estado de los botones de acción según la selección."""
        selected_count = sum(v.get() for v in self.remote_selection.values())
        
        # Ocultar todos primero para manejar el orden dinámico
        self.btn_delete.pack_forget()
        self.btn_rename.pack_forget()
        self.btn_download.pack_forget()

        if self.is_busy:
            return

        # Mostrar según selección (Repackear con colores fijos evita el "cuadro blanco")
        if selected_count > 0:
            self.btn_download.pack(side="right", padx=5)
            if selected_count == 1:
                self.btn_rename.pack(side="right", padx=5)
            self.btn_delete.pack(side="right", padx=5)

    def run_rename(self):
        sel = [n for n, v in self.remote_selection.items() if v.get()]
        if not sel:
            self.custom_msg("INFO", "Seleccione *un único* elemento para renombrar.") # Mensaje más claro
            return
        old_name = sel[0]
        self.rename_res = None
        msg = ctk.CTkToplevel(self)
        msg.title(T["rename_title"])
        msg.geometry("400x200")
        msg.configure(fg_color=self._get_appearance_mode_color("modal_bg")) # Usar color dinámico
        msg.attributes("-topmost", True)
        msg.grab_set()
        ctk.CTkLabel(msg, text=f"{T['rename_msg']}\n{old_name}", font=("Segoe UI", 12), wraplength=350).pack(pady=20)
        entry = ctk.CTkEntry(msg, width=300); entry.insert(0, old_name); entry.pack(pady=10); entry.focus()
        def submit():
            self.rename_res = entry.get()
            msg.destroy()
        ctk.CTkButton(msg, text=T["btn_confirm"], width=100, command=submit).pack(pady=10) # Eliminar fg_color
        self.wait_window(msg)
        if self.rename_res and self.rename_res != old_name:
            try:
                self.ftp.rename(old_name, self.rename_res)
                self.log(f"Renombrado: {old_name} -> {self.rename_res}")
                self.refresh_remote_view()
            except Exception as e:
                self.custom_msg("ERROR", f"No se pudo renombrar:\n{e}")

    def on_closing(self):
        if self.is_busy:
            top = ctk.CTkToplevel(self)
            top.title("Advertencia")
            top.geometry("400x180")
            top.configure(fg_color=self._get_appearance_mode_color("modal_bg")) # Usar color dinámico
            top.attributes("-topmost", True)
            
            ctk.CTkLabel(top, text="Proceso en ejecución", font=("Segoe UI", 14, "bold"), text_color="#f90").pack(pady=(20, 10))
            ctk.CTkLabel(top, text="Cerrar ahora podría corromper los datos.\n¿Está seguro de que desea salir?", font=("Segoe UI", 12), wraplength=350).pack(pady=10)
            
            btns = ctk.CTkFrame(top, fg_color="transparent")
            btns.pack(pady=10)
            
            def confirm_close():
                self.stop_flag = True
                top.destroy()
                self.destroy()

            ctk.CTkButton(btns, text="SÍ, SALIR", width=100, fg_color="#622", hover_color="#822", command=confirm_close).pack(side="left", padx=10)
            ctk.CTkButton(btns, text="NO", width=100, fg_color="#222", command=top.destroy).pack(side="left", padx=10)
        else: self.destroy()

    def update_file_bar(self, p):
        self.after(0, lambda: [self.p_bar_file.set(p), self.perc_file.configure(text=f"{int(p*100)}%")])

    def update_gen_bar(self, p):
        self.after(0, lambda: [self.p_bar_gen.set(p), self.perc_gen.configure(text=f"{int(p*100)}%")])

    def set_ui_busy(self, busy, status_text="Procesando..."):
        self.is_busy = busy
        self.btn_stop.configure(state="normal" if busy else "disabled")
        
        state = "disabled" if busy else "normal"
        btns = [
            self.btn_new_conn, self.btn_refresh, self.btn_delete, 
            self.btn_download, self.btn_add_queue, self.btn_upload, 
            self.btn_toggle_theme, self.btn_advanced, self.btn_term_toggle, self.btn_rename
        ]
        for b in btns:
            try: b.configure(state=state)
            except: pass

        self.update_selection_buttons_state()

        for b in self.nav_buttons:
            try: b.configure(state=state)
            except: pass
            
        for row in self.queue_view.winfo_children():
            for child in row.winfo_children():
                if isinstance(child, ctk.CTkButton): child.configure(state=state)

        self.progress_label.configure(text=status_text)
        if not busy: 
            self.reset_ui()

    def reset_ui(self):
        self.p_bar_file.set(0); self.p_bar_gen.set(0)
        self.perc_file.configure(text="0%"); self.perc_gen.configure(text="0%")
        self.progress_label.configure(text=T["status_ready"])
        self.file_label.configure(text=f"Conectado a {self.host_ip.get()}")

    def request_stop(self):
        top = ctk.CTkToplevel(self)
        top.title("Confirmar")
        top.geometry("300x140")
        top.configure(fg_color=self._get_appearance_mode_color("modal_bg")) # Usar color dinámico
        top.attributes("-topmost", True)
        
        ctk.CTkLabel(top, text="¿Detener proceso y reconectar?", font=("Segoe UI", 12, "bold")).pack(pady=(20, 10))
        
        btns = ctk.CTkFrame(top, fg_color="transparent")
        btns.pack(pady=10)
        
        def confirm():
            top.destroy()
            self.stop_flag = True
            self.log("Operación detenida por el usuario.", "error")
            self.file_label.configure(text="Reiniciando conexión...")
            self.upload_queue = []
            self.refresh_queue_ui()
            try: self.ftp.close()
            except: pass
            self.after(1000, self.connect_ftp)
            
        ctk.CTkButton(btns, text="SÍ", width=80, fg_color="#622", hover_color="#822", command=confirm).pack(side="left", padx=10)
        ctk.CTkButton(btns, text="NO", width=80, fg_color="#222", command=top.destroy).pack(side="left", padx=10)

    def load_last_ip(self):
        try: return open(CONFIG_FILE, "r").read().strip()
        except: return "192.168.1."

    def add_to_queue(self):
        p = filedialog.askdirectory()
        if p:
            self.upload_queue.append(p)
            self.refresh_queue_ui()
            self.file_label.configure(text=f"Agregado: {os.path.basename(p)}")

    def open_paypal_link(self):
        webbrowser.open_new("https://www.paypal.com/paypalme/YAKARA")

    def _count_local_files(self, path):
        """Cuenta recursivamente el número de archivos en una ruta local."""
        count = 0
        for root, dirs, files in os.walk(path):
            count += len(files)
        return count

    def _count_remote_files(self, remote_path):
        """Cuenta recursivamente el número de archivos en una ruta remota (FTP)."""
        count = 0
        original_cwd = self.ftp.pwd() # Guardar el directorio actual
        try:
            self.ftp.cwd(remote_path) # Intentar cambiar al directorio remoto
            # Si tiene éxito, es un directorio, listar su contenido
            lines = []
            self.ftp.retrlines('LIST', lines.append)
            for line in lines:
                parts = line.split(None, 8)
                if len(parts) < 9: continue
                name = parts[-1]
                if name in [".", ".."]: continue
                if line.startswith("d"):
                    count += self._count_remote_files(name) # Llamada recursiva para subdirectorios
                else:
                    count += 1 # Es un archivo
        except Exception:
            # Si cwd falla, podría ser un archivo o una ruta inválida.
            # Si es un archivo, lo contamos. Si es inválido, contamos 0.
            try:
                self.ftp.size(remote_path) # Intentar obtener el tamaño para confirmar que es un archivo
                count = 1
            except Exception:
                pass # No es un archivo o es inaccesible, contar 0
        finally:
            self.ftp.cwd(original_cwd) # Siempre restaurar el directorio original
        return count

    def refresh_queue_ui(self):
        for w in self.queue_view.winfo_children(): w.destroy()
        for i, p in enumerate(self.upload_queue):
            row = ctk.CTkFrame(self.queue_view, fg_color="#080808", height=30)
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=f"📦 {os.path.basename(p)}", font=("Segoe UI", 11)).pack(side="left", padx=15) # Eliminar fg_color
            ctk.CTkButton(row, text="✖", width=25, height=20, fg_color="#502020", hover_color="#801010", command=lambda idx=i: [self.upload_queue.pop(idx), self.refresh_queue_ui()]).pack(side="right", padx=10)

    # --- WORKERS (MANTENIDOS PARA FUNCIONALIDAD) ---
    def run_batch_download(self):
        """Inicia el proceso de descarga por lotes en un hilo separado."""
        sel = [n for n, v in self.remote_selection.items() if v.get()]
        if sel:
            dest = filedialog.askdirectory()
            if dest:
                self.stop_flag = False
                self.set_ui_busy(True, "CALCULANDO ARCHIVOS A DESCARGAR...")
                threading.Thread(target=self._prepare_download_worker, args=(sel, dest), daemon=True).start()

    def _prepare_download_worker(self, items, dest):
        """Prepara el worker de descarga calculando el total de archivos."""
        self.global_files_xferred = 0
        self.total_files_to_xfer = 0
        current_remote_path = self.ftp.pwd() # Guardar la ruta actual
        for name in items:
            # Pasar la ruta completa a _count_remote_files
            self.total_files_to_xfer += self._count_remote_files(f"{current_remote_path}/{name}")
        
        self.after(0, lambda: self.set_ui_busy(True, "DESCARGANDO...")) # Actualizar estado en el hilo principal
        threading.Thread(target=self.download_worker, args=(items, dest), daemon=True).start()

    def download_worker(self, items, local_base):
        """Worker para descargar archivos/carpetas seleccionados."""
        try:
            self.log(f"Iniciando descarga de {len(items)} elementos...")
            for i, name in enumerate(items):
                if self.stop_flag: break
                self.after(0, lambda n=name: self.file_label.configure(text=f"Descargando: {n}"))
                self._download_recursive(f"{self.ftp.pwd()}/{name}", os.path.join(local_base, name))
            if not self.stop_flag: self.log("Descarga completada.", "success")
            if not self.stop_flag: self.after(0, lambda: self.custom_msg("ÉXITO", "Descarga completada."))
        finally: self.after(0, lambda: self.set_ui_busy(False))

    def _download_recursive(self, remote_item_path, local_path):
        """Descarga recursivamente un archivo o directorio remoto."""
        if self.stop_flag: return

        original_cwd = self.ftp.pwd() # Guardar el directorio actual
        is_directory = False
        try:
            self.ftp.cwd(remote_item_path) # Intentar cambiar de directorio
            is_directory = True
            self.ftp.cwd(original_cwd) # Volver al directorio original
        except Exception:
            pass # No es un directorio

        if is_directory:
            try:
                os.makedirs(local_path, exist_ok=True)
                self.ftp.cwd(remote_item_path) # Entrar al directorio
            
                lines = []
                self.ftp.retrlines('LIST', lines.append)
                
                for line in lines:
                    parts = line.split(None, 8)
                    if len(parts) < 9: continue
                    name = parts[-1]
                    if name in [".", ".."]: continue
                    
                    # Llamada recursiva para sub-elementos
                    self._download_recursive(f"{remote_item_path}/{name}", os.path.join(local_path, name))
                
                self.ftp.cwd("..") # Subir un nivel después de procesar todo el contenido
            except Exception as e:
                print(f"Error durante la descarga recursiva del directorio {remote_item_path}: {e}")
            finally:
                self.ftp.cwd(original_cwd) # Asegurarse de volver al directorio original
        else: # Es un archivo
            try:
                self.current_f_size = self.ftp.size(remote_item_path)
            except Exception:
                self.current_f_size = 0
            self.bytes_xferred = 0
            fname = os.path.basename(remote_item_path)
            self.after(0, lambda n=fname: self.file_label.configure(text=f"Descargando: {n}"))
            self.update_file_bar(0)
            self.log(f"Descargando: {fname}")
            with open(local_path, "wb") as f:
                def callback(data):
                    f.write(data)
                    self.xfer_callback(data)
                self.ftp.retrbinary(f"RETR {remote_item_path}", callback)
            
            # Actualizar el progreso global después de cada archivo
            self.global_files_xferred += 1
            if self.total_files_to_xfer > 0:
                self.after(0, lambda: self.update_gen_bar(self.global_files_xferred / self.total_files_to_xfer))

    def run_upload_queue(self):
        """Inicia el proceso de subida de la cola en un hilo separado."""
        if self.upload_queue:
            self.stop_flag = False
            self.set_ui_busy(True, "CALCULANDO ARCHIVOS A SUBIR...")
            threading.Thread(target=self._prepare_upload_worker, daemon=True).start()

    def _prepare_upload_worker(self):
        """Prepara el worker de subida calculando el total de archivos."""
        self.global_files_xferred = 0
        self.total_files_to_xfer = 0
        for lp in self.upload_queue:
            self.total_files_to_xfer += self._count_local_files(lp)
        
        self.after(0, lambda: self.set_ui_busy(True, "SUBIENDO...")) # Actualizar estado en el hilo principal
        threading.Thread(target=self.upload_worker, daemon=True).start()

    def upload_worker(self):
        """Worker para subir los elementos de la cola."""
        base = self.ftp.pwd()
        try:
            self.log(f"Iniciando subida de {len(self.upload_queue)} carpetas...")
            for i, lp in enumerate(self.upload_queue):
                if self.stop_flag: break
                fn = os.path.basename(lp)
                try: self.ftp.mkd(fn)
                except: pass
                self.ftp.cwd(fn)
                self._upload_recursive(lp)
                self.ftp.cwd(base)
            if not self.stop_flag: self.log("Subida de cola completada.", "success")
            if not self.stop_flag: 
                self.upload_queue = []; self.after(0, self.refresh_queue_ui)
                self.after(0, lambda: self.custom_msg("ÉXITO", "Subida completada."))
        finally: self.after(0, lambda: self.set_ui_busy(False)); self.after(0, self.refresh_remote_view)

    def _upload_recursive(self, ld):
        items = os.listdir(ld)
        files = [i for i in items if os.path.isfile(os.path.join(ld, i))]
        dirs = [i for i in items if os.path.isdir(os.path.join(ld, i))]
        files.sort(); dirs.sort()

        # 1. Subir archivos primero (evita fragmentación)
        for item in files:
            if self.stop_flag: raise Exception("Stop")
            p = os.path.join(ld, item)
            self.current_f_size = os.path.getsize(p)
            self.bytes_xferred = 0
            self.after(0, lambda n=item: self.file_label.configure(text=f"Enviando: {n}"))
            self.update_file_bar(0)
            self.log(f"Subiendo: {item}")
            with open(p, "rb") as f:
                def callback(data):
                    self.xfer_callback(data)
                self.ftp.storbinary(f"STOR {item}", f, callback=callback)
            
            # Actualizar el progreso global después de cada archivo
            self.global_files_xferred += 1
            if self.total_files_to_xfer > 0:
                self.after(0, lambda: self.update_gen_bar(self.global_files_xferred / self.total_files_to_xfer))

        # 2. Entrar en subcarpetas después
        for item in dirs:
            if self.stop_flag: raise Exception("Stop")
            p = os.path.join(ld, item)
            try: self.ftp.mkd(item)
            except: pass
            self.ftp.cwd(item); self._upload_recursive(p); self.ftp.cwd("..")
    def run_batch_delete(self):
        """Inicia el proceso de borrado por lotes en un hilo separado."""
        sel = [n for n, v in self.remote_selection.items() if v.get()]
        if sel:
            if self.custom_confirm("CONFIRMAR BORRADO", f"¿Estás seguro de que quieres borrar {len(sel)} elementos? Esta acción es irreversible."):
                self.stop_flag = False
                self.set_ui_busy(True, "BORRANDO...")
                threading.Thread(target=self.delete_worker, args=(sel,), daemon=True).start()

    def delete_worker(self, items):
        """Worker para borrar archivos/carpetas remotos."""
        try:
            self.log(f"Iniciando borrado de {len(items)} elementos...")
            for i, n in enumerate(items):
                if self.stop_flag: break
                self._delete_recursive(n)
                # No hay barra de progreso general para borrado, ya que no hay un "total de bytes" claro.
                # Podríamos actualizarla por número de elementos, pero no es tan crítico como la transferencia.
        finally: self.after(0, self.refresh_remote_view); self.after(0, lambda: self.set_ui_busy(False))

    def _delete_recursive(self, name):
        try:
            self.ftp.cwd(name)
            cnt = []; self.ftp.retrlines('LIST', cnt.append)
            for l in cnt:
                n = l.split(None, 8)[-1]
                if n not in [".", ".."]: self._delete_recursive(n)
            self.ftp.cwd(".."); 
            self.ftp.rmd(name)
            self.log(f"Carpeta borrada: {name}", "warn")
        except: 
            self.ftp.delete(name)
            self.log(f"Archivo borrado: {name}", "info")

    def xfer_callback(self, data):
        if self.stop_flag: raise Exception("Stop")
        self.bytes_xferred += len(data)
        if self.current_f_size > 0: self.update_file_bar(self.bytes_xferred / self.current_f_size)

    def enter_dir(self, base, target):
        try:
            self.ftp.cwd(base)
            if target.lower() not in [i.lower() for i in self.ftp.nlst()]: self.ftp.mkd(target)
            self.ftp.cwd(target); self.refresh_remote_view()
        except: pass

    # --- HELPERS DE COLOR (MOVIDOS DENTRO DE LA CLASE) ---
    def _get_main_bg_color(self): # Método de la clase
        return self._get_appearance_mode_color("main_bg")

    def _get_remote_view_bg_color(self): # Método de la clase
        return self._get_appearance_mode_color("remote_view_bg")

    def _get_appearance_mode_color(self, element): # Método de la clase
        if ctk.get_appearance_mode() == "Dark":
            if element == "main_bg": return "#0f0f0f"
            if element == "remote_view_bg": return "#000"
            if element == "modal_bg": return "#111"
        else: # Light mode
            if element == "main_bg": return "#e0e0e0"
            if element == "remote_view_bg": return "#ffffff"
            if element == "modal_bg": return "#f0f0f0"
        return None # Fallback

if __name__ == "__main__":
    app = XboxFTPManager()
    app.mainloop()