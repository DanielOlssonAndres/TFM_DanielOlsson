# modules/ai_handler.py
import os
import sys
import numpy as np
import threading
from tensorflow.keras.models import model_from_json
from modules.signal_buffer import SignalBuffer
import queue

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
        
        # Limitar la cola para evitar OOM
        self.prediction_queue = queue.Queue(maxsize=self.config.MAX_PREDICTION_QUEUE_SIZE)
        
        # Añadir un Lock para concurrencia
        self.data_lock = threading.Lock()
        
        self.worker_thread = threading.Thread(target=self._prediction_worker, daemon=True)
        self.worker_thread.start()

    def _load_model(self, model_name):
        # Usar rutas inyectadas de la configuración
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
        
        # Esperar a que el hilo muera
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)

    def start_prediction(self):
        # Proteger con Lock
        with self.data_lock:
            print(">> [IA] SISTEMA ACTIVADO. Esperando sincronización de sensores...")
            self.buffers.clear() 
            self.latest_tensors = {mac: None for mac in self.mac_order}
            self.latest_timestamps = {mac: 0 for mac in self.mac_order}
            self.is_active = True

    def stop_prediction(self):
        # Proteger con Lock
        with self.data_lock:
            self.is_active = False
            print(">> [IA] SISTEMA DETENIDO.")

    def process_incoming_data(self, mac, alias, samples, timestamp):
        # Todo el procesamiento de datos entrantes es una sección crítica
        with self.data_lock:
            if not self.is_active or mac not in self.mac_order:
                return

            if mac not in self.buffers:
                # Usar configuración inyectada
                self.buffers[mac] = SignalBuffer(self.config)

            buffer_obj = self.buffers[mac]
            is_ready = buffer_obj.add_packet(samples)

            if is_ready:
                tensor = buffer_obj.get_tensor_for_lstm()
                if tensor is not None:
                    self.latest_tensors[mac] = tensor
                    self.latest_timestamps[mac] = timestamp 
                    
                    if all(t is not None for t in self.latest_tensors.values()):
                        tiempos = [self.latest_timestamps[m] for m in self.mac_order]
                        diferencia_maxima = max(tiempos) - min(tiempos)

                        # Usar tolerancia inyectada
                        if diferencia_maxima > self.config.SYNC_TOLERANCE_MS:
                            print(f"[IA] AVISO: Desincronización detectada ({diferencia_maxima}ms). Descartando ventana...")
                            min_mac = self.mac_order[np.argmin(tiempos)]
                            self.latest_tensors[min_mac] = None
                            return
                        
                        combined_tensor = np.concatenate([self.latest_tensors[m] for m in self.mac_order], axis=2)
                        
                        try:
                            # put_nowait evita bloqueos indefinidos si la cola está llena
                            self.prediction_queue.put_nowait(combined_tensor)
                        except queue.Full:
                            print("[IA] AVISO: Cola de predicciones llena. Descartando tensor (posible cuello de botella en inferencia).")
                        
                        self.latest_tensors = {m: None for m in self.mac_order}

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