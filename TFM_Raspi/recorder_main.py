import asyncio
import multiprocessing as mp
from config import SystemConfig
from modules.base_controller import BaseController
from modules.ble_manager import BLEManager
from modules.data_recorder import DataRecorder
from modules.ui_console import ConsoleUI

class AppRecorderController(BaseController):
    def __init__(self):
        self.config = SystemConfig()
        self.recorder = DataRecorder(self.config) 
        self.ble = BLEManager(self.config, data_callback=self.recorder.process_incoming_data)
        super().__init__(self.config, self.ble)

    async def handle_recording(self):
        if not self.ble.connected_devices:
            ConsoleUI.show_error("No hay dispositivos registrados para grabar.")
            await asyncio.sleep(1)
            return
        
        await ConsoleUI.get_input("\n>> Se va a iniciar la grabación. Pulse ENTER para continuar...")

        try:
            num_gestures = int(await ConsoleUI.get_input(">> Número de gestos/actividades a grabar: "))
            gestures = []
            for i in range(num_gestures):
                g = await ConsoleUI.get_input(f"   Nombre del gesto {i+1} (ej. Correr, Saltar): ")
                gestures.append(g.strip())
            
            num_frames = int(await ConsoleUI.get_input(">> Número de frames (ventanas) por actividad: "))
        except ValueError:
            ConsoleUI.show_error("Entrada inválida. Debe introducir números enteros.")
            return

        ConsoleUI.show_info(f"RESUMEN DE LA GRABACIÓN: Gestos: {', '.join(gestures)} | Frames por gesto: {num_frames}")
        
        # Selección del modo de visualización de energía
        while True:
            print("\n1. Grabar CON visualizador de energía")
            print("2. Grabar SIN visualizador de energía")
            print("3. Volver al menú principal")
            
            modo = (await ConsoleUI.get_input("\n>> Elija una opción (1-3): ")).strip()
            
            if modo == "1":
                self.recorder.use_visualizer = True
                break
            elif modo == "2":
                self.recorder.use_visualizer = False
                break 
            elif modo == "3":
                return 
            else:
                ConsoleUI.show_error("Opción no válida.")

        # Preparación del entorno de grabación
        self.recorder.clear_memory()
        await self.ble.start_listening()
        
        if self.recorder.use_visualizer:
            self.recorder.start_visualizers(self.ble.connected_devices)

        mac_list = list(self.ble.connected_devices.keys())

        # Bucle de grabación principal por actividad
        for gesture in gestures:
            await ConsoleUI.get_input(f"\n>> Pulse ENTER para comenzar a grabar '{gesture}'...")
            ConsoleUI.show_info(f"[GRABANDO] Gesto: {gesture} | Esperando {num_frames} frames...")
            
            # Forzar re-sincronización precisa justo antes de la captura
            for mac in self.ble.connected_devices.keys():
                await self.ble.sync_node_time(mac)

            self.recorder.start_recording(gesture, num_frames, mac_list)
            last_printed = -1
            active_macs = mac_list.copy()

            # Bucle de monitorización 
            while not self.recorder.is_recording_complete(active_macs):
                await asyncio.sleep(0.1) # Libera CPU
                
                # Verifica si se han desconectado nodos
                for mac in active_macs[:]: 
                    if mac not in self.ble.connected_devices:
                        ConsoleUI.show_error(f"Dispositivo {mac} desconectado. Descartando sus datos...")
                        active_macs.remove(mac)
                        self.recorder.discard_device(mac) 
                
                # Si nos quedamos sin hardware en mitad de la toma, abortamos
                if not active_macs:
                    ConsoleUI.show_error("Todos los dispositivos se desconectaron. Abortando gesto.")
                    break
                
                # Actualización de feedback de consola en la misma línea
                current = self.recorder.get_max_frames_recorded()
                if current != last_printed and current > 0:
                    print(f"\r   -> Grabados {current}/{num_frames} frames...", end='', flush=True)
                    last_printed = current
            
            self.recorder.stop_recording()
            
            if not active_macs:
                ConsoleUI.show_error("Secuencia de grabación interrumpida por desconexión total.")
                break 
            
            print() 
            ConsoleUI.show_info(f"[DETENIDO] Grabación de '{gesture}' finalizada.")
        
        # Limpieza y guardado final
        await self.ble.stop_listening()
        if self.recorder.use_visualizer:
            self.recorder.stop_visualizers()

        archivos_creados = self.recorder.save_data(gestures, self.ble.connected_devices)
        ConsoleUI.show_info("SECUENCIA FINALIZADA. Archivos guardados:")
        for f in archivos_creados:
            print(f"   - {f}")
            
        await ConsoleUI.get_input("\nPulse ENTER para volver al menú...")

    async def run(self):
        """Máquina de estados del menú de grabación."""
        while True:
            ConsoleUI.show_main_menu(self.ble.connected_devices, mode="GRABACIÓN")
            choice = (await ConsoleUI.get_input("\n>> Seleccione opción: ")).strip()

            if choice == "1":
                await self.handle_registration()
            elif choice == "2":
                await self.handle_recording()   
            elif choice == "3":
                await self.handle_disconnection()
            elif choice == "4":
                await self.handle_battery()      
            elif choice == "5":
                break
            else:
                ConsoleUI.show_error("Opción no válida.")

        await self.ble.disconnect_all()
        ConsoleUI.show_info("Sistema apagado.")

if __name__ == "__main__":
    mp.freeze_support() # Necesario en Windows para Multiprocessing 
    app = AppRecorderController()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass