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
        self.buffers = {}           
        self.recorded_rows = {}     
        self.frames_recorded = {}   
        
        self.use_visualizer = False
        self.visualizer = EnergyVisualizer() # Inyectamos o instanciamos el nuevo módulo

    def start_recording(self, gesture, target_frames, connected_macs):
        self.current_gesture = gesture
        self.target_frames = target_frames
        self.is_recording = True
        
        for mac in connected_macs:
            # Usamos la configuración centralizada
            self.buffers[mac] = SignalBuffer(self.config)
            self.frames_recorded[mac] = 0

    def stop_recording(self):
        self.is_recording = False

    def is_recording_complete(self, active_macs):
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
        if mac not in self.aliases:
            self.aliases[mac] = alias
            
        if self.is_recording and mac in self.buffers:
            if self.frames_recorded[mac] < self.target_frames:
                is_ready = self.buffers[mac].add_packet(samples)
                
                if is_ready:
                    tensor_2d = np.column_stack((
                        self.buffers[mac].acc_x, 
                        self.buffers[mac].acc_y, 
                        self.buffers[mac].acc_z
                    ))
                    flat_row = list(tensor_2d.flatten()) + [self.current_gesture]
                    
                    if mac not in self.recorded_rows:
                        self.recorded_rows[mac] = []
                        
                    self.recorded_rows[mac].append(flat_row)
                    self.frames_recorded[mac] += 1

        # Delegamos la visualización
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