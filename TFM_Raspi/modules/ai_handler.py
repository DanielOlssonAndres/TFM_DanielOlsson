import os
import sys
import numpy as np
import threading
from tensorflow.keras.models import model_from_json
from modules.signal_buffer import SignalBuffer
import queue

# Estas constantes deben coincidir con las usadas para entrenar el modelo
WINDOW_SIZE = 200   
OVERLAP = 150      

MODELS_DIR = "models/"

class AIManager:
    def __init__(self, model_name, classes, mac_order):
        self.classes = classes
        self.mac_order = mac_order
        self.buffers = {}  
        self.is_active = False 
        self.model = self._load_model(model_name)
        
        self.latest_tensors = {mac: None for mac in self.mac_order}
        self.latest_timestamps = {mac: 0 for mac in self.mac_order}
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
        print(">> [IA] SISTEMA ACTIVADO. Esperando sincronización de sensores...")
        self.buffers.clear() 
        self.latest_tensors = {mac: None for mac in self.mac_order}
        self.latest_timestamps = {mac: 0 for mac in self.mac_order}
        self.is_active = True

    def stop_prediction(self):
        self.is_active = False
        print(">> [IA] SISTEMA DETENIDO.")

    def process_incoming_data(self, mac, alias, samples, timestamp):
        if not self.is_active or mac not in self.mac_order:
            return

        if mac not in self.buffers:
            self.buffers[mac] = SignalBuffer(WINDOW_SIZE, OVERLAP)

        buffer_obj = self.buffers[mac]
        is_ready = buffer_obj.add_packet(samples)

        if is_ready:
            tensor = buffer_obj.get_tensor_for_lstm()
            if tensor is not None:
                # Guardamos el tensor más reciente para este dispositivo específico
                self.latest_tensors[mac] = tensor
                self.latest_timestamps[mac] = timestamp # Guardar el tiempo real de la ventana
                
                # Comprobamos si ya tenemos una ventana lista de todos los dispositivos requeridos
                if all(t is not None for t in self.latest_tensors.values()):
                    
                    # Extraer los tiempos actuales de todos los tensores listos
                    tiempos = [self.latest_timestamps[m] for m in self.mac_order]
                    diferencia_maxima = max(tiempos) - min(tiempos)

                    # Si la diferencia entre los tensores es mayor a 600 ms, están desincronizados
                    if diferencia_maxima > 600:
                        print(f"[IA] AVISO: Desincronización detectada ({diferencia_maxima}ms). Descartando ventana...")
                        # Identificar el dispositivo más atrasado y vaciar solo su tensor para esperar al siguiente
                        min_mac = self.mac_order[np.argmin(tiempos)]
                        self.latest_tensors[min_mac] = None
                        return
                    
                    # Si están sincronizados, concatenar y predecir
                    combined_tensor = np.concatenate([self.latest_tensors[m] for m in self.mac_order], axis=2)
                    
                    # Mandamos al hilo de predicción
                    self.prediction_queue.put(combined_tensor)
                    
                    # Vaciamos los tensores para requerir nuevos datos para la próxima ventana
                    self.latest_tensors = {m: None for m in self.mac_order}

    def _prediction_worker(self):
        while True:
            combined_tensor = self.prediction_queue.get()
            if combined_tensor is None:
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