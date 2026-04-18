import asyncio
from config import SystemConfig
from modules.base_controller import BaseController
from modules.ble_manager import BLEManager
from modules.ai_handler import AIManager
from modules.ui_console import ConsoleUI
from modules.model_config_parser import ModelConfigParser

class AppController(BaseController):
    """Controlador principal enfocado en el Reconocimiento de Actividades (Predicción)."""
    def __init__(self):
        self.config = SystemConfig()
        self.ble = BLEManager(self.config, data_callback=self.data_router)
        super().__init__(self.config, self.ble)
        self.ai_system = None
        self.model_parser = ModelConfigParser(self.config.MODELS_DIR, self.config.MODEL_CONFIGS_DIR)

    def data_router(self, mac, alias, samples, timestamp):
        if self.ai_system and self.ai_system.is_active:
            self.ai_system.process_incoming_data(mac, alias, samples, timestamp)

    async def handle_ai_start(self):
        # Recuperar nombres de modelos
        model_names = self.model_parser.get_available_models()
        modelo_elegido = await ConsoleUI.select_model_from_list(model_names)
        if not modelo_elegido: 
            return

        # Cargar las dependencias y clases del modelo elegido 
        try:
            model_config = self.model_parser.load_config(modelo_elegido)
        except Exception as e:
            ConsoleUI.show_error(str(e))
            await asyncio.sleep(2)
            return

        # Validar si el hardware conectado cumple la topología requerida 
        connected_aliases = [info['alias'] for info in self.ble.connected_devices.values()]        
        faltan = [d for d in model_config.required_devices if d not in connected_aliases]
        
        if faltan:
            ConsoleUI.show_error(f"Topología incorrecta. Faltan estos dispositivos: {faltan}")
            await asyncio.sleep(3)
            return

        ConsoleUI.show_info("Configuración del modelo cargada correctamente.")
        
        # Construir el mapeo de tensores ordenado 
        mac_order = []
        for req in model_config.required_devices:
            for mac, info in self.ble.connected_devices.items(): 
                if info['alias'] == req and mac not in mac_order:
                    mac_order.append(mac)
                    break

        ConsoleUI.show_info(f"Cargando modelo '{modelo_elegido}' en memoria...")            
        self.ai_system = AIManager(modelo_elegido, model_config.classes, mac_order, self.config)
        
        ConsoleUI.show_info("INICIANDO SISTEMA DE RECONOCIMIENTO")
        await ConsoleUI.get_input(">> Pulse ENTER para comenzar y detener el sistema.\n")
        
        try:
            await self.ble.start_listening()
            self.ai_system.start_prediction()
            await ConsoleUI.get_input("") 
        finally:
            if self.ai_system:
                self.ai_system.cleanup() 
            await self.ble.stop_listening()

    async def run(self):
        """Máquina de estados del menú de predicción."""
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
            else:
                ConsoleUI.show_error("Opción no válida.")

        await self.ble.disconnect_all()
        ConsoleUI.show_info("Sistema apagado.")

if __name__ == "__main__":
    app = AppController()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass