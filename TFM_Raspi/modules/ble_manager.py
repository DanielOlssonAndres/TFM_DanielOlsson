import asyncio # Para operaciones asíncronas
from bleak import BleakScanner, BleakClient # Librería BLE
try:
    # Importacion si ejecutamos main.py
    from modules.data_handler import decode_packet
except ImportError:
    # Si falla, se esta probando este archivo solo. Importacion directa.
    from data_handler import decode_packet

# Constantes BLE de los dispositivos BLE
UUID_CHAR_DATA = "0000ff01-0000-1000-8000-00805f9b34fb"

class BLEManager:
    # Constructor de la clase
    def __init__(self, registry):
        self.registry = registry # Recibimos el registro como dependencia
        self.active_clients = {} # Diccionario: { "MAC": BleakClient }

    # Función para escanear dispositivos NO registrados
    async def scan_new_devices(self):
        # Escaneo durante 5 segundos y guardamos todos los dispositivos encontrados 
        devices = await BleakScanner.discover(timeout=5.0)
        
        candidates = []
        for d in devices:
            # Filtramos dispositivos que tengan nombre y NO estén ya registrados
            if d.name and not self.registry.is_registered(d.address):
                candidates.append(d)
        return candidates

    # Función para emparejar y registrar un dispositivo BLE
    async def pair_and_register(self, device, alias):
        # Conecta, fuerza el emparejamiento y guarda en registro.
        print(f"Conectando a {device.name} para emparejamiento...")
        
        async with BleakClient(device.address) as client:
            if client.is_connected:
                try:
                    # Intentamos suscribirnos. Si la característica es segura (Read Encrypted),
                    # se iniciará el Pairing/Bonding automáticamente.
                    await client.start_notify(UUID_CHAR_DATA, lambda s, d: None)
                    
                    # Si no da error, estamos emparejados.
                    print("Emparejamiento exitoso")
                    self.registry.save_device(device.address, device.name, alias)
                    return True
                except Exception as e:
                    print(f"Error de seguridad/emparejamiento: {e}")
                    return False
        return False

    # Función para conectarse a los dispositivos ya conocidos (los guardados en el registro)
    async def connect_known_devices(self):
        known_devs = self.registry.get_all_devices()
        
        if not known_devs:
            return

        # Escaneo rápido para ver cuáles están disponibles
        found = await BleakScanner.discover(timeout=3.0)
        found_map = {d.address: d for d in found}

        for stored_dev in known_devs:
            mac = stored_dev["mac"]
            
            # Si lo vemos cerca Y no estamos conectados ya
            if mac in found_map and mac not in self.active_clients:
                # Lanzamos conexión en segundo plano (no bloqueante)
                asyncio.create_task(self._connect_single_device(mac, stored_dev["alias"]))

    # Funcion interna para conectar un solo dispositivo
    async def _connect_single_device(self, mac, alias):
        print(f"[BLE] Intentando conectar a {alias}...")
        client = BleakClient(mac)
        
        try:
            # Intentamos conectar
            await client.connect()
            
            if client.is_connected:
                # Intentamos activar notificaciones (esto dispara la seguridad)
                try:
                    callback = lambda sender, data: self._handle_notification(alias, data)
                    await client.start_notify(UUID_CHAR_DATA, callback)
                    
                    # Si llegamos aquí, todo bien
                    self.active_clients[mac] = client
                    print(f"[BLE] {alias} -> CONECTADO Y SEGURO")
                    
                except Exception as e_auth:
                    # SI FALLA AQUÍ, es probable que las claves no coincidan
                    print(f"[ALERTA] {alias} conectado pero FALLÓ LA SEGURIDAD.")
                    print(f"[ALERTA] Es posible que el dispositivo se haya reseteado.")
                    print(f"Detalle error: {e_auth}")
                    
                    # Desconectamos inmediatamente
                    await client.disconnect()
                    
                    # Eliminar del registro automáticamente si las claves no valen
                    self.registry.remove_device(mac) 

        except Exception as e:
            pass

    # Función interna para manejar notificaciones BLE 
    def _handle_notification(self, alias, data):
        packet = decode_packet(data) # Decodificamos los bytes crudos
        
        if packet:
            # Extraemos los datos que quieres ver
            seq_id = packet['sequence_id']
            timestamp = packet['timestamp_start']
            
            # El paquete tiene 35 muestras, cogemos la primera (índice 0)
            first_sample = packet['samples'][0]
            
            # Imprimimos con el formato solicitado
            print(f"[{alias}] ID: {seq_id} | Time: {timestamp}ms | Dato[0]: {first_sample}")

    # Función para cerrar todas las conexiones BLE
    async def disconnect_all(self):
        for mac, client in self.active_clients.items():
            if client.is_connected:
                await client.disconnect()
        print("Todas las conexiones cerradas.")
