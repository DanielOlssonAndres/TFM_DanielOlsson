import os
import sys
import numpy as np

# Importamos TensorFlow/Keras para la carga del modelo
# Nota: Puede tardar unos segundos en importar al arrancar el script
from tensorflow.keras.models import model_from_json

# Importamos nuestro buffer circular
from modules.signal_buffer import SignalBuffer

# --- CONSTANTES ---
# Deben coincidir con las que usaste para entrenar el modelo
WINDOW_SIZE = 200   # 3 segundos a 50Hz
OVERLAP = 150       # 2 segundos de solapamiento
MODELS_DIR = "models/"

class AIManager:
    def __init__(self, model_name, classes):
        """
        Inicializa el gestor de IA.
        :param model_name: Nombre del archivo sin extensión (ej: 'mi_modelo')
        :param classes: Lista de strings con las etiquetas (ej: ['Andar', 'Correr'])
        """
        self.classes = classes
        self.buffers = {} # Diccionario: { 'MAC_ADDRESS': SignalBuffer }
        
        # Estado del sistema (Interruptor)
        self.is_active = False
        
        # Cargamos el modelo al iniciar
        self.model = self._load_model(model_name)

    def _load_model(self, model_name):
        """Carga la arquitectura .json y los pesos .h5"""
        json_path = os.path.join(MODELS_DIR, model_name + ".json")
        weights_path = os.path.join(MODELS_DIR, model_name + ".weights.h5")

        # Verificación de existencia
        if not os.path.exists(json_path) or not os.path.exists(weights_path):
            print(f"\n[IA ERROR] No se encuentran los archivos del modelo en '{MODELS_DIR}'")
            print(f" - Esperado: {model_name}.json")
            print(f" - Esperado: {model_name}.h5")
            print("Deteniendo ejecución...")
            sys.exit(1)

        print(f">> [IA] Cargando modelo '{model_name}'...")
        try:
            # 1. Cargar arquitectura
            with open(json_path, 'r') as json_file:
                loaded_model_json = json_file.read()
            model = model_from_json(loaded_model_json)
            
            # 2. Cargar pesos
            model.load_weights(weights_path)
            print(">> [IA] Modelo cargado y compilado exitosamente.")
            return model
        except Exception as e:
            print(f"[IA ERROR] Fallo crítico cargando el modelo: {e}")
            sys.exit(1)

    def start_prediction(self):
        """Activa el procesamiento de la IA y limpia buffers viejos."""
        print(">> [IA] SISTEMA ACTIVADO. Esperando datos para inferencia...")
        self.buffers.clear() # Limpiamos memoria para no usar datos viejos
        self.is_active = True

    def stop_prediction(self):
        """Desactiva el procesamiento de la IA."""
        self.is_active = False
        print(">> [IA] SISTEMA DETENIDO.")

    def process_incoming_data(self, mac, alias, samples):
        """
        Recibe datos crudos desde el BLEManager.
        Si la IA está activa, los añade al buffer y ejecuta predicción si corresponde.
        """
        # 1. Si el interruptor está apagado, ignoramos los datos
        if not self.is_active:
            return

        # 2. Si es un dispositivo nuevo, le creamos su propio Buffer
        if mac not in self.buffers:
            self.buffers[mac] = SignalBuffer(WINDOW_SIZE, OVERLAP)

        # 3. Añadimos los datos al buffer de ese dispositivo
        buffer_obj = self.buffers[mac]
        
        # add_packet devuelve True si se ha completado un STEP (ventana lista)
        is_ready = buffer_obj.add_packet(samples)

        # 4. Si el buffer está listo, predecimos
        if is_ready:
            self._predict(mac, alias, buffer_obj)

    def _predict(self, mac, alias, buffer_obj):
        """Prepara el tensor y ejecuta la inferencia en el modelo Keras"""
        
        # Obtenemos el tensor. Ahora tendrá forma (1, 200, 3) directamente.
        tensor = buffer_obj.get_tensor_for_lstm()
        
        if tensor is not None:
            # YA NO HACEMOS expand_dims AQUÍ porque get_tensor_for_lstm ya incluye la dimensión batch
            
            try:
                # Ejecutamos la predicción pasando 'tensor' directamente
                prediction_dist = self.model.predict(tensor, verbose=0)
                # Interpretamos el resultado (One-Hot Encoding -> Clase)
                winner_idx = np.argmax(prediction_dist, axis=1)[0]
                
                # Seguridad por si el índice sale de rango
                if winner_idx < len(self.classes):
                    winner_label = self.classes[winner_idx]
                    confidence = prediction_dist[0][winner_idx] * 100
                    
                    # IMPRIMIMOS EL RESULTADO
                    print(f"[{alias}] PREDICCIÓN: {winner_label} ({confidence:.1f}%)")
                else:
                    print(f"[{alias}] Error: Índice de clase {winner_idx} fuera de rango.")
                    
            except Exception as e:
                print(f"[{alias}] Error en inferencia: {e}")