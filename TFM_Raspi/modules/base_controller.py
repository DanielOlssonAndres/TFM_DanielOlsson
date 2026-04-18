import asyncio
from modules.ui_console import ConsoleUI

# Contiene la lógica común del sistema (gestión de emparejamiento, batería y desconexión)
class BaseController:
    def __init__(self, config, ble_manager):
        self.config = config
        self.ble = ble_manager

    async def handle_registration(self):
        ConsoleUI.show_info("Buscando dispositivos cercanos...")
        candidates = await self.ble.scan_available()
        
        # Filtro: Solo los módulos propios del proyecto
        valid_candidates = [d for d in candidates if d.name and d.name.startswith("D2526") and d.address not in self.ble.connected_devices]

        # La UI maneja la visualización y devuelve el objeto seleccionado directamente
        target = await ConsoleUI.select_candidate_device(valid_candidates)
        
        if target:
            # Si el usuario seleccionó correctamente, pedimos la posición
            alias = await ConsoleUI.get_position_alias()
            # Registramos a nivel BLE
            await self.ble.connect_and_register(target, alias)

    async def handle_disconnection(self):
        target_mac = await ConsoleUI.select_device_to_disconnect(self.ble.connected_devices)
        
        if target_mac:
            # Si la UI devuelve una MAC válida, ordenamos la desconexión
            await self.ble.disconnect_device(target_mac)

    async def handle_battery(self):
        if not self.ble.connected_devices:
            ConsoleUI.show_info("No hay dispositivos conectados.")
            await asyncio.sleep(1)
            return

        battery_data = []
        # Solicitamos los niveles de batería
        for mac, info in self.ble.connected_devices.items():
            nivel = await self.ble.read_battery_level(mac)
            battery_data.append((info['name'], info['alias'], mac, nivel))
            
        ConsoleUI.show_battery_levels(battery_data)
        await ConsoleUI.get_input("\nPulse ENTER para continuar...")