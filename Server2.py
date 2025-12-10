import socket
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from pathlib import Path
import collections

# --- LIBRERÍAS GRÁFICAS ---
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ==========================================
# === CONFIGURACIÓN ========================
# ==========================================
HOST = "0.0.0.0"
PORT = 4321
DATA_DIR = Path("datos_sensor")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Parámetros físicos (GUI)
N_WINDOW = 256
SAMPLE_RATE = 400

# Buffers de Datos (Gráfica) - Últimos 200 puntos
MAX_PLOT = 200 

# Buffers RAW
data_ax = collections.deque([0]*MAX_PLOT, maxlen=MAX_PLOT)
data_ay = collections.deque([0]*MAX_PLOT, maxlen=MAX_PLOT)
data_az = collections.deque([0]*MAX_PLOT, maxlen=MAX_PLOT)

# Buffers FEATURES
data_rms   = collections.deque([0]*MAX_PLOT, maxlen=MAX_PLOT)
data_peaks = collections.deque([0]*MAX_PLOT, maxlen=MAX_PLOT) # <-- Buffer para Picks
data_freq  = collections.deque([0]*MAX_PLOT, maxlen=MAX_PLOT)

# Variables de Estado Global
TARGET_PROTOCOL = "TCP" 
TARGET_STATE = "IDLE"
SHOW_FEATURES = False 

# ==========================================
# === LÓGICA DE DATOS ======================
# ==========================================

def guardar_procesar(raw_data, addr, protocol):
    """
    Recibe datos desde los hilos de red.
    Formato esperado CSV: ax,ay,az,gx,gy,gz,rms,peaks,freq
    """
    if "STATUS:IDLE" in raw_data: 
        return
    
    clean_data = raw_data.strip()
    
    # 1. Guardar en Archivo
    try:
        fname = DATA_DIR / f"{datetime.now().strftime('%Y%m%d')}_sensor.csv"
        with open(fname, "a") as f:
            f.write(f"{datetime.now()},{protocol},{clean_data}\n")
    except Exception as e:
        print(f"Error guardando archivo: {e}")

    # 2. Parsear para Gráfica
    try:
        parts = clean_data.split(',')
        # Esperamos 9 columnas (0..8)
        if len(parts) >= 9:
            # --- RAW DATA (Cols 0, 1, 2) ---
            data_ax.append(float(parts[0]))
            data_ay.append(float(parts[1]))
            data_az.append(float(parts[2]))
            
            # --- FEATURES (Cols 6, 7, 8) ---
            data_rms.append(float(parts[6]))   # RMS
            data_peaks.append(float(parts[7])) # Picks (Conteo)
            data_freq.append(float(parts[8]))  # Frecuencia Dominante
    except Exception:
        pass

def obtener_orden():
    """Genera la respuesta para el ESP32 con las órdenes actuales"""
    cmds = [f"CMD:SET_{TARGET_PROTOCOL}"]
    
    if TARGET_STATE == "RUNNING":
        cmds.append("CMD:START")
    else:
        cmds.append("CMD:STOP")
        
    return ";".join(cmds) + "\n"

# ==========================================
# === HILOS DE RED =========================
# ==========================================

def server_thread(sock_type):
    """Maneja sockets TCP o UDP según el argumento"""
    proto_name = "TCP" if sock_type == socket.SOCK_STREAM else "UDP"
    
    try:
        s = socket.socket(socket.AF_INET, sock_type)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        
        if sock_type == socket.SOCK_STREAM:
            s.listen(5)
            print(f"[*] Servidor {proto_name} escuchando en puerto {PORT}")
    except Exception as e:
        print(f"Error iniciando socket {proto_name}: {e}")
        return

    while True:
        try:
            if sock_type == socket.SOCK_STREAM:
                # --- Lógica TCP ---
                conn, addr = s.accept()
                conn.settimeout(0.5)
                try:
                    while True:
                        d = conn.recv(1024)
                        if not d: break
                        guardar_procesar(d.decode('utf-8','ignore'), addr, "TCP")
                        # Responder con órdenes
                        conn.sendall(obtener_orden().encode())
                except:
                    pass
                finally:
                    conn.close()
            else:
                # --- Lógica UDP ---
                d, addr = s.recvfrom(1024)
                guardar_procesar(d.decode('utf-8','ignore'), addr, "UDP")
                # Responder con órdenes
                s.sendto(obtener_orden().encode(), addr)
        except:
            pass

# ==========================================
# === INTERFAZ GRÁFICA =====================
# ==========================================

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Monitor de Vibraciones Industrial (ESP32 Edge)")
        self.root.geometry("900x700")

        # --- PANEL SUPERIOR (CONTROLES) ---
        control_frame = tk.Frame(root, bg="#e1e1e1", bd=2, relief=tk.RAISED)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        # Info Labels
        info_frame = tk.Frame(root, bg="#cccccc", bd=1)
        info_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=0)
        tk.Label(info_frame, text=f"Fs: {SAMPLE_RATE} Hz", bg="#cccccc").pack(side=tk.LEFT, padx=10)
        tk.Label(info_frame, text=f"Ventana: {N_WINDOW}", bg="#cccccc").pack(side=tk.LEFT, padx=10)
        tk.Label(info_frame, text=f"Resolución: {SAMPLE_RATE/N_WINDOW:.2f} Hz", bg="#cccccc").pack(side=tk.LEFT, padx=10)

        # Estado y Botones
        self.lbl_status = tk.Label(control_frame, text="ESTADO: DETENIDO", fg="red", bg="#e1e1e1", font=("Arial", 12, "bold"))
        self.lbl_status.pack(side=tk.LEFT, padx=20, pady=10)
        
        tk.Button(control_frame, text="INICIAR / DETENER", command=self.toggle_run, bg="white").pack(side=tk.LEFT, padx=10)
        
        self.btn_proto = tk.Button(control_frame, text=f"Modo Actual: {TARGET_PROTOCOL}", command=self.toggle_proto, bg="lightblue")
        self.btn_proto.pack(side=tk.LEFT, padx=10)
        
        # Checkbox Features
        self.var_feat = tk.BooleanVar(value=False)
        tk.Checkbutton(control_frame, text="Ver Features (RMS / Picks / FFT)", 
                       var=self.var_feat, command=self.update_mode, bg="#e1e1e1", font=("Arial", 10)).pack(side=tk.RIGHT, padx=20)

        # --- ÁREA DE GRÁFICO ---
        self.fig, self.ax = plt.subplots()
        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # Inicialización de líneas (modo RAW por defecto)
        self.setup_raw_plot()

        # Animación (cache_frame_data=False evita el warning)
        self.anim = FuncAnimation(self.fig, self.update_plot, interval=100, blit=False, cache_frame_data=False)

    def setup_raw_plot(self):
        """Configura el gráfico para ver Aceleración X, Y, Z"""
        self.ax.clear()
        self.ax.grid(True)
        self.l1, = self.ax.plot([], [], 'r', label='Acc X')
        self.l2, = self.ax.plot([], [], 'g', label='Acc Y')
        self.l3, = self.ax.plot([], [], 'b', label='Acc Z')
        self.ax.set_ylim(-32000, 32000)
        self.ax.set_title("Señal Cruda (Raw)")
        self.ax.legend(loc='upper right')

    def setup_feat_plot(self):
        """Configura el gráfico para ver RMS, Frecuencia y Picks"""
        self.ax.clear()
        self.ax.grid(True)
        # RMS (Magenta)
        self.l1, = self.ax.plot([], [], 'm', label='RMS (Z)')
        # Frecuencia (Negro)
        self.l2, = self.ax.plot([], [], 'k', label='Freq Dom (Hz)')
        # Picks (Cian)
        self.l3, = self.ax.plot([], [], 'c', label='Picks (Conteo)') 
        
        self.ax.set_ylim(0, 1000) # Rango aproximado para Features
        self.ax.set_title("Edge Computing: Features Calculados en ESP32")
        self.ax.legend(loc='upper right')

    def update_mode(self):
        """Callback del Checkbox"""
        global SHOW_FEATURES
        SHOW_FEATURES = self.var_feat.get()
        
        if SHOW_FEATURES:
            self.setup_feat_plot()
        else:
            self.setup_raw_plot()

    def update_plot(self, frame):
        """Loop de animación"""
        if SHOW_FEATURES:
            self.l1.set_data(range(len(data_rms)), data_rms)
            self.l2.set_data(range(len(data_freq)), data_freq)
            self.l3.set_data(range(len(data_peaks)), data_peaks)
        else:
            self.l1.set_data(range(len(data_ax)), data_ax)
            self.l2.set_data(range(len(data_ay)), data_ay)
            self.l3.set_data(range(len(data_az)), data_az)

    def toggle_run(self):
        global TARGET_STATE
        if TARGET_STATE == "IDLE":
            TARGET_STATE = "RUNNING"
            self.lbl_status.config(text="ESTADO: MIDIENDO", fg="green")
        else:
            TARGET_STATE = "IDLE"
            self.lbl_status.config(text="ESTADO: DETENIDO", fg="red")
            
            # Limpiar gráficos al detener (opcional, visualmente limpio)
            data_ax.clear(); data_ay.clear(); data_az.clear()
            data_rms.clear(); data_peaks.clear(); data_freq.clear()

    def toggle_proto(self):
        global TARGET_PROTOCOL
        if TARGET_PROTOCOL == "TCP":
            TARGET_PROTOCOL = "UDP"
        else:
            TARGET_PROTOCOL = "TCP"
        self.btn_proto.config(text=f"Modo Actual: {TARGET_PROTOCOL}")

# ==========================================
# === MAIN =================================
# ==========================================
if __name__ == "__main__":
    # Iniciar Hilos de Red
    t_tcp = threading.Thread(target=server_thread, args=(socket.SOCK_STREAM,), daemon=True)
    t_udp = threading.Thread(target=server_thread, args=(socket.SOCK_DGRAM,), daemon=True)
    t_tcp.start()
    t_udp.start()

    # Iniciar GUI
    root = tk.Tk()
    app = App(root)
    
    # Manejo de cierre seguro
    def on_closing():
        root.quit()
        root.destroy()
        import os
        os._exit(0)

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()