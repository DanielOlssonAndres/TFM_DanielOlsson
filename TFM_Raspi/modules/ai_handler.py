import os
import sys
import numpy as np
import threading
from tensorflow.keras.models import model_from_json
from modules.signal_buffer import SignalBuffer
import queue
from config import SystemConfig

class AIManager:
    def __init__(self, model_name, classes, mac_order, config):
        self.classes = classes
        self.mac_order = mac_order
        self.config = config
        # Diccionario para instanciar los buffers de señal por cada dirección MAC
        self.buffers = {}  
        # Flag de estado para controlar la entrada de datos hacia la inferencia
        self.is_active = False 
        # Carga del modelo en memoria durante la instanciación de la clase
        self.model = self._load_model(model_name)
        # Almacenamiento del último tensor válido generado por cada sensor
        self.latest_tensors = {mac: None for mac in self.mac_order}
        # Registro del timestamp de cada tensor 
        self.latest_timestamps = {mac: 0 for mac in self.mac_order}
        # Buffer intermedio entre la recepción de BLE y la inferencia de la IA 
        self.prediction_queue = queue.Queue(maxsize=self.config.MAX_PREDICTION_QUEUE_SIZE)
        # Mutex para proteger las estructuras de datos 
        self.data_lock = threading.Lock()
        # Hilo de inferencia 
        # Daemon=True hace que este hilo muera automáticamente si el hilo principal termina
        self.worker_thread = threading.Thread(target=self._prediction_worker, daemon=True)
        self.worker_thread.start()
        self.temporal_buffer = {} 
        self.TIME_TOLERANCE_MS = self.config.WINDOW_TOLERANCE_MS

    def _load_model(self, model_name):
        json_path = os.path.join(self.config.MODELS_DIR, f"{model_name}.json")
        weights_path = os.path.join(self.config.MODELS_DIR, f"{model_name}.weights.h5")

        # Comprobación de integridad del sistema de archivos
        if not os.path.exists(json_path) or not os.path.exists(weights_path):
            print(f"\n[IA ERROR] No se encuentran los archivos en '{self.config.MODELS_DIR}'")
            sys.exit(1)

        print(f">> [IA] Cargando modelo '{model_name}'...")
        try:
            # Reconstrucción de la arquitectura de la red neuronal desde el JSON
            with open(json_path, 'r') as json_file:
                loaded_model_json = json_file.read()
            model = model_from_json(loaded_model_json)
            # Población de los pesos de las capas
            model.load_weights(weights_path)
            print(">> [IA] Modelo cargado y compilado exitosamente.")
            return model
        except Exception as e:
            # Captura de errores de formato
            print(f"[IA ERROR] Fallo crítico cargando el modelo: {e}")
            sys.exit(1)

    def cleanup(self):
        # Secuencia de apagado controlado 
        self.stop_prediction()
        try:
            self.prediction_queue.put_nowait(None)
        except queue.Full:
            pass
        
        # Esperar a que el hilo muera
        # Se bloquea el hilo principal para asegurar que el worker termina sus operaciones pendientes
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)

    def start_prediction(self):
        with self.data_lock:
            print(">> [IA] SISTEMA ACTIVADO. Esperando sincronización de sensores...")
            self.buffers.clear() 
            self.latest_tensors = {mac: None for mac in self.mac_order}
            self.latest_timestamps = {mac: 0 for mac in self.mac_order}
            self.is_active = True

    def stop_prediction(self):
        with self.data_lock:
            self.is_active = False
            print(">> [IA] SISTEMA DETENIDO.")

    def process_incoming_data(self, mac, alias, samples, timestamp):
        with self.data_lock:
            if not self.is_active or mac not in self.mac_order:
                return

            if mac not in self.buffers:
                self.buffers[mac] = SignalBuffer(self.config)

            # Extraemos si la ventana está lista y su timestamp global real
            is_ready, window_timestamp = self.buffers[mac].add_packet(samples, timestamp)

            if is_ready:
                tensor = self.buffers[mac].get_tensor_for_lstm()
                if tensor is not None:
                    # Búsqueda de ancla dinámica (Dynamic Clustering)
                    grid_size = self.config.PACKET_INTERVAL_MS
                    matched_time = round(window_timestamp / grid_size) * grid_size
                    
                    if matched_time not in self.temporal_buffer:
                        self.temporal_buffer[matched_time] = {}
                        
                    self.temporal_buffer[matched_time][mac] = tensor

                    # Limpieza proactiva de memoria (Evita Memory Leaks por paquetes perdidos)
                    # Eliminamos cualquier grupo que se haya quedado incompleto y sea más antiguo de 1 segundo
                    obsolete_keys = [k for k in self.temporal_buffer.keys() if k < (matched_time - 1000)]
                    for k in obsolete_keys:
                        del self.temporal_buffer[k]

                    # Comprobación de integridad del tensor
                    if len(self.temporal_buffer[matched_time]) == len(self.mac_order):
                        combined_tensor = np.concatenate(
                            [self.temporal_buffer[matched_time][m] for m in self.mac_order], 
                            axis=2
                        )
                        
                        try:
                            self.prediction_queue.put_nowait(combined_tensor)
                        except queue.Full:
                            print("[IA] AVISO: Cola llena. Descartando inferencia.")
                        
                        # Limpieza tras consumo
                        del self.temporal_buffer[matched_time]

    def _prediction_worker(self):
        while True:
            # El hilo duerme aquí sin consumir CPU hasta que haya un elemento en la cola.
            combined_tensor = self.prediction_queue.get()
            
            # Condición de salida 
            if combined_tensor is None:
                self.prediction_queue.task_done() 
                break
            
            try:
                # Inferencia directa sobre el modelo cargado en memoria
                prediction_dist = self.model.predict(combined_tensor, verbose=0)
                # Extracción del índice de la clase con mayor probabilidad probabilística 
                winner_idx = np.argmax(prediction_dist, axis=1)[0]
                
                # Mapeo del índice 
                if winner_idx < len(self.classes):
                    winner_label = self.classes[winner_idx]
                    confidence = prediction_dist[0][winner_idx] * 100
                    print(f"[{len(self.mac_order)} Sensores] PREDICCIÓN: {winner_label} ({confidence:.1f}%)")
                else:
                    print(f"[IA] Error: Índice de clase {winner_idx} fuera de rango.")
                    
            except Exception as e:
                # Captura de errores 
                print(f"[IA] Error en inferencia: {e}")
            finally:
                self.prediction_queue.task_done()