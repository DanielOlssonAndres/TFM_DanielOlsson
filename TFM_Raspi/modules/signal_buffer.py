import numpy as np

class SignalBuffer:
    def __init__(self, window_size=150, overlap=100):
        self.window_size = window_size
        self.overlap = overlap
        self.step_size = window_size - overlap
        
        # Inicializamos los arrays de X, Y, Z llenos de ceros (como en el legacy)
        # Usamos float64 porque es lo que usaba el legacy (np.float64)
        self.acc_x = np.zeros(window_size, dtype=np.float64)
        self.acc_y = np.zeros(window_size, dtype=np.float64)
        self.acc_z = np.zeros(window_size, dtype=np.float64)
        
        # Contador para saber cuántas muestras nuevas hemos acumulado desde la última predicción
        self.new_samples_count = 0
        self.is_buffer_full = False

    def add_packet(self, samples):
        """
        Recibe una lista de diccionarios [{'x':..., 'y':..., 'z':...}, ...]
        Normalmente son 25 muestras.
        """
        n_new = len(samples)
        if n_new == 0:
            return False

        # Extraer los datos en listas separadas
        # Nota: Asumimos que los datos ya vienen escalados o crudos según necesite tu IA.
        # Si el legacy multiplicaba por GRAVITY_ACCEL (9.81), hazlo aquí.
        new_x = np.array([s['x'] for s in samples], dtype=np.float64)
        new_y = np.array([s['y'] for s in samples], dtype=np.float64)
        new_z = np.array([s['z'] for s in samples], dtype=np.float64)

        # --- LÓGICA DE BUFFER CIRCULAR (ROLLING) ---
        # 1. Desplazamos los datos antiguos hacia la izquierda
        self.acc_x = np.roll(self.acc_x, -n_new)
        self.acc_y = np.roll(self.acc_y, -n_new)
        self.acc_z = np.roll(self.acc_z, -n_new)

        # 2. Insertamos los nuevos datos al final
        self.acc_x[-n_new:] = new_x
        self.acc_y[-n_new:] = new_y
        self.acc_z[-n_new:] = new_z

        # 3. Control de flujo para la IA
        self.new_samples_count += n_new
        
        # Solo marcamos el buffer como "lleno" la primera vez que completamos el tamaño
        if not self.is_buffer_full and self.new_samples_count >= self.window_size:
            self.is_buffer_full = True
            self.new_samples_count = 0 # Reset para empezar a contar el step
            return True # Listo para predecir (primera vez)

        # Si ya estaba lleno, verificamos si hemos superado el STEP (Window - Overlap)
        # Ejemplo: Window 150, Overlap 100 -> Step 50. Predecimos cada 50 muestras nuevas.
        if self.is_buffer_full and self.new_samples_count >= self.step_size:
            self.new_samples_count = 0 # Reset del contador de paso
            return True # Listo para predecir

        return False

    def get_tensor_for_lstm(self):
        """
        Replica EXACTAMENTE la construcción del tensor del archivo 'demo-lstm-recognizer.py'
        """
        # Legacy Code reference:
        # tensor = np.array([recorder.AccXarray, recorder.AccYarray, recorder.AccZarray]).flatten()
        # tensor = np.reshape(tensor, newshape=(-1, recorder.buffer_size, 3), order='F')
        
        try:
            # 1. Crear array combinado
            tensor = np.array([self.acc_x, self.acc_y, self.acc_z])
            
            # 2. Aplanar
            tensor = tensor.flatten()
            
            # 3. Reshape con orden 'F' (Fortran-like index order), vital para tu modelo entrenado
            tensor = np.reshape(tensor, (-1, self.window_size, 3), order='F')
            
            return tensor
        except Exception as e:
            print(f"Error construyendo tensor: {e}")
            return None