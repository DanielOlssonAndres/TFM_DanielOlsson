# modules/ble_manager.py
import asyncio
from functools import partial
from bleak import BleakClient, BleakScanner
from modules.data_handler import decode_packet
from modules.packet_sequencer import PacketSequencer

class BLEManager:
    def __init__(self, config, data_callback=None):
        self.config = config
        self.connected_devices = {}
        self.scanner = BleakScanner()
        # Inyectamos el secuenciador
        self.sequencer = PacketSequencer(config, data_callback) if data_callback else None

    def _handle_disconnect(self, client):
        mac = client.address
        alias = "Desconocido"

        if mac in self.connected_devices:
            alias = self.connected_devices[mac]['alias'] 
            del self.connected_devices[mac]

        # Delegamos la limpieza al secuenciador
        if self.sequencer:
            self.sequencer.remove_device(mac)

        print(f"\n" + "!"*50)
        print(f" [AVISO] {alias} ({mac}) se ha desconectado.")
        print("!"*50 + "\n")
        print(">> (Presione Enter para actualizar el menú): ", end="", flush=True)

    def _notification_handler(self, alias, mac, sender, data):
        # Usamos la constante inyectada de la configuración
        packet = decode_packet(data, self.config.SAMPLES_PER_PACKET)

        if packet:
            if self.sequencer:
                self.sequencer.process_packet(mac, alias, packet)
            else:
                print(f"[{alias}] Dato recibido (sin procesar)")
        else:
            print(f"[{alias}] Error: Paquete corrupto o tamaño inválido.")

    async def scan_available(self):
        return await self.scanner.discover()

    async def connect_and_register(self, device, alias):
        print(f"Conectando a {device.name} ({device.address})...")
        client = BleakClient(device.address, disconnected_callback=self._handle_disconnect)
        
        try:
            await client.connect()
            if client.is_connected:
                print(f"Conectado exitosamente a {alias}.")
                self.connected_devices[device.address] = {
                    "client": client,
                    "alias": alias,
                    "name": device.name
                }
                return True
            else:
                print("Fallo al conectar.")
                return False
        except Exception as e:
            print(f"Error en conexión: {e}")
            return False

    async def disconnect_device(self, address):
        if address in self.connected_devices:
            print(f"Desconectando {address}...")
            client = self.connected_devices[address]['client']
            await client.disconnect()
            return True
        return False

    async def start_listening(self):        
        for mac, info in list(self.connected_devices.items()):
            client = info['client']
            alias = info['alias'] 
            if client.is_connected:
                try:
                    callback_con_alias = partial(self._notification_handler, alias, mac)
                    # Usamos UUID de la config
                    await client.start_notify(self.config.CHARACTERISTIC_UUID, callback_con_alias)
                except Exception as e:
                    print(f"Error al suscribirse a {alias}: {e}")

    async def stop_listening(self):
        items = list(self.connected_devices.items())
        for mac, info in items:
            client = info['client']
            alias = info['alias']
            if client.is_connected:
                try:
                    await client.stop_notify(self.config.CHARACTERISTIC_UUID)
                except Exception as e:
                    print(f" -> No se pudo detener {alias} (posiblemente ya desconectado).")

    async def disconnect_all(self):
        print("Desconectando todos los dispositivos...")
        macs = list(self.connected_devices.keys())
        for mac in macs:
            await self.connected_devices[mac]['client'].disconnect()
    
    async def read_battery_level(self, mac):
        if mac in self.connected_devices:
            client = self.connected_devices[mac]['client']
            alias = self.connected_devices[mac]['alias']
            if client.is_connected:
                try:
                    # Usamos UUID de la config
                    battery_data = await client.read_gatt_char(self.config.BATTERY_UUID)
                    return int(battery_data[0])
                except Exception as e:
                    print(f" -> Error leyendo batería de {alias}: {e}")
        return None