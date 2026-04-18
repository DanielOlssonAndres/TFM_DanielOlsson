import os
import csv
import numpy as np
from datetime import datetime
from modules.signal_buffer import SignalBuffer
from modules.energy_visualizer import EnergyVisualizer

class DataRecorder:
    def __init__(self, config):
        self.config = config
        self.is_recording = False
        self.current_gesture = ""
        self.target_frames = 0
        self.aliases = {}
        self.buffers = {}           # Instancias de SignalBuffer por MAC
        self.recorded_rows = {}     # Almacenamiento temporal de los tensores aplanados
        self.frames_recorded = {}   # Contadores independientes de ventanas completadas por MAC
        
        # Integración de visualización en tiempo real
        self.use_visualizer = False
        self.visualizer = EnergyVisualizer() 

    def start_recording(self, gesture, target_frames, connected_macs):
        # Configura los metadatos de la sesión de captura
        self.current_gesture = gesture
        self.target_frames = target_frames
        self.is_recording = True
        
        # Inicialización de las estructuras de datos para cada sensor conectado
        for mac in connected_macs:
            # Cada sensor requiere su propio buffer circular para aislar los flujos de datos
            self.buffers[mac] = SignalBuffer(self.config)
            self.frames_recorded[mac] = 0

    def stop_recording(self):
        # Detiene la ingesta de nuevos datos en los buffers de grabación
        self.is_recording = False

    def is_recording_complete(self, active_macs):
        # Lógica de comprobación de finalización de la captura
        if not active_macs: return True
        if not self.frames_recorded: return False
        # Retorna True solo si todos los sensores activos han alcanzado la cuota de frames
        # Garantiza conjuntos de datos balanceados entre los diferentes dispositivos 
        return all(self.frames_recorded.get(mac, 0) >= self.target_frames for mac in active_macs)

    def discard_device(self, mac):
        # Limpieza dinámica en caso de desconexión de un sensor durante la grabación
        if mac in self.recorded_rows: del self.recorded_rows[mac]
        if mac in self.frames_recorded: del self.frames_recorded[mac]

    def get_max_frames_recorded(self):
        if not self.frames_recorded: return 0
        return max(self.frames_recorded.values())

    def process_incoming_data(self, mac, alias, samples, timestamp=None):
        if mac not in self.aliases:
            self.aliases[mac] = alias
            
        if self.is_recording and mac in self.buffers:
            # Si un sensor va más rápido, deja de grabar al llegar a su objetivo, esperando a los demás
            if self.frames_recorded[mac] < self.target_frames:
                # Inyección de muestras crudas en el buffer específico del sensor
                is_ready = self.buffers[mac].add_packet(samples)
                
                # Indica que el buffer tiene suficientes datos para extraer una ventana completa
                if is_ready:
                    # Ensamblaje del tensor 2D 
                    tensor_2d = np.column_stack((
                        self.buffers[mac].acc_x, 
                        self.buffers[mac].acc_y, 
                        self.buffers[mac].acc_z
                    ))
                    
                    # Aplanado del tensor para exportación a CSV
                    # Se concatena la etiqueta del gesto al final de la fila.
                    # Formato resultante: [x0, y0, z0, x1, y1, z1 ... xN, yN, zN, "gesto"]
                    flat_row = list(tensor_2d.flatten()) + [self.current_gesture]
                    
                    if mac not in self.recorded_rows:
                        self.recorded_rows[mac] = []
                        
                    # Almacenamiento en memoria RAM de la fila completada
                    self.recorded_rows[mac].append(flat_row)
                    self.frames_recorded[mac] += 1

        if self.use_visualizer:
            self.visualizer.update(mac, samples)

    def start_visualizers(self, connected_devices):
        if self.use_visualizer:
            self.visualizer.start(connected_devices)

    def stop_visualizers(self):
        self.visualizer.stop()

    def clear_memory(self):
        # Liberación explícita de la memoria RAM entre sesiones
        self.recorded_rows.clear()
        self.frames_recorded.clear()

    def save_data(self, gestures_list, connected_devices):
        # Creación del directorio de destino si no existe
        os.makedirs("grabaciones", exist_ok=True)
        saved_files = []
        
        # Generación de la nomenclatura del archivo basada en los gestos y la hora
        gesture_str = "".join([g[:3].capitalize() for g in gestures_list])
        time_str = datetime.now().strftime("%H%M")
        
        # Exportación de los datos a disco. Se crea un archivo CSV independiente por cada sensor MAC
        for mac, rows in self.recorded_rows.items():
            alias_limpio = self.aliases.get(mac, "Unknown").replace("_", "").replace(" ", "")
            dev_name_limpio = connected_devices.get(mac, {}).get("name", "UnknownDev").replace("_", "").replace(" ", "")
            
            # Convención de nombres: NombreBLE_AliasSensor_Gesto_Hora.csv
            filename = f"{dev_name_limpio}_{alias_limpio}_{gesture_str}_{time_str}.csv"
            filepath = os.path.join("grabaciones", filename)
            
            # Operación bloqueante de escritura en disco
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                for row in rows:
                    writer.writerow(row)
                    
            saved_files.append(filepath)
        
        return saved_files