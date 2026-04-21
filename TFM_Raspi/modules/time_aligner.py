import numpy as np

class TimeGridAligner:
    def __init__(self, mac_list, sample_rate=50, chunk_ms=500):
        self.macs = mac_list
        self.dt = 1000.0 / sample_rate # 20 ms
        self.chunk_ms = chunk_ms
        self.streams = {mac: {'t': [], 'x': [], 'y': [], 'z': []} for mac in self.macs}
        self.master_t_next = None

    def add_packet(self, mac, samples, timestamp_start):
        # Desempaquetamos la ráfaga y asignamos un tiempo absoluto real a cada muestra individual
        for i, s in enumerate(samples):
            t = timestamp_start + (i * self.dt)
            self.streams[mac]['t'].append(t)
            self.streams[mac]['x'].append(s['x'])
            self.streams[mac]['y'].append(s['y'])
            self.streams[mac]['z'].append(s['z'])

        # Determinamos el "Punto Cero" (T0)
        if self.master_t_next is None:
            # Esperamos a que todos los sensores hayan enviado datos
            if all(len(self.streams[m]['t']) > 0 for m in self.macs):
                # El tiempo maestro comienza en el sensor que arrancó más tarde, asegurando
                # que todos tienen datos registrados a partir de este punto.
                self.master_t_next = max(self.streams[m]['t'][0] for m in self.macs)

    def get_aligned_chunk(self):
        """Devuelve un diccionario de muestras interpoladas si hay datos suficientes."""
        if self.master_t_next is None: return None, None

        t_end = self.master_t_next + self.chunk_ms

        # Barrera lógica: ¿Tenemos datos en TODOS los sensores que sobrepasen t_end?
        # Necesitamos datos del "futuro" para poder interpolar el "presente".
        for mac in self.macs:
            if not self.streams[mac]['t'] or self.streams[mac]['t'][-1] < t_end:
                return None, None

        # Vector de tiempos ideal y determinista (ej. 25 marcas de tiempo exactas cada 20ms)
        grid_t = np.arange(self.master_t_next, t_end, self.dt)
        aligned_data = {}

        for mac in self.macs:
            t_arr = np.array(self.streams[mac]['t'])
            x_arr = np.array(self.streams[mac]['x'])
            y_arr = np.array(self.streams[mac]['y'])
            z_arr = np.array(self.streams[mac]['z'])

            # Interpolación Lineal: Calculamos la aceleración exacta en el grid ideal
            x_interp = np.interp(grid_t, t_arr, x_arr)
            y_interp = np.interp(grid_t, t_arr, y_arr)
            z_interp = np.interp(grid_t, t_arr, z_arr)

            aligned_data[mac] = [{'x': x_interp[i], 'y': y_interp[i], 'z': z_interp[i]} for i in range(len(grid_t))]

            # Poda del buffer (Garbage Collection): Eliminamos muestras pasadas para no desbordar RAM
            idx = np.searchsorted(t_arr, t_end) - 1
            if idx > 0:
                self.streams[mac]['t'] = self.streams[mac]['t'][idx:]
                self.streams[mac]['x'] = self.streams[mac]['x'][idx:]
                self.streams[mac]['y'] = self.streams[mac]['y'][idx:]
                self.streams[mac]['z'] = self.streams[mac]['z'][idx:]

        chunk_start_time = self.master_t_next
        self.master_t_next = t_end
        
        return aligned_data, chunk_start_time