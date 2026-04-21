class PacketSequencer:
    def __init__(self, config, data_callback=None):
        self.config = config
        self.data_callback = data_callback
        self.device_states = {}

    def process_packet(self, mac, alias, packet):
        samples = packet['samples']       
        seq = packet['sequence_id']
        timestamp = packet['timestamp_start']
        n_samples = len(samples)

        if mac not in self.device_states:
            self.device_states[mac] = {'last_seq': seq, 'last_samples': samples}
            if self.data_callback:
                self.data_callback(mac, alias, samples, timestamp)
            return

        last_seq = self.device_states[mac]['last_seq']
        expected_seq = last_seq + 1

        if seq > expected_seq:
            lost_count = seq - expected_seq
            print(f"\n[AVISO - {alias}] Pérdida de {lost_count} paquete(s) BLE. Aplicando interpolación lineal...")
            # Pasamos 'samples' (el paquete actual) para poder trazar la línea entre el pasado y el presente
            self._reconstruct_packets(mac, alias, lost_count, timestamp, samples, n_samples)
            
        elif seq < last_seq:
            print(f"\n[INFO - {alias}] Reinicio de secuencia BLE detectado (Anterior: {last_seq}, Nuevo: {seq}).")

        self.device_states[mac]['last_seq'] = seq
        self.device_states[mac]['last_samples'] = samples

        if self.data_callback:
            self.data_callback(mac, alias, samples, timestamp)

    def _reconstruct_packets(self, mac, alias, lost_count, timestamp, current_samples, n_samples):
        # Punto A: Última muestra válida antes de perder la conexión
        last_known_sample = self.device_states[mac]['last_samples'][-1]
        
        # Punto B: Primera muestra válida al recuperar la conexión
        first_new_sample = current_samples[0]
        
        total_missing_samples = lost_count * n_samples
        synthetic_packets = []
        
        # 1. Generación de las muestras perdidas trazando una recta entre A y B
        for i in range(total_missing_samples):
            ratio = (i + 1) / (total_missing_samples + 1)
            
            interp_x = int(last_known_sample['x'] + (first_new_sample['x'] - last_known_sample['x']) * ratio)
            interp_y = int(last_known_sample['y'] + (first_new_sample['y'] - last_known_sample['y']) * ratio)
            interp_z = int(last_known_sample['z'] + (first_new_sample['z'] - last_known_sample['z']) * ratio)
            
            synthetic_packets.append({'x': interp_x, 'y': interp_y, 'z': interp_z})

        # 2. Empaquetado en fragmentos del tamaño original y envío a la cola principal
        if self.data_callback:
            for p_idx in range(lost_count):
                start_idx = p_idx * n_samples
                end_idx = start_idx + n_samples
                packet_samples = synthetic_packets[start_idx:end_idx]
                
                # Cálculo de la marca de tiempo simulada para el paquete intermedio
                simulated_timestamp = timestamp - ((lost_count - p_idx) * self.config.PACKET_INTERVAL_MS)
                
                self.data_callback(mac, alias, packet_samples, simulated_timestamp)

    def remove_device(self, mac):
        if mac in self.device_states:
            del self.device_states[mac]
