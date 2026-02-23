import os
import sys
import numpy as np
import threading
from tensorflow.keras.models import model_from_json
from modules.signal_buffer import SignalBuffer
import queue

# Estas constantes deben coincidir con las usadas para entrenar el modelo
WINDOW_SIZE = 200   # 3 segundos a 50Hz
OVERLAP = 150       # 2 segundos de solapamiento

MODELS_DIR = "models/"

class AIManager:
    def __init__(self, model_name, classes):
        self.classes = classes
        self.buffers = {}  
        self.is_active = False 
        self.model = self._load_model(model_name)
        
        # Sistema de encolado seguro para IA
        self.prediction_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._prediction_worker, daemon=True)
        self.worker_thread.start()

    def _load_model(self, model_name):
        json_path = os.path.join(MODELS_DIR, model_name + ".json")
        weights_path = os.path.join(MODELS_DIR, model_name + ".weights.h5")

        # Verificación de existencia
        if not os.path.exists(json_path) or not os.path.exists(weights_path):
            print(f"\n[IA ERROR] No se encuentran los archivos del modelo en '{MODELS_DIR}'")
            print(f" - Esperado: {model_name}.json")
            print(f" - Esperado: {model_name}.weights.h5")
            print("Deteniendo ejecución...")
            sys.exit(1)

        print(f">> [IA] Cargando modelo '{model_name}'...")
        try:
            # Cargar arquitectura
            with open(json_path, 'r') as json_file:
                loaded_model_json = json_file.read()
            model = model_from_json(loaded_model_json)
            
            # Cargar pesos
            model.load_weights(weights_path)
            print(">> [IA] Modelo cargado y compilado exitosamente.")
            return model
        except Exception as e:
            print(f"[IA ERROR] Fallo crítico cargando el modelo: {e}")
            sys.exit(1)

    def start_prediction(self):
        print(">> [IA] SISTEMA ACTIVADO. Esperando datos para inferencia...")
        self.buffers.clear() # Limpiamos memoria para no usar datos viejos
        self.is_active = True

    def stop_prediction(self):
        self.is_active = False
        print(">> [IA] SISTEMA DETENIDO.")

    def process_incoming_data(self, mac, alias, samples):
        if not self.is_active:
            return

        if mac not in self.buffers:
            self.buffers[mac] = SignalBuffer(WINDOW_SIZE, OVERLAP)

        buffer_obj = self.buffers[mac]
        is_ready = buffer_obj.add_packet(samples)

        if is_ready:
            tensor = buffer_obj.get_tensor_for_lstm()
            if tensor is not None:
                self.prediction_queue.put((mac, alias, tensor))

    def _prediction_worker(self):
        # Este hilo vive siempre en segundo plano procesando la cola uno por uno
        while True:
            item = self.prediction_queue.get()
            if item is None:
                break
            
            mac, alias, tensor = item
            try:
                prediction_dist = self.model.predict(tensor, verbose=0)
                winner_idx = np.argmax(prediction_dist, axis=1)[0]
                
                if winner_idx < len(self.classes):
                    winner_label = self.classes[winner_idx]
                    confidence = prediction_dist[0][winner_idx] * 100
                    print(f"[{alias}] PREDICCIÓN: {winner_label} ({confidence:.1f}%)")
                else:
                    print(f"[{alias}] Error: Índice de clase {winner_idx} fuera de rango.")
                    
            except Exception as e:
                print(f"[{alias}] Error en inferencia: {e}")
            finally:
                self.prediction_queue.task_done()