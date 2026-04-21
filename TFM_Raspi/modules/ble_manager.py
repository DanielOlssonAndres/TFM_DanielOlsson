import asyncio
from functools import partial
from bleak import BleakClient, BleakScanner
from modules.data_handler import decode_packet
from modules.packet_sequencer import PacketSequencer
import struct
import time
from config import SystemConfig

class BLEManager:
    def __init__(self, config, data_callback=None):
        self.config = config
        # Diccionario para mantener el estado de las conexiones activas
        self.connected_devices = {}
        # Instancia del escáner BLE para descubrimiento de periféricos
        self.scanner = BleakScanner()
        self.sequencer = PacketSequencer(config, data_callback) if data_callback else None

    async def sync_node_time(self, mac):
        if mac in self.connected_devices:
            client = self.connected_devices[mac]['client']
            alias = self.connected_devices[mac]['alias']
            
            master_time_ms = int(time.time() * 1000)
            payload = struct.pack("<Q", master_time_ms)
            
            t_start_perf = time.perf_counter()
            
            try:
                await client.write_gatt_char(self.config.SYNC_UUID, payload, response=True)
                t_end_perf = time.perf_counter()
                
                rtt_ms = int((t_end_perf - t_start_perf) * 1000)
                
                # Eliminamos las referencias a rtt_corrections y cambiamos el print
                print(f"[*] {alias} sincronizado. Latencia de red BLE: {rtt_ms} ms")
                
            except Exception as e:
                print(f"[!] Error de sincronización: {e}")

    def _handle_disconnect(self, client):
        # Callback invocado automáticamente por la librería Bleak cuando se pierde la conexión
        mac = client.address
        alias = "Desconocido"

        if mac in self.connected_devices:
            alias = self.connected_devices[mac]['alias'] 
            # Eliminación del dispositivo del diccionario de estado activo
            del self.connected_devices[mac]

        # Limpieza (secuenciador)
        if self.sequencer:
            self.sequencer.remove_device(mac)

        print(f"\n" + "!"*50)
        print(f" [AVISO] {alias} ({mac}) se ha desconectado.")
        print("!"*50 + "\n")
        print(">> (Presione Enter para actualizar el menú): ", end="", flush=True)

    def _notification_handler(self, alias, mac, sender, data):
        # Callback ejecutado cada vez que el periférico envía un paquete 
        # Conversión del payload binario a una estructura de datos utilizable
        packet = decode_packet(data, self.config.SAMPLES_PER_PACKET)

        if packet:                        
            if self.sequencer:
                self.sequencer.process_packet(mac, alias, packet)

    async def scan_available(self):
        # Descubrimiento activo de dispositivos  
        # Retorna una lista de objetos BLEDevice
        return await self.scanner.discover()

    async def connect_and_register(self, device, alias):
        print(f"Conectando a {device.name} ({device.address})...")
        # Instanciación del cliente GATT
        client = BleakClient(device.address, disconnected_callback=self._handle_disconnect)
        
        try:
            # Petición de conexión a nivel GAP
            await client.connect()
            if client.is_connected:
                print(f"Conectado exitosamente a {alias}.")
                # Registro del cliente 
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
            # Captura de errores 
            print(f"Error en conexión: {e}")
            return False

    async def disconnect_device(self, address):
        # Desconexión controlada 
        if address in self.connected_devices:
            print(f"Desconectando {address}...")
            client = self.connected_devices[address]['client']
            await client.disconnect()
            return True
        return False

    async def start_listening(self):        
        # Iteración sobre una copia de los items 
        for mac, info in list(self.connected_devices.items()):
            client = info['client']
            alias = info['alias'] 
            if client.is_connected:
                try:
                    callback_con_alias = partial(self._notification_handler, alias, mac)
                    await client.start_notify(self.config.CHARACTERISTIC_UUID, callback_con_alias)
                except Exception as e:
                    print(f"Error al suscribirse a {alias}: {e}")

    async def stop_listening(self):
        # Desuscripción 
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
        # Apagado completo de BLE
        print("Desconectando todos los dispositivos...")
        macs = list(self.connected_devices.keys())
        for mac in macs:
            await self.connected_devices[mac]['client'].disconnect()
    
    async def read_battery_level(self, mac):
        # Petición de lectura de un atributo GATT
        if mac in self.connected_devices:
            client = self.connected_devices[mac]['client']
            alias = self.connected_devices[mac]['alias']
            if client.is_connected:
                try:
                    battery_data = await client.read_gatt_char(self.config.BATTERY_UUID)
                    return int(battery_data[0])
                except Exception as e:
                    print(f" -> Error leyendo batería de {alias}: {e}")
        return None