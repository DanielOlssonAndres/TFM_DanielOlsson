# main.py
import asyncio
import os
from config import SystemConfig
from modules.ble_manager import BLEManager
from modules.ai_handler import AIManager
from modules.ui_console import ConsoleUI

class AppController:
    def __init__(self):
        self.config = SystemConfig()
        self.ble = BLEManager(self.config, data_callback=self.data_router)
        self.ai_system = None

    def data_router(self, mac, alias, samples, timestamp):
        if self.ai_system and self.ai_system.is_active:
            self.ai_system.process_incoming_data(mac, alias, samples, timestamp)

    async def handle_registration(self):
        ConsoleUI.show_info("Buscando dispositivos cercanos...")
        candidates = await self.ble.scan_available()
        
        valid_candidates = [d for d in candidates if d.name and d.name.startswith("D2526") and d.address not in self.ble.connected_devices]

        if not valid_candidates:
            ConsoleUI.show_info("No se encontraron dispositivos 'D2526' nuevos.")
            return

        print("\n--- Dispositivos Disponibles ---")
        for i, d in enumerate(valid_candidates):
            print(f"[{i}] {d.name} ({d.address})")
        
        sel = await ConsoleUI.get_input(">> Nº disp. (o 'BACK' para volver): ")
        if sel.strip().upper() == "BACK": return
        
        try:
            idx = int(sel)
            if 0 <= idx < len(valid_candidates):
                target = valid_candidates[idx]
                alias = await ConsoleUI.get_position_alias()
                await self.ble.connect_and_register(target, alias)
            else:
                ConsoleUI.show_error("Número inválido.")
        except ValueError:
            ConsoleUI.show_error("Entrada inválida.")

    async def handle_ai_start(self):
        modelos_disponibles = [f.replace('.json', '') for f in os.listdir(self.config.MODELS_DIR) if f.endswith('.json')]
        if not modelos_disponibles:
            ConsoleUI.show_error(f"No hay modelos en la carpeta '{self.config.MODELS_DIR}'.")
            await asyncio.sleep(1)
            return
            
        print("\n--- Modelos Disponibles ---")
        for i, mod in enumerate(modelos_disponibles):
            print(f"[{i}] {mod}")
            
        sel_mod = await ConsoleUI.get_input(">> Seleccione modelo (o 'BACK'): ")
        if sel_mod.strip().upper() == "BACK": return
        
        try:
            modelo_elegido = modelos_disponibles[int(sel_mod)]
        except (ValueError, IndexError):
            ConsoleUI.show_error("Selección inválida.")
            return
            
        config_path = os.path.join(self.config.MODEL_CONFIGS_DIR, f"{modelo_elegido}.txt")
        if not os.path.exists(config_path):
            ConsoleUI.show_error(f"Falta el fichero de configuración: {config_path}")
            await asyncio.sleep(2)
            return
        
        req_devs, clases_finales = [], []
        try:
            with open(config_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DEVICES:"):
                        req_devs = [d.strip() for d in line.split("DEVICES:")[1].split(",")]
                    elif line.startswith("CLASSES:"):
                        clases_finales = [c.strip() for c in line.split("CLASSES:")[1].split(",")]
        except Exception as e:
            ConsoleUI.show_error(f"Fallo crítico al leer {config_path}: {e}")
            return
        
        if not req_devs or not clases_finales:
            ConsoleUI.show_error("El fichero de configuración está mal formateado o incompleto.")
            await asyncio.sleep(2)
            return

        connected_aliases = [info['alias'] for info in list(self.ble.connected_devices.values())]        faltan = [d for d in req_devs if d not in connected_aliases]
        
        if faltan:
            ConsoleUI.show_error(f"Los alias conectados no coinciden con el modelo.\nRequeridos: {req_devs}\nFaltan: {faltan}")
            await asyncio.sleep(3)
            return

        ConsoleUI.show_info("Configuración cargada correctamente.")
        
        mac_order = []
        for req in req_devs:
            for mac, info in list(self.ble.connected_devices.items()): 
                if info['alias'] == req and mac not in mac_order:
                    mac_order.append(mac)
                    break

        ConsoleUI.show_info(f"Cargando modelo '{modelo_elegido}'...")            
        self.ai_system = AIManager(modelo_elegido, clases_finales, mac_order, self.config)
        
        ConsoleUI.show_info("INICIANDO SISTEMA DE RECONOCIMIENTO MULTI-SENSOR")
        await ConsoleUI.get_input(">> Pulse ENTER para detener y volver al menú.\n")
        
        try:
            await self.ble.start_listening()
            self.ai_system.start_prediction()
            await ConsoleUI.get_input("") 
        finally:
            if self.ai_system:
                self.ai_system.cleanup() 
            await self.ble.stop_listening()

    async def handle_disconnection(self):
        if not self.ble.connected_devices:
            ConsoleUI.show_info("No hay dispositivos conectados para eliminar.")
            await asyncio.sleep(1)
            return

        print("\n--- Seleccione dispositivo a desconectar ---")
        mac_list = list(self.ble.connected_devices.keys())
        
        for i, mac in enumerate(mac_list):
            alias = self.ble.connected_devices[mac]['alias']
            print(f"[{i}] {alias} ({mac})")
        
        sel = await ConsoleUI.get_input(">> Nº disp. (o 'BACK' para volver): ")
        if sel.strip().upper() == "BACK": return
        
        try:
            idx = int(sel)
            if 0 <= idx < len(mac_list):
                await self.ble.disconnect_device(mac_list[idx])
                await asyncio.sleep(1) 
            else:
                ConsoleUI.show_error("Número inválido.")
        except ValueError:
            ConsoleUI.show_error("Entrada inválida.")

    async def handle_battery(self):
        if not self.ble.connected_devices:
            ConsoleUI.show_info("No hay dispositivos conectados.")
            await asyncio.sleep(1)
            return

        print("\n--- Nivel de Batería ---")
        for mac, info in self.ble.connected_devices.items():
            nivel = await self.ble.read_battery_level(mac)
            estado = f"{nivel}%" if nivel is not None else "ERROR DE LECTURA"
            print(f" * {info['alias']} ({mac}): {estado}")
                
        await ConsoleUI.get_input("\nPulse ENTER para continuar...")

    async def run(self):
        while True:
            ConsoleUI.show_main_menu(self.ble.connected_devices, mode="RECONOCIMIENTO")
            choice = (await ConsoleUI.get_input("\n>> Seleccione opción: ")).strip()

            if choice == "1":
                await self.handle_registration()
            elif choice == "2":
                await self.handle_ai_start()
            elif choice == "3":
                await self.handle_disconnection()
            elif choice == "4":
                await self.handle_battery()
            elif choice == "5":
                break
            elif choice != "":
                ConsoleUI.show_error("Opción no válida.")

        await self.ble.disconnect_all()
        ConsoleUI.show_info("Sistema apagado.")

if __name__ == "__main__":
    app = AppController()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass