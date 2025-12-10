import socket
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from pathlib import Path
import collections

# --- LIBRERÍAS DE GRÁFICOS ---
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# --- CONFIGURACIÓN DE RED ---
HOST = "192.168.0.213"
PORT = 4321
DATA_DIR = Path("datos_sensor")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- CONFIGURACIÓN DE GRÁFICA ---
MAX_SAMPLES = 100  # Cantidad de puntos a mostrar en el tiempo
# Buffers circulares para los datos (se borran solos al llenarse)
data_ax = collections.deque([0]*MAX_SAMPLES, maxlen=MAX_SAMPLES)
data_ay = collections.deque([0]*MAX_SAMPLES, maxlen=MAX_SAMPLES)
data_az = collections.deque([0]*MAX_SAMPLES, maxlen=MAX_SAMPLES)

# --- VARIABLES DE CONTROL GLOBAL ---
TARGET_PROTOCOL = "TCP" 
TARGET_STATE = "IDLE"   

def guardar_y_graficar(raw_data, addr, protocol):
    """
    1. Guarda en CSV
    2. Parsea los datos para el gráfico
    """
    if "STATUS:IDLE" in raw_data:
        return

    now = datetime.now()
    clean_data = raw_data.strip()
    
    # 1. Guardar CSV
    linea = f"{now.isoformat()},{protocol},{addr[0]},{clean_data}\n"
    fname = DATA_DIR / f"{now.strftime('%Y%m%d')}_bmi270.csv"
    try:
        with fname.open("a", encoding="utf-8") as f:
            f.write(linea)
    except Exception:
        pass

    # 2. Actualizar Buffers para Gráfica
    # Formato esperado: ax,ay,az,gx,gy,gz
    try:
        parts = clean_data.split(',')
        if len(parts) >= 3:
            # Convertimos a float y añadimos al buffer
            val_x = float(parts[0])
            val_y = float(parts[1])
            val_z = float(parts[2])
            
            data_ax.append(val_x)
            data_ay.append(val_y)
            data_az.append(val_z)
    except ValueError:
        print(f"Error parseando datos: {clean_data}")

def obtener_orden():
    cmds = []
    cmds.append(f"CMD:SET_{TARGET_PROTOCOL}")
    if TARGET_STATE == "RUNNING":
        cmds.append("CMD:START")
    else:
        cmds.append("CMD:STOP")
    return ";".join(cmds) + "\n"

# --- HILOS DE RED  ---
def tcp_thread_func():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(5)
    print(f"[*] TCP Listener en {PORT}")

    while True:
        try:
            conn, addr = s.accept()
            conn.settimeout(0.5)
            try:
                while True:
                    data = conn.recv(1024)
                    if not data: break
                    msg = data.decode('utf-8', errors='ignore').strip()
                    guardar_y_graficar(msg, addr, "TCP")
                    conn.sendall(obtener_orden().encode())
            except:
                pass
            finally:
                conn.close()
        except:
            pass

def udp_thread_func():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    print(f"[*] UDP Listener en {PORT}")
    while True:
        try:
            data, addr = s.recvfrom(1024)
            msg = data.decode('utf-8', errors='ignore').strip()
            guardar_y_graficar(msg, addr, "UDP")
            s.sendto(obtener_orden().encode(), addr)
        except:
            pass

# --- INTERFAZ GRÁFICA  ---
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Monitor BMI270 - Tiempo Real")
        self.root.geometry("800x600") # Ventana más grande para el gráfico

        # --- 1. PANEL SUPERIOR (CONTROLES) ---
        top_frame = tk.Frame(root, bg="#f0f0f0", bd=2, relief=tk.RAISED)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        # Label Protocolo
        self.lbl_proto = tk.Label(top_frame, text=f"Protocolo Actual: {TARGET_PROTOCOL}", 
                                  font=("Arial", 12, "bold"), bg="#f0f0f0", fg="blue")
        self.lbl_proto.pack(side=tk.LEFT, padx=20, pady=10)

        # Botón Protocolo
        self.btn_proto = tk.Button(top_frame, text="Cambiar a UDP", command=self.toggle_protocol, bg="lightblue")
        self.btn_proto.pack(side=tk.LEFT, padx=10)

        # Separador visual
        ttk.Separator(top_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=20, pady=5)

        # Label Estado
        self.lbl_status = tk.Label(top_frame, text="Estado: DETENIDO", 
                                   font=("Arial", 12, "bold"), bg="#f0f0f0", fg="red")
        self.lbl_status.pack(side=tk.LEFT, padx=20)

        # Botón Inicio/Fin
        self.btn_run = tk.Button(top_frame, text="INICIAR MEDICIÓN", command=self.toggle_run, 
                                 bg="#90ee90", font=("Arial", 10, "bold"))
        self.btn_run.pack(side=tk.LEFT, padx=10)


        # --- 2. PANEL CENTRAL (GRÁFICO) ---
        self.graph_frame = tk.Frame(root, bg="white")
        self.graph_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Configuración de Matplotlib
        self.fig, self.ax = plt.subplots()
        self.fig.suptitle("Aceleración (X, Y, Z)", fontsize=14)
        
        # Inicializamos líneas vacías
        self.line_x, = self.ax.plot([], [], label='Acc X', color='r')
        self.line_y, = self.ax.plot([], [], label='Acc Y', color='g')
        self.line_z, = self.ax.plot([], [], label='Acc Z', color='b')
        
        self.ax.set_ylim(-10, 10) # Rango fijo aprox +/- 1g (9.8 m/s2) o +/- 8g según tu config
        self.ax.set_xlim(0, MAX_SAMPLES)
        self.ax.grid(True)
        self.ax.legend(loc='upper right')
        
        # Embed en Tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.graph_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Animación (llama a update_plot cada 100ms)
        self.anim = FuncAnimation(self.fig, self.update_plot, interval=100, blit=False, cache_frame_data=False)

    def update_plot(self, frame):
        # Si está detenido, no actualizamos visualmente para ahorrar recursos
        
        
        self.line_x.set_data(range(len(data_ax)), data_ax)
        self.line_y.set_data(range(len(data_ay)), data_ay)
        self.line_z.set_data(range(len(data_az)), data_az)
        
        # Auto-escalar eje Y si los movimientos son muy bruscos
        self.ax.relim()
        self.ax.autoscale_view()
        
        return self.line_x, self.line_y, self.line_z

    def toggle_protocol(self):
        global TARGET_PROTOCOL
        if TARGET_PROTOCOL == "TCP":
            TARGET_PROTOCOL = "UDP"
            self.lbl_proto.config(text="Protocolo Actual: UDP")
            self.btn_proto.config(text="Cambiar a TCP")
        else:
            TARGET_PROTOCOL = "TCP"
            self.lbl_proto.config(text="Protocolo Actual: TCP")
            self.btn_proto.config(text="Cambiar a UDP")

    def toggle_run(self):
        global TARGET_STATE
        if TARGET_STATE == "IDLE":
            # INICIAR
            TARGET_STATE = "RUNNING"
            self.lbl_status.config(text="Estado: MIDIENDO", fg="green")
            self.btn_run.config(text="DETENER MEDICIÓN", bg="#ffcccb")
        else:
            # DETENER Y REINICIAR GRÁFICO
            TARGET_STATE = "IDLE"
            self.lbl_status.config(text="Estado: DETENIDO", fg="red")
            self.btn_run.config(text="INICIAR MEDICIÓN", bg="#90ee90")
            
            # Limpiar buffers
            self.reset_graph()

    def reset_graph(self):
        print("Reiniciando gráfico...")
        data_ax.clear()
        data_ay.clear()
        data_az.clear()
        # Rellenar con ceros para mantener la longitud
        data_ax.extend([0]*MAX_SAMPLES)
        data_ay.extend([0]*MAX_SAMPLES)
        data_az.extend([0]*MAX_SAMPLES)

if __name__ == "__main__":
    # Hilos de red en background
    t_tcp = threading.Thread(target=tcp_thread_func, daemon=True)
    t_udp = threading.Thread(target=udp_thread_func, daemon=True)
    t_tcp.start()
    t_udp.start()

    # Interfaz Gráfica (Main Loop)
    root = tk.Tk()
    app = App(root)
    
    # Manejo correcto del cierre de ventana
    def on_closing():
        root.quit()
        root.destroy()
        import os
        os._exit(0) # Forzar cierre de hilos

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()