import os
import sys
import numpy as np
import threading
from tensorflow.keras.models import model_from_json
from modules.signal_buffer import SignalBuffer
import queue
from config import SystemConfig
from modules.time_aligner import TimeGridAligner

class AIManager:
    def __init__(self, model_name, classes, mac_order, config):
        self.classes = classes
        self.mac_order = mac_order
        self.config = config
        
        self.buffers = {}  
        self.is_active = False 
        self.model = self._load_model(model_name)
        
        self.latest_tensors = {mac: None for mac in self.mac_order}
        self.latest_timestamps = {mac: 0 for mac in self.mac_order}
        
        self.prediction_queue = queue.Queue(maxsize=self.config.MAX_PREDICTION_QUEUE_SIZE)
        self.data_lock = threading.Lock()
        
        self.worker_thread = threading.Thread(target=self._prediction_worker, daemon=True)
        self.worker_thread.start()
        
        self.temporal_buffer = {} 
        self.TIME_TOLERANCE_MS = self.config.WINDOW_TOLERANCE_MS

        # Motor de sincronización
        self.aligner = None

    def _load_model(self, model_name):
        json_path = os.path.join(self.config.MODELS_DIR, f"{model_name}.json")
        weights_path = os.path.join(self.config.MODELS_DIR, f"{model_name}.weights.h5")

        if not os.path.exists(json_path) or not os.path.exists(weights_path):
            print(f"\n[IA ERROR] No se encuentran los archivos en '{self.config.MODELS_DIR}'")
            sys.exit(1)

        print(f">> [IA] Cargando modelo '{model_name}'...")
        try:
            with open(json_path, 'r') as json_file:
                loaded_model_json = json_file.read()
            model = model_from_json(loaded_model_json)
            model.load_weights(weights_path)
            print(">> [IA] Modelo cargado y compilado exitosamente.")
            return model
        except Exception as e:
            print(f"[IA ERROR] Fallo crítico cargando el modelo: {e}")
            sys.exit(1)

    def cleanup(self):
        self.stop_prediction()
        try:
            self.prediction_queue.put_nowait(None)
        except queue.Full:
            pass
        
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)

    def start_prediction(self):
        with self.data_lock:
            print(">> [IA] SISTEMA ACTIVADO. Esperando sincronización temporal...")
            self.buffers.clear() 
            self.latest_tensors = {mac: None for mac in self.mac_order}
            self.latest_timestamps = {mac: 0 for mac in self.mac_order}
            self.temporal_buffer.clear()
            
            # Instanciamos el motor matemático para la inferencia
            self.aligner = TimeGridAligner(self.mac_order, chunk_ms=self.config.PACKET_INTERVAL_MS)

            self.is_active = True

    def stop_prediction(self):
        with self.data_lock:
            self.is_active = False
            print(">> [IA] SISTEMA DETENIDO.")

    def process_incoming_data(self, mac, alias, samples, timestamp):
        with self.data_lock:
            if not self.is_active or mac not in self.mac_order or self.aligner is None:
                return

            # 1. Alimentar el motor asíncrono
            self.aligner.add_packet(mac, samples, timestamp)

            # 2. Extraer bloques de la cuadrícula perfecta (50Hz síncronos)
            aligned_chunk, chunk_time = self.aligner.get_aligned_chunk()
            
            if aligned_chunk:
                for m in self.mac_order:
                    ideal_samples = aligned_chunk[m]
                    self._process_aligned_packet(m, ideal_samples, chunk_time)

    def _prediction_worker(self):
        while True:
            combined_tensor = self.prediction_queue.get()
            
            if combined_tensor is None:
                self.prediction_queue.task_done() 
                break
            
            try:
                prediction_dist = self.model.predict(combined_tensor, verbose=0)
                winner_idx = np.argmax(prediction_dist, axis=1)[0]
                
                if winner_idx < len(self.classes):
                    winner_label = self.classes[winner_idx]
                    confidence = prediction_dist[0][winner_idx] * 100
                    print(f"[{len(self.mac_order)} Sensores] PREDICCIÓN: {winner_label} ({confidence:.1f}%)")
                else:
                    print(f"[IA] Error: Índice de clase {winner_idx} fuera de rango.")
                    
            except Exception as e:
                print(f"[IA] Error en inferencia: {e}")
            finally:
                self.prediction_queue.task_done()

    def _process_aligned_packet(self, mac, samples, timestamp):
        # Todo el mecanismo fallido de 'discard_count' ha sido eliminado.
        # Solo procesamos la señal pura inyectándola al buffer circular.
        
        if mac not in self.buffers:
            self.buffers[mac] = SignalBuffer(self.config)

        is_ready, window_timestamp = self.buffers[mac].add_packet(samples, timestamp)

        if is_ready:
            tensor = self.buffers[mac].get_tensor_for_lstm()
            if tensor is not None:
                grid_size = self.config.PACKET_INTERVAL_MS
                matched_time = round(window_timestamp / grid_size) * grid_size
                
                if matched_time not in self.temporal_buffer:
                    self.temporal_buffer[matched_time] = {}
                    
                self.temporal_buffer[matched_time][mac] = tensor

                obsolete_keys = [k for k in self.temporal_buffer.keys() if k < (matched_time - 1000)]
                for k in obsolete_keys:
                    del self.temporal_buffer[k]

                # Si tenemos la matriz de todos los sensores para esa ventana, inferimos
                if len(self.temporal_buffer[matched_time]) == len(self.mac_order):
                    combined_tensor = np.concatenate(
                        [self.temporal_buffer[matched_time][m] for m in self.mac_order], 
                        axis=2
                    )
                    
                    try:
                        self.prediction_queue.put_nowait(combined_tensor)
                    except queue.Full:
                        print("[IA] AVISO: Cola llena. Descartando inferencia.")
                    
                    del self.temporal_buffer[matched_time]