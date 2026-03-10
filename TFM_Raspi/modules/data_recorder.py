import os
import csv
import time
import sys
import numpy as np
import multiprocessing as mp
import matplotlib.pyplot as plt
from collections import deque
from datetime import datetime
from modules.signal_buffer import SignalBuffer

WINDOW_SIZE = 200   
OVERLAP = 150 

class FiltroExponencial3Ejes:
    def __init__(self, alpha=0.9):
        self.alpha = alpha
        self.g = np.zeros(3)
        self.primera_lectura = True

    def filtrar(self, ax, ay, az):
        a_t = np.array([ax, ay, az])
        
        if self.primera_lectura:
            self.g = a_t
            self.primera_lectura = False

        # LPF para la gravedad
        self.g = (self.alpha * self.g) + (1.0 - self.alpha) * a_t
        
        # HPF para la dinámica
        a_dyn = a_t - self.g
        return a_dyn

def plot_worker(queue, alias):
    try:
        plt.ion()
        fig, ax = plt.subplots()
        fig.canvas.manager.set_window_title(f"Energía - {alias}")
    except Exception as e:
        print(f"\n>> [ERROR GRÁFICO - {alias}] Fallo al inicializar la ventana de Matplotlib.")
        print(f">> Excepción del sistema: {e}")
        print(">> CAUSAS PROBABLES (Caso ejecución local HDMI):")
        print(">>   1. Violación de permisos: El script se ha ejecutado con 'sudo' (root). Ejecútelo con el usuario estándar (ej. 'pi').")
        print(">>   2. Servidor gráfico ausente: No hay un entorno de escritorio (GUI) activo o autologin configurado en la Raspberry Pi.")
        sys.exit(1)
    
    filtro = FiltroExponencial3Ejes(alpha=0.9)
    # Añadimos una nueva cola para almacenar el histórico de la energía
    x_data = deque(maxlen=150)
    y_data = deque(maxlen=150)
    z_data = deque(maxlen=150)
    e_data = deque(maxlen=150) 
    
    # Definimos las líneas
    line_x, = ax.plot([], [], 'r-', label='Eje X')
    line_y, = ax.plot([], [], 'g-', label='Eje Y')
    line_z, = ax.plot([], [], 'b-', label='Eje Z')
    line_e, = ax.plot([], [], 'k-', linewidth=2, label='Energía (Sin Gravedad)') 
    
    ax.legend(loc="upper left")
    
    while True:
        try:
            updated = False
            while not queue.empty():
                msg = queue.get_nowait()
                if msg == "STOP":
                    plt.close(fig)
                    return
                
                for s in msg:
                    x = s['x']
                    y = s['y']
                    z = s['z']

                    # Obtener la aceleración dinámica sin gravedad
                    a_dyn = filtro.filtrar(x, y, z)
                    
                    # Calculamos la Magnitud del Vector Aceleración 
                    energia = (a_dyn[0]**2 + a_dyn[1]**2 + a_dyn[2]**2) ** 0.5
                    
                    x_data.append(x)
                    y_data.append(y)
                    z_data.append(z)
                    e_data.append(energia)
                    
                updated = True
            
            if updated and len(x_data) > 0:
                line_x.set_data(range(len(x_data)), x_data)
                line_y.set_data(range(len(y_data)), y_data)
                line_z.set_data(range(len(z_data)), z_data)
                line_e.set_data(range(len(e_data)), e_data)
                
                ax.relim()
                ax.autoscale_view()
                
            fig.canvas.flush_events()
            time.sleep(0.05)
            
        except Exception:
            pass

class DataRecorder:
    def __init__(self):
        self.is_recording = False
        self.current_gesture = ""
        self.target_frames = 0
        
        self.aliases = {}
        self.buffers = {}           # Para almacenar un SignalBuffer por cada dispositivo
        self.recorded_rows = {}     # Filas aplanadas
        self.frames_recorded = {}   # Contador de frames grabados por MAC
        
        self.use_visualizer = False
        self.queues = {}
        self.processes = {}

    def start_recording(self, gesture, target_frames, connected_macs):
        self.current_gesture = gesture
        self.target_frames = target_frames
        self.is_recording = True
        
        for mac in connected_macs:
            # Window = 200, Overlap = 150
            self.buffers[mac] = SignalBuffer(WINDOW_SIZE, OVERLAP)
            self.frames_recorded[mac] = 0

    def stop_recording(self):
        self.is_recording = False

    def is_recording_complete(self, active_macs):
        # Si no hay dispositivos activos, hemos terminado (forzado)
        if not active_macs:
            return True
        if not self.frames_recorded:
            return False
        # Solo comprobamos los que siguen conectados
        return all(self.frames_recorded.get(mac, 0) >= self.target_frames for mac in active_macs)

    def discard_device(self, mac):
        # Eliminamos sus datos parciales de la RAM para que no se genere su .csv
        if mac in self.recorded_rows:
            del self.recorded_rows[mac]
        if mac in self.frames_recorded:
            del self.frames_recorded[mac]

    def get_max_frames_recorded(self):
        if not self.frames_recorded:
            return 0
        return max(self.frames_recorded.values())

    def process_incoming_data(self, mac, alias, samples):
        if mac not in self.aliases:
            self.aliases[mac] = alias
            
        # Si estamos grabando y este dispositivo aún necesita grabar más frames
        if self.is_recording and mac in self.buffers:
            if self.frames_recorded[mac] < self.target_frames:
                
                # Inyectar datos al buffer
                is_ready = self.buffers[mac].add_packet(samples)
                
                # Si el buffer dice que hay un frame completo listo
                if is_ready:
                    # Aplastar los datos: [200 X] + [200 Y] + [200 Z] + [Gesto]
                    flat_row = list(self.buffers[mac].acc_x) + \
                               list(self.buffers[mac].acc_y) + \
                               list(self.buffers[mac].acc_z) + \
                               [self.current_gesture]
                    
                    if mac not in self.recorded_rows:
                        self.recorded_rows[mac] = []
                        
                    self.recorded_rows[mac].append(flat_row)
                    self.frames_recorded[mac] += 1

        if self.use_visualizer and mac in self.queues:
            self.queues[mac].put(samples)

    def start_visualizers(self, connected_devices):
        self.stop_visualizers()
        for mac, info in connected_devices.items():
            alias = info['alias']
            q = mp.Queue()
            p = mp.Process(target=plot_worker, args=(q, alias), daemon=True)
            p.start()
            self.queues[mac] = q
            self.processes[mac] = p

    def stop_visualizers(self):
        for mac, q in self.queues.items():
            try:
                q.put("STOP")
            except:
                pass
        for p in self.processes.values():
            p.join(timeout=1.0)
        self.queues.clear()
        self.processes.clear()

    def clear_memory(self):
        self.recorded_rows.clear()
        self.frames_recorded.clear()

    def save_data(self, gestures_list, connected_devices):
        os.makedirs("grabaciones", exist_ok=True)
        saved_files = []
        
        # Extraer las 3 primeras letras de cada gesto. Primera mayúscula, resto minúscula
        gesture_str = "".join([g[:3].capitalize() for g in gestures_list])
        time_str = datetime.now().strftime("%H%M")
        
        for mac, rows in self.recorded_rows.items():
            alias = self.aliases.get(mac, "Unknown")
            
            # Extraer el nombre del dispositivo 
            dev_info = connected_devices.get(mac, {})
            dev_name = dev_info.get("name", "UnknownDev").replace(" ", "")
            
            # Formato: ESP32Name_Alias_Gestos_Hora.csv
            filename = f"{dev_name}_{alias}_{gesture_str}_{time_str}.csv"
            filepath = os.path.join("grabaciones", filename)
            
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                for row in rows:
                    writer.writerow(row)
                    
            saved_files.append(filepath)
        
        return saved_files