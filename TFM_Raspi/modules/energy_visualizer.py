import sys
import time
import numpy as np
import multiprocessing as mp
import matplotlib.pyplot as plt
from collections import deque

class FiltroExponencial3Ejes:
    def __init__(self, alpha=0.9):
        self.alpha = alpha
        self.g = np.zeros(3)
        self.primera_lectura = True

    def filtrar(self, ax, ay, az):
        a_t = np.array([ax, ay, az])
        if self.primera_lectura:
            self.g = a_t
            self.primera_lectura = False
        self.g = (self.alpha * self.g) + (1.0 - self.alpha) * a_t
        return a_t - self.g

def plot_worker(queue, alias):
    try:
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
    
    while True:
        try:
            updated = False
            while not queue.empty():
                msg = queue.get_nowait()
                if msg == "STOP":
                    plt.close(fig)
                    return
                
                for s in msg:
                    x, y, z = s['x'], s['y'], s['z']
                    a_dyn = filtro.filtrar(x, y, z)
                    energia = (a_dyn[0]**2 + a_dyn[1]**2 + a_dyn[2]**2) ** 0.5
                    
                    x_data.append(x); y_data.append(y); z_data.append(z); e_data.append(energia)
                updated = True
            
            if updated and len(x_data) > 0:
                line_x.set_data(range(len(x_data)), x_data)
                line_y.set_data(range(len(y_data)), y_data)
                line_z.set_data(range(len(z_data)), z_data)
                line_e.set_data(range(len(e_data)), e_data)
                
                ax.relim()
                ax.autoscale_view()
                
            fig.canvas.flush_events()
            time.sleep(0.05)
        except Exception:
            pass

class EnergyVisualizer:
    def __init__(self):
        self.queues = {}
        self.processes = {}

    def start(self, connected_devices):
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
                pass