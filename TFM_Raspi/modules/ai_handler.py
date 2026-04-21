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
        self.classes = classes # Lista de etiquetas de actividades 
        self.mac_order = mac_order # Orden estricto de los sensores para el tensor
        self.config = config # Configuracion del sistema 
        
        self.buffers = {} # Diccionario para almacenar un SignalBuffer por cada sensor
        self.is_active = False # Flag para la inferencia en tiempo real
        self.model = self._load_model(model_name) # Carga de la arquitectura y pesos
        
        # Almacenamiento de los ultimos estados procesados para cada dispositivo MAC
        self.latest_tensors = {mac: None for mac in self.mac_order}
        self.latest_timestamps = {mac: 0 for mac in self.mac_order}
        
        # Cola de hilos segura para pasar datos del hilo de red al hilo de computacion 
        self.prediction_queue = queue.Queue(maxsize=self.config.MAX_PREDICTION_QUEUE_SIZE)
        # Lock de exclusion mutua para evitar condiciones de carrera en los buffers de datos
        self.data_lock = threading.Lock()
        
        # Hilo dedicado exclusivamente a ejecutar el modelo para no bloquear la recepcion BLE
        self.worker_thread = threading.Thread(target=self._prediction_worker, daemon=True)
        self.worker_thread.start()
        
        self.temporal_buffer = {} # Buffer para sincronizar ventanas temporales de distintos sensores
        self.TIME_TOLERANCE_MS = self.config.WINDOW_TOLERANCE_MS

        # Motor de sincronizacion para alinear flujos de datos asincronos
        self.aligner = None

    # Carga el modelo desde archivos JSON y H5 
    def _load_model(self, model_name):
        json_path = os.path.join(self.config.MODELS_DIR, f"{model_name}.json")
        weights_path = os.path.join(self.config.MODELS_DIR, f"{model_name}.weights.h5")

        # Verificacion de existencia de archivos de modelo
        if not os.path.exists(json_path) or not os.path.exists(weights_path):
            print(f"\n[IA ERROR] No se encuentran los archivos en '{self.config.MODELS_DIR}'")
            sys.exit(1)

        print(f">> [IA] Cargando modelo '{model_name}'...")
        try:
            # Lectura y reconstruccion de la arquitectura Keras
            with open(json_path, 'r') as json_file:
                loaded_model_json = json_file.read()
            model = model_from_json(loaded_model_json)
            # Carga de los pesos entrenados
            model.load_weights(weights_path)
            print(">> [IA] Modelo cargado y compilado exitosamente.")
            return model
        except Exception as e:
            print(f"[IA ERROR] Fallo crítico cargando el modelo: {e}")
            sys.exit(1)

    # Libera recursos y detiene el hilo de ejecucion de forma limpia
    def cleanup(self):
        self.stop_prediction()
        try:
            # Enviamos None a la cola para señalizar al hilo que debe finalizar
            self.prediction_queue.put_nowait(None)
        except queue.Full:
            pass
        
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)

    # Activa el sistema y reinicia todos los buffers de sincronizacion
    def start_prediction(self):
        with self.data_lock:
            print(">> [IA] SISTEMA ACTIVADO. Esperando sincronización temporal...")
            self.buffers.clear() 
            self.latest_tensors = {mac: None for mac in self.mac_order}
            self.latest_timestamps = {mac: 0 for mac in self.mac_order}
            self.temporal_buffer.clear()
            
            # Instancia el motor de alineacion temporal basado en una cuadricula fija
            self.aligner = TimeGridAligner(self.mac_order, chunk_ms=self.config.PACKET_INTERVAL_MS)

            self.is_active = True

    # Detiene el flujo de procesamiento de datos
    def stop_prediction(self):
        with self.data_lock:
            self.is_active = False
            print(">> [IA] SISTEMA DETENIDO.")

    # Punto de entrada de datos desde el secuenciador BLE
    def process_incoming_data(self, mac, alias, samples, timestamp):
        with self.data_lock:
            # Ignora datos si el sistema esta apagado o el sensor no pertenece al modelo actual
            if not self.is_active or mac not in self.mac_order or self.aligner is None:
                return

            # Alimenta el motor de alineacion con el nuevo paquete recibido
            self.aligner.add_packet(mac, samples, timestamp)

            # Intenta extraer bloques alineados 
            aligned_chunk, chunk_time = self.aligner.get_aligned_chunk()
            
            if aligned_chunk:
                # Si hay bloque listo, procesa los datos de cada sensor individualmente
                for m in self.mac_order:
                    ideal_samples = aligned_chunk[m]
                    self._process_aligned_packet(m, ideal_samples, chunk_time)

    # Funcion que corre en segundo plano procesando la cola de inferencias
    def _prediction_worker(self):
        while True:
            # Bloquea el hilo hasta que llega un nuevo tensor 
            combined_tensor = self.prediction_queue.get()
            
            # Si el tensor es None, el hilo debe terminar
            if combined_tensor is None:
                self.prediction_queue.task_done() 
                break
            
            try:
                # Ejecucion de la inferencia mediante el modelo Keras
                prediction_dist = self.model.predict(combined_tensor, verbose=0)
                # Seleccion de la clase con mayor probabilidad
                winner_idx = np.argmax(prediction_dist, axis=1)[0]
                
                if winner_idx < len(self.classes):
                    winner_label = self.classes[winner_idx]
                    confidence = prediction_dist[0][winner_idx] * 100
                    # Salida por consola del resultado de reconocimiento de actividad
                    print(f"[{len(self.mac_order)} Sensores] PREDICCIÓN: {winner_label} ({confidence:.1f}%)")
                else:
                    print(f"[IA] Error: Índice de clase {winner_idx} fuera de rango.")
                    
            except Exception as e:
                print(f"[IA] Error en inferencia: {e}")
            finally:
                # Marca la tarea como completada para el control de la cola
                self.prediction_queue.task_done()

    # Procesa datos que ya han sido alineados temporalmente por el TimeGridAligner
    def _process_aligned_packet(self, mac, samples, timestamp):
        # Si no existe el buffer circular para este sensor, lo crea
        if mac not in self.buffers:
            self.buffers[mac] = SignalBuffer(self.config)

        # Añade las muestras al buffer circular 
        is_ready, window_timestamp = self.buffers[mac].add_packet(samples, timestamp)

        # Si el buffer ha completado una ventana completa 
        if is_ready:
            # Obtiene los datos normalizados y listos
            tensor = self.buffers[mac].get_tensor_for_lstm()
            if tensor is not None:
                # Alineacion de la marca de tiempo de la ventana a la cuadricula principal
                grid_size = self.config.PACKET_INTERVAL_MS
                matched_time = round(window_timestamp / grid_size) * grid_size
                
                # Almacenamiento temporal del tensor de este sensor esperando a los demas
                if matched_time not in self.temporal_buffer:
                    self.temporal_buffer[matched_time] = {}
                    
                self.temporal_buffer[matched_time][mac] = tensor

                # Limpieza de datos obsoletos
                obsolete_keys = [k for k in self.temporal_buffer.keys() if k < (matched_time - 1000)]
                for k in obsolete_keys:
                    del self.temporal_buffer[k]

                # Si tenemos los tensores de todos los sensores para el mismo instante de tiempo
                if len(self.temporal_buffer[matched_time]) == len(self.mac_order):
                    # Fusiona los ejes de entrada para crear el tensor multicanal final
                    combined_tensor = np.concatenate(
                        [self.temporal_buffer[matched_time][m] for m in self.mac_order], 
                        axis=2
                    )
                    
                    try:
                        # Envia el tensor combinado a la cola del trabajador de IA
                        self.prediction_queue.put_nowait(combined_tensor)
                    except queue.Full:
                        print("[IA] AVISO: Cola llena. Descartando inferencia.")
                    
                    # Elimina la entrada del buffer temporal una vez enviada a la cola
                    del self.temporal_buffer[matched_time]