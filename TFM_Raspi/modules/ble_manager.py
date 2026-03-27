import asyncio
import subprocess  # Necesario para borrar claves de sistema en Linux
from functools import partial
from bleak import BleakClient, BleakScanner
from modules.data_handler import decode_packet

CHARACTERISTIC_UUID = "0000FF01-0000-1000-8000-00805F9B34FB"
BATTERY_UUID = "00002A19-0000-1000-8000-00805F9B34FB"

class BLEManager:
    def __init__(self, data_callback=None):
        self.connected_devices = {}  # Diccionario: {mac: {client, alias, ...}}
        self.scanner = BleakScanner()
        self.data_callback = data_callback # Enlace con parte de IA
        self.device_states = {} # Registro de estado para control de pérdidas por MAC

    # Callback para manejar apagado/reset de dispositivos => Desconexiones
    def _handle_disconnect(self, client):
        mac = client.address
        alias = "Desconocido"

        if mac in self.connected_devices:
            alias = self.connected_devices[mac]['alias'] 
            del self.connected_devices[mac]

        # Limpiar el estado de secuencia
        if mac in self.device_states:
            del self.device_states[mac]

        # Creamos una tarea en el event loop actual para no bloquear este callback
        # loop = asyncio.get_event_loop()
        # loop.create_task(self._remove_bluetooth_device_async(mac))

        # Mensaje al usuario
        print(f"\n" + "!"*50)
        print(f" [AVISO] {alias} ({mac}) se ha desconectado.")
        print("!"*50 + "\n")
        print(">> (Presione Enter para actualizar el menú): ", end="", flush=True)

    # Callback para manejar notificaciones entrantes
    def _notification_handler(self, alias, mac, sender, data):
       
        # Decodificamos el paquete
        packet = decode_packet(data)

        if packet:    
            samples = packet['samples']       
            seq = packet['sequence_id']
            timestamp = packet['timestamp_start']
            n_samples = len(samples)
            
            # Primer paquete recibido de este dispositivo
            if mac not in self.device_states:
                self.device_states[mac] = {'last_seq': seq, 'last_samples': samples}
                if self.data_callback:
                    self.data_callback(mac, alias, samples, timestamp)
                else:
                    print(f"[{alias}] Dato recibido (sin procesar)")
                    
            # Siguientes paquetes: comprobación de secuencia
            else:
                last_seq = self.device_states[mac]['last_seq']
                expected_seq = last_seq + 1

                # Detección de pérdida
                if seq > expected_seq:
                    lost_count = seq - expected_seq
                    print(f"\n[AVISO - {alias}] Pérdida detectada: {lost_count} paquete(s) no recibidos. Reconstruyendo...")

                    # Calcular la media del paquete anterior
                    last_samples = self.device_states[mac]['last_samples']
                    avg_x = int(sum(s['x'] for s in last_samples) / n_samples)
                    avg_y = int(sum(s['y'] for s in last_samples) / n_samples)
                    avg_z = int(sum(s['z'] for s in last_samples) / n_samples)

                    # Crear el paquete sintético plano
                    synthetic_samples = [{'x': avg_x, 'y': avg_y, 'z': avg_z} for _ in range(n_samples)]

                    # Inyectar los paquetes sintéticos para mantener la sincronización temporal
                    if self.data_callback:
                        for i in range(lost_count):
                            simulated_timestamp = timestamp - ((lost_count - i) * 500)
                            self.data_callback(mac, alias, synthetic_samples, simulated_timestamp)

                # Detección de reinicio del contador 
                elif seq < last_seq:
                    print(f"\n[INFO - {alias}] Reinicio de secuencia BLE detectado (Anterior: {last_seq}, Nuevo: {seq}).")

                # Actualizar el tracker con los datos del paquete actual
                self.device_states[mac]['last_seq'] = seq
                self.device_states[mac]['last_samples'] = samples

                # Pasar el paquete real actual 
                if self.data_callback:
                    self.data_callback(mac, alias, samples, timestamp)
                else:
                    print(f"[{alias}] Dato recibido (sin procesar)")

        else:
            print(f"[{alias}] Error: Paquete corrupto o tamaño inválido.")

    async def scan_available(self):
        return await self.scanner.discover()

    async def connect_and_register(self, device, alias):
        print(f"Conectando a {device.name} ({device.address})...")
        
        # Creamos el cliente pasando el callback de desconexión
        client = BleakClient(
            device.address, 
            disconnected_callback=self._handle_disconnect  # Callback de detección de desconexión
        )
        
        try:
            await client.connect()
            if client.is_connected:
                print(f"Conectado exitosamente a {alias}.")
                
                # Guardamos en nuestro registro
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
            # Al llamar a disconnect, Bleak disparará el callback _handle_disconnect
            await client.disconnect()
            return True
        else:
            print(f"ERROR: El dispositivo {address} no está en la lista de conectados.")
            return False

    async def start_listening(self):        
        for mac, info in self.connected_devices.items():
            client = info['client']
            alias = info['alias'] 
            
            if client.is_connected:
                try:
                    # Inyectar el alias en el callback para saber de quién es.
                    callback_con_alias = partial(self._notification_handler, alias, mac)
                    
                    await client.start_notify(CHARACTERISTIC_UUID, callback_con_alias)
                    
                except Exception as e:
                    print(f"Error al suscribirse a {alias}: {e}")

    async def stop_listening(self):
        # Se hace una copia de los items porque el diccionario cambiará mientras borramos
        items = list(self.connected_devices.items())

        for mac, info in items:
            client = info['client']
            alias = info['alias']
            
            # Solo intentamos parar si sigue conectado
            if client.is_connected:
                try:
                    await client.stop_notify(CHARACTERISTIC_UUID)
                except Exception as e:
                    print(f" -> No se pudo detener {alias} (posiblemente ya desconectado).")
            else:
                print(f" -> {alias} ya estaba desconectado. Omitiendo.")

    async def disconnect_all(self):
        print("Desconectando todos los dispositivos...")
        # Hacemos una copia de las keys porque el diccionario cambiará mientras borramos
        macs = list(self.connected_devices.keys())
        for mac in macs:
            await self.connected_devices[mac]['client'].disconnect()
    
    async def read_battery_level(self, mac):
        if mac in self.connected_devices:
            client = self.connected_devices[mac]['client']
            alias = self.connected_devices[mac]['alias']
            
            if client.is_connected:
                try:
                    battery_data = await client.read_gatt_char(BATTERY_UUID)
                    # El ESP32 envía un uint8_t, lo decodificamos directamente del índice 0
                    return int(battery_data[0])
                except Exception as e:
                    print(f" -> Error leyendo batería de {alias}: {e}")
                    return None
            else:
                print(f" -> {alias} no está conectado.")
                return None
        return None
    