class PacketSequencer:
    def __init__(self, config, data_callback=None):
        self.config = config
        self.data_callback = data_callback
        self.device_states = {}

    # Metodo principal que procesa cada paquete recibido de los dispositivos
    def process_packet(self, mac, alias, packet):
        # Extraccion de los datos clave del payload del paquete
        samples = packet['samples']       
        seq = packet['sequence_id']
        timestamp = packet['timestamp_start']
        n_samples = len(samples)

        # Si es la primera vez que vemos esta MAC, inicializamos su estado
        if mac not in self.device_states:
            self.device_states[mac] = {'last_seq': seq, 'last_samples': samples}
            # Enviamos el paquete al callback y salimos de la funcion
            if self.data_callback:
                self.data_callback(mac, alias, samples, timestamp)
            return

        # Recuperamos el numero de secuencia del ultimo paquete recibido para comparar
        last_seq = self.device_states[mac]['last_seq']
        # Calculamos cual deberia ser el siguiente numero de secuencia contiguo
        expected_seq = last_seq + 1

        # Si el numero de secuencia recibido es mayor al esperado, hay perdida de paquetes
        if seq > expected_seq:
            # Calculamos cuantos paquetes se han perdido en la transmision
            lost_count = seq - expected_seq
            print(f"\n[AVISO - {alias}] Pérdida de {lost_count} paquete(s) BLE. Aplicando interpolación lineal...")
            # Llamamos a la funcion de reconstruccion pasando las muestras actuales para poder trazar la recta
            self._reconstruct_packets(mac, alias, lost_count, timestamp, samples, n_samples)
            
        # Si el numero recibido es menor, asumimos un reinicio o desbordamiento de variable
        elif seq < last_seq:
            print(f"\n[INFO - {alias}] Reinicio de secuencia BLE detectado (Anterior: {last_seq}, Nuevo: {seq}).")

        # Actualizamos el estado del dispositivo con los datos validos de este paquete
        self.device_states[mac]['last_seq'] = seq
        self.device_states[mac]['last_samples'] = samples

        # Enviamos el paquete actual valido a la cola principal
        if self.data_callback:
            self.data_callback(mac, alias, samples, timestamp)

    def _reconstruct_packets(self, mac, alias, lost_count, timestamp, current_samples, n_samples):
        last_known_sample = self.device_states[mac]['last_samples'][-1]
        # A: Primera muestra valida del nuevo paquete recibido tras la perdida
        first_new_sample = current_samples[0]
        # B: Calculo del total de muestras individuales que faltan por rellenar
        total_missing_samples = lost_count * n_samples
        synthetic_packets = []
        
        # Generacion de las muestras perdidas trazando una recta entre el Punto A y el Punto B
        for i in range(total_missing_samples):
            # Calculo del ratio de interpolacion (distancia normalizada de 0.0 a 1.0 entre A y B)
            ratio = (i + 1) / (total_missing_samples + 1)
            
            # Interpolacion lineal para cada eje aplicando la formula geometrica basica
            interp_x = int(last_known_sample['x'] + (first_new_sample['x'] - last_known_sample['x']) * ratio)
            interp_y = int(last_known_sample['y'] + (first_new_sample['y'] - last_known_sample['y']) * ratio)
            interp_z = int(last_known_sample['z'] + (first_new_sample['z'] - last_known_sample['z']) * ratio)
            
            # Añadimos la muestra sintetica a la lista temporal
            synthetic_packets.append({'x': interp_x, 'y': interp_y, 'z': interp_z})

        # Empaquetado en fragmentos del tamaño original y envio al callback
        if self.data_callback:
            for p_idx in range(lost_count):
                # Calculo de los indices de inicio y fin para rebanar la lista de muestras sinteticas
                start_idx = p_idx * n_samples
                end_idx = start_idx + n_samples
                packet_samples = synthetic_packets[start_idx:end_idx]
                
                # Calculo de la marca de tiempo simulada para este paquete sintetico
                simulated_timestamp = timestamp - ((lost_count - p_idx) * self.config.PACKET_INTERVAL_MS)
                
                # Envio del paquete sintetico reconstruido 
                self.data_callback(mac, alias, packet_samples, simulated_timestamp)

    # Metodo para limpiar el estado en memoria de un dispositivo si se desconecta
    def remove_device(self, mac):
        if mac in self.device_states:
            del self.device_states[mac]