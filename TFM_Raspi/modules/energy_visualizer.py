import sys
import time
import numpy as np
import multiprocessing as mp
import matplotlib.pyplot as plt
from collections import deque

class FiltroExponencial3Ejes:
    # Filtro IIR (Infinite Impulse Response) paso alto basado en Media Móvil Exponencial (EMA).
    # Se utiliza para aislar la aceleración lineal dinámica, eliminando el componente 
    # continuo (DC) que representa el vector de la gravedad terrestre (1g).
    def __init__(self, alpha=0.9):
        self.alpha = alpha
        self.g = np.zeros(3)
        self.primera_lectura = True

    def filtrar(self, ax, ay, az):
        a_t = np.array([ax, ay, az]).
        if self.primera_lectura:
            self.g = a_t
            self.primera_lectura = False
            
        # Estimación paso bajo (Low-pass) para aislar la gravedad.
        # G(t) = alpha * G(t-1) + (1 - alpha) * Acc(t)
        self.g = (self.alpha * self.g) + (1.0 - self.alpha) * a_t
        
        # Aceleración dinámica (paso alto) = Aceleración total - Gravedad
        return a_t - self.g

def plot_worker(queue, alias):
    try:
        # Modo interactivo de matplotlib, necesario para actualizar gráficos en tiempo real sin bloquear la ejecución
        plt.ion()
        fig, ax = plt.subplots()
        fig.canvas.manager.set_window_title(f"Energía - {alias}")
    except Exception as e:
        print(f"\n>> [ERROR GRÁFICO - {alias}] Fallo al inicializar la ventana de Matplotlib.")
        print(f">> Excepción del sistema: {e}")
        sys.exit(1)
    
    filtro = FiltroExponencial3Ejes(alpha=0.9)
    x_data, y_data, z_data, e_data = [deque(maxlen=150) for _ in range(4)]
    
    line_x, = ax.plot([], [], 'r-', label='Eje X')
    line_y, = ax.plot([], [], 'g-', label='Eje Y')
    line_z, = ax.plot([], [], 'b-', label='Eje Z')
    line_e, = ax.plot([], [], 'k-', linewidth=2, label='Energía (Sin Gravedad)') 
    
    ax.legend(loc="upper left")
    
    # Bucle infinito del proceso renderizador
    while True:
        try:
            updated = False
            # Se procesan todos los paquetes pendientes antes de repintar la pantalla
            while not queue.empty():
                msg = queue.get_nowait()
                if msg == "STOP":
                    plt.close(fig)
                    return
                
                # Desempaquetado de las muestras entrantes
                for s in msg:
                    x, y, z = s['x'], s['y'], s['z']
                    # Filtrado de gravedad
                    a_dyn = filtro.filtrar(x, y, z)
                    # Cálculo de la Energía de la señal 
                    energia = (a_dyn[0]**2 + a_dyn[1]**2 + a_dyn[2]**2) ** 0.5
                    
                    # Inserción en los buffers circulares
                    x_data.append(x); y_data.append(y); z_data.append(z); e_data.append(energia)
                updated = True
            
            # Solo se gasta CPU en repintar si ha entrado nueva información
            if updated and len(x_data) > 0:
                # Actualización de los datos
                line_x.set_data(range(len(x_data)), x_data)
                line_y.set_data(range(len(y_data)), y_data)
                line_z.set_data(range(len(z_data)), z_data)
                line_e.set_data(range(len(e_data)), e_data)
                
                # Recálculo de los límites de los ejes (Autoscaling dinámico)
                ax.relim()
                ax.autoscale_view()
                
                # Forzado del repintado del buffer de la ventana GUI 
            fig.canvas.flush_events()
            # Control de la tasa de refresco para no saturar la CPU de la Raspberry Pi
            time.sleep(0.05)
        except Exception:
            # Silencia cualquier fallo intermitente de la GUI durante el repintado
            pass

class EnergyVisualizer:
    def __init__(self):
        # Diccionarios para mantener referencias a las colas y procesos hijos por MAC
        self.queues = {}
        self.processes = {}

    def start(self, connected_devices):
        # Prevención de procesos huérfanos: asegura que se limpian ejecuciones previas
        self.stop()
        for mac, info in connected_devices.items():
            q = mp.Queue()
            p = mp.Process(target=plot_worker, args=(q, info['alias']), daemon=True)
            p.start()
            self.queues[mac] = q
            self.processes[mac] = p

    def stop(self):
        for q in self.queues.values():
            try: q.put_nowait("STOP")
            except Exception: pass
                
        for p in self.processes.values():
            if p.is_alive():
                p.join(timeout=1.0)
                if p.is_alive():
                    p.terminate()
                    p.join()
                    
        self.queues.clear()
        self.processes.clear()

    def update(self, mac, samples):
        if mac in self.queues and self.processes[mac].is_alive():
            try:
                self.queues[mac].put_nowait(samples)
            except Exception:
                # Si la tubería está rota o inaccesible, se descarta el paquete de visualización
                pass