import os
import csv
import numpy as np
from datetime import datetime
from modules.signal_buffer import SignalBuffer
from modules.energy_visualizer import EnergyVisualizer
from modules.time_aligner import TimeGridAligner # Importante: requiere el nuevo módulo

class DataRecorder:
    def __init__(self, config):
        self.config = config
        self.is_recording = False
        self.current_gesture = ""
        self.target_frames = 0
        self.aliases = {}
        self.buffers = {}           # Instancias de SignalBuffer por MAC
        self.recorded_rows = {}     # Almacenamiento de tensores para CSV
        self.frames_recorded = {}   # Contador de ventanas por sensor
        
        self.active_macs_list = []
        self.aligner = None         # Motor de sincronización por interpolación

        # Integración de visualización
        self.use_visualizer = False
        self.visualizer = EnergyVisualizer() 

    def start_recording(self, gesture, target_frames, connected_macs):
        """Inicializa una sesión de captura con alineación temporal."""
        self.current_gesture = gesture
        self.target_frames = target_frames
        self.is_recording = True
        self.active_macs_list = connected_macs.copy()
        
        # Instanciamos el alineador. chunk_ms define el tamaño del bloque (500ms)
        self.aligner = TimeGridAligner(
            self.active_macs_list, 
            sample_rate=50, 
            chunk_ms=self.config.PACKET_INTERVAL_MS
        )

        # Reset de buffers y contadores
        for mac in connected_macs:
            self.buffers[mac] = SignalBuffer(self.config)
            self.frames_recorded[mac] = 0

    def stop_recording(self):
        self.is_recording = False

    def is_recording_complete(self, active_macs):
        """Verifica si todos los dispositivos han alcanzado el objetivo de frames."""
        if not active_macs: return True
        if not self.frames_recorded: return False
        return all(self.frames_recorded.get(mac, 0) >= self.target_frames for mac in active_macs)

    def discard_device(self, mac):
        if mac in self.recorded_rows: del self.recorded_rows[mac]
        if mac in self.frames_recorded: del self.frames_recorded[mac]

    def get_max_frames_recorded(self):
        if not self.frames_recorded: return 0
        return max(self.frames_recorded.values())

    def process_incoming_data(self, mac, alias, samples, timestamp=None):
        """Punto de entrada de datos desde BLEManager."""
        if mac not in self.aliases:
            self.aliases[mac] = alias

        if not self.is_recording or self.aligner is None:
            return

        # 1. Añadimos los paquetes asíncronos al motor de alineación
        self.aligner.add_packet(mac, samples, timestamp)

        # 2. Intentamos extraer un bloque de tiempo (chunk) alineado para todos los sensores
        # El motor devuelve datos interpolados a la frecuencia ideal (50Hz)
        aligned_chunk, chunk_time = self.aligner.get_aligned_chunk()
        
        if aligned_chunk:
            # Si el motor tiene datos suficientes de todos los sensores, procesamos el bloque
            for m in self.active_macs_list:
                ideal_samples = aligned_chunk[m]
                self._process_aligned_packet(m, ideal_samples, chunk_time)

    def _process_aligned_packet(self, mac, samples, timestamp):
        """Procesa datos que ya vienen garantizados en sincronía temporal."""
        if self.frames_recorded.get(mac, 0) < self.target_frames:
            # Asegurar existencia de buffer (failsafe)
            if mac not in self.buffers:
                self.buffers[mac] = SignalBuffer(self.config)
                
            # Añadir al buffer circular y verificar si hay ventana (window_size) lista
            is_ready, window_time = self.buffers[mac].add_packet(samples, timestamp)

            if is_ready:
                # Construcción del tensor plano para CSV
                tensor_2d = np.column_stack((
                    self.buffers[mac].acc_x, 
                    self.buffers[mac].acc_y, 
                    self.buffers[mac].acc_z
                ))
                
                # Timestamp | Datos (aplanados) | Etiqueta Gesto
                flat_row = [window_time] + list(tensor_2d.flatten()) + [self.current_gesture]
                
                if mac not in self.recorded_rows:
                    self.recorded_rows[mac] = []
                    
                self.recorded_rows[mac].append(flat_row)
                self.frames_recorded[mac] = self.frames_recorded.get(mac, 0) + 1

        # Envío de muestras interpoladas al visualizador en tiempo real
        if self.use_visualizer:
            self.visualizer.update(mac, samples)

    def start_visualizers(self, connected_devices):
        if self.use_visualizer:
            self.visualizer.start(connected_devices)

    def stop_visualizers(self):
        self.visualizer.stop()

    def clear_memory(self):
        self.recorded_rows.clear()
        self.frames_recorded.clear()

    def save_data(self, gestures_list, connected_devices):
        """Exporta los datos acumulados a archivos CSV."""
        os.makedirs("grabaciones", exist_ok=True)
        saved_files = []
        
        gesture_str = "".join([g[:3].capitalize() for g in gestures_list])
        time_str = datetime.now().strftime("%H%M")
        
        for mac, rows in self.recorded_rows.items():
            alias_limpio = self.aliases.get(mac, "Unknown").replace("_", "").replace(" ", "")
            dev_name_limpio = connected_devices.get(mac, {}).get("name", "UnknownDev").replace("_", "").replace(" ", "")
            
            filename = f"{dev_name_limpio}_{alias_limpio}_{gesture_str}_{time_str}.csv"
            filepath = os.path.join("grabaciones", filename)
            
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                for row in rows:
                    writer.writerow(row)
                    
            saved_files.append(filepath)
        
        return saved_files