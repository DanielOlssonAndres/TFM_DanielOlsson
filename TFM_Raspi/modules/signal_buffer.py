import numpy as np

class SignalBuffer:
    def __init__(self, config):
        self.window_size = config.WINDOW_SIZE
        self.overlap = config.OVERLAP
        self.step_size = config.WINDOW_SIZE - config.OVERLAP
        self.scale_factor = config.SCALE_FACTOR
        
        self.acc_x = np.zeros(self.window_size, dtype=np.float64)
        self.acc_y = np.zeros(self.window_size, dtype=np.float64)
        self.acc_z = np.zeros(self.window_size, dtype=np.float64)
        
        self.new_samples_count = 0
        self.is_buffer_full = False

    def add_packet(self, samples):
        n_new = len(samples)
        if n_new == 0:
            return False

        # PREPROCESADO ----------------------------------
        # Extraer los datos y convertirlos a gravedades (g) reales
        new_x = np.array([s['x'] for s in samples], dtype=np.float64) / self.scale_factor
        new_y = np.array([s['y'] for s in samples], dtype=np.float64) / self.scale_factor
        new_z = np.array([s['z'] for s in samples], dtype=np.float64) / self.scale_factor
        # ----------------------------------------------

        # Lógica del buffer circular 
        # Desplazamos los datos antiguos hacia la izquierda
        self.acc_x = np.roll(self.acc_x, -n_new)
        self.acc_y = np.roll(self.acc_y, -n_new)
        self.acc_z = np.roll(self.acc_z, -n_new)

        # Insertamos los nuevos datos al final
        self.acc_x[-n_new:] = new_x
        self.acc_y[-n_new:] = new_y
        self.acc_z[-n_new:] = new_z

        # Control de flujo
        self.new_samples_count += n_new
        
        # Solo se marca el buffer como lleno la primera vez que completamos el tamaño
        if not self.is_buffer_full and self.new_samples_count >= self.window_size:
            self.is_buffer_full = True
            self.new_samples_count = 0 # Reset para empezar a contar el step
            return True # Listo para predecir (primera vez)

        # Si ya estaba lleno, verificamos si hemos superado el STEP (Window - Overlap)
        if self.is_buffer_full and self.new_samples_count >= self.step_size:
            self.new_samples_count -= self.step_size
            return True # Listo para predecir

        return False

    def get_tensor_for_lstm(self):
        try:
            # Apilar las matrices como columnas 
            # Resultado: Array de dimensiones (window_size, 3)
            tensor = np.column_stack((self.acc_x, self.acc_y, self.acc_z))
            
            # Añadir la dimensión del batch en el eje 0
            # Resultado final: (1, window_size, 3)
            tensor = np.expand_dims(tensor, axis=0)
            
            return tensor
        
        except Exception as e:
            print(f"Error construyendo tensor: {e}")
            return None