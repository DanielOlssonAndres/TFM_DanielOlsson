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

        # Primer paquete recibido de este dispositivo
        if mac not in self.device_states:
            self.device_states[mac] = {'last_seq': seq, 'last_samples': samples}
            if self.data_callback:
                self.data_callback(mac, alias, samples, timestamp)
            return

        # Siguientes paquetes: comprobación de secuencia
        last_seq = self.device_states[mac]['last_seq']
        expected_seq = last_seq + 1

        if seq > expected_seq:
            lost_count = seq - expected_seq
            print(f"\n[AVISO - {alias}] Pérdida detectada: {lost_count} paquete(s) no recibidos. Reconstruyendo...")
            self._reconstruct_packets(mac, alias, lost_count, timestamp, n_samples)
            
        elif seq < last_seq:
            print(f"\n[INFO - {alias}] Reinicio de secuencia BLE detectado (Anterior: {last_seq}, Nuevo: {seq}).")

        # Actualizar estado
        self.device_states[mac]['last_seq'] = seq
        self.device_states[mac]['last_samples'] = samples

        # Enviar paquete real actual
        if self.data_callback:
            self.data_callback(mac, alias, samples, timestamp)

    def _reconstruct_packets(self, mac, alias, lost_count, timestamp, n_samples):
        """Genera paquetes sintéticos planos basados en la media del último paquete válido."""
        last_samples = self.device_states[mac]['last_samples']
        
        avg_x = int(sum(s['x'] for s in last_samples) / n_samples)
        avg_y = int(sum(s['y'] for s in last_samples) / n_samples)
        avg_z = int(sum(s['z'] for s in last_samples) / n_samples)

        synthetic_samples = [{'x': avg_x, 'y': avg_y, 'z': avg_z} for _ in range(n_samples)]

        if self.data_callback:
            for i in range(lost_count):
                simulated_timestamp = timestamp - ((lost_count - i) * self.config.PACKET_INTERVAL_MS)
                self.data_callback(mac, alias, synthetic_samples, simulated_timestamp)

    def remove_device(self, mac):
        """Limpia el estado de un dispositivo cuando se desconecta."""
        if mac in self.device_states:
            del self.device_states[mac]