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
        
        # Variables para alineación temporal
        self.first_timestamps = {}
        self.alignment_offsets = {}
        self.is_aligned = False
        self.active_macs_list = []

        # Integración de visualización en tiempo real
        self.use_visualizer = False
        self.visualizer = EnergyVisualizer() 

    def start_recording(self, gesture, target_frames, connected_macs):
        # Configura los metadatos de la sesión de captura
        self.current_gesture = gesture
        self.target_frames = target_frames
        self.is_recording = True

        self.first_timestamps.clear()
        self.alignment_offsets.clear()
        self.is_aligned = False
        self.active_macs_list = connected_macs.copy()
        
        self.pre_buffer = {mac: [] for mac in connected_macs}

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

        if not self.is_recording or mac not in self.buffers:
            return

        if not self.is_aligned:
            # Retener los paquetes en el pre-buffer mientras esperamos a los rezagados
            self.pre_buffer[mac].append((samples, timestamp))

            if mac not in self.first_timestamps:
                self.first_timestamps[mac] = timestamp
            
            if len(self.first_timestamps) == len(self.active_macs_list):
                tiempo_mas_lento = max(self.first_timestamps.values())
                
                for m, t in self.first_timestamps.items():
                    desfase_ms = tiempo_mas_lento - t
                    self.alignment_offsets[m] = int(desfase_ms / 20) 
                    
                self.is_aligned = True
                print(f"\n[*] Calibración de fase completada. Descarte: {self.alignment_offsets}")

                # Volcar los pre-buffers aplicando la corrección al principio de los datos
                for m in self.active_macs_list:
                    for pkt_samples, pkt_timestamp in self.pre_buffer[m]:
                        self._process_aligned_packet(m, pkt_samples, pkt_timestamp)
                
                # Liberar memoria del pre-buffer
                self.pre_buffer.clear()
            
            # Bloquear la ejecución normal hasta que la alineación termine
            return 

        # Ejecución normal cuando el sistema ya está alineado
        self._process_aligned_packet(mac, samples, timestamp)

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
    
    def _process_aligned_packet(self, mac, samples, timestamp):
        # Aplicar el descarte progresivamente hasta consumir el offset
        if self.alignment_offsets.get(mac, 0) > 0:
            discard_count = min(len(samples), self.alignment_offsets[mac])
            samples = samples[discard_count:] 
            self.alignment_offsets[mac] -= discard_count
            
            if not samples: 
                return
            
        if self.frames_recorded[mac] < self.target_frames:
            is_ready, window_time = self.buffers[mac].add_packet(samples, timestamp)

            if is_ready:
                tensor_2d = np.column_stack((
                    self.buffers[mac].acc_x, 
                    self.buffers[mac].acc_y, 
                    self.buffers[mac].acc_z
                ))
                
                flat_row = [window_time] + list(tensor_2d.flatten()) + [self.current_gesture]
                
                if mac not in self.recorded_rows:
                    self.recorded_rows[mac] = []
                    
                self.recorded_rows[mac].append(flat_row)
                self.frames_recorded[mac] += 1