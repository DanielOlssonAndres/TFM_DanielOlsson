import os
import csv
import time
import multiprocessing as mp
import matplotlib.pyplot as plt
from collections import deque
from datetime import datetime
from modules.signal_buffer import SignalBuffer

def plot_worker(queue, alias):
    plt.ion()
    fig, ax = plt.subplots()
    fig.canvas.manager.set_window_title(f"Energía - {alias}")
    
    # Añadimos una nueva cola para almacenar el histórico de la energía
    x_data = deque(maxlen=150)
    y_data = deque(maxlen=150)
    z_data = deque(maxlen=150)
    e_data = deque(maxlen=150) 
    
    # Definimos las líneas
    line_x, = ax.plot([], [], 'r-', label='Eje X')
    line_y, = ax.plot([], [], 'g-', label='Eje Y')
    line_z, = ax.plot([], [], 'b-', label='Eje Z')
    line_e, = ax.plot([], [], 'k-', linewidth=2, label='Energía (SVM)') 
    
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
                    
                    # Calculamos la Magnitud del Vector Aceleración 
                    energia = (x**2 + y**2 + z**2) ** 0.5
                    
                    x_data.append(x)
                    y_data.append(y)
                    z_data.append(z)
                    e_data.append(energia) # Guardamos el nuevo cálculo
                    
                updated = True
            
            if updated and len(x_data) > 0:
                line_x.set_data(range(len(x_data)), x_data)
                line_y.set_data(range(len(y_data)), y_data)
                line_z.set_data(range(len(z_data)), z_data)
                line_e.set_data(range(len(e_data)), e_data) # Actualizamos la línea en la gráfica
                
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
            # (Window=150, Overlap=100)
            self.buffers[mac] = SignalBuffer(150, 100)
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
                    # Aplastar los datos: [150 X] + [150 Y] + [150 Z] + [Gesto]
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

    def save_data(self, gestures_list):
        os.makedirs("grabaciones", exist_ok=True)
        saved_files = []
        
        gesture_initials = "_".join([g[0].upper() for g in gestures_list])
        time_str = datetime.now().strftime("%H%M")
        
        for mac, rows in self.recorded_rows.items():
            alias = self.aliases.get(mac, "Unknown")
            simp_alias = "".join([word[0].upper() for word in alias.split("_") if word])
            
            filename = f"{simp_alias}_{gesture_initials}_{time_str}.csv"
            filepath = os.path.join("grabaciones", filename)
            
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                for row in rows:
                    writer.writerow(row)
                    
            saved_files.append(filepath)
        
        return saved_files