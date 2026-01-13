import asyncio # Para operaciones asíncronas
from bleak import BleakScanner, BleakClient # Librería BLE
try:
    # Importacion si ejecutamos main.py
    from modules.data_handler import decode_packet
except ImportError:
    # Si falla, se esta probando este archivo solo. Importacion directa.
    from data_handler import decode_packet

# Constantes BLE de los dispositivos BLE
UUID_SVC_ACCEL = "000000ff-0000-1000-8000-00805f9b34fb"
UUID_CHAR_DATA = "0000ff01-0000-1000-8000-00805f9b34fb"

class BLEManager:
    # Constructor de la clase
    def __init__(self):
        self.connected_devices = {}

    # Función para escanear dispositivos
    async def scan_available(self):
        print(">> Escaneando aire...")
        devices = await BleakScanner.discover(timeout=4.0)
        return devices

    # Función para emparejar y registrar un dispositivo BLE
    async def connect_and_register(self, device, alias):
        print(f"Intentando conectar a {alias} ({device.address})...")
        
        client = BleakClient(device.address, disconnected_callback=self._on_disconnect)
        
        try:
            await client.connect()
            # Verificación de compatibilidad 
            has_service = False
            for service in client.services:
                if service.uuid == UUID_SVC_ACCEL: # Comprobamos UUID del servicio
                    has_service = True
                    break
            
            if not has_service:
                print(">> ERROR: Dispositivo no compatible.")
                await client.disconnect()
                return False

            # Si es compatible, intentamos emparejar 
            try:
                # Al leer o notificar una característica segura, salta el pairing
                paired = await client.pair(protection_level=2) 
                print(f">> Emparejamiento: {'Exitoso' if paired else 'Fallido/Ya existente'}")
            except Exception as e:
                print(f">> Nota sobre emparejamiento: {e}")

            # Guardamos 
            self.connected_devices[device.address] = {
                "client": client,
                "alias": alias,
                "original_name": device.name
            }
            print(f">> {alias} registrado y conectado correctamente")
            return True

        except Exception as e:
            print(f">> ERROR conectando: {e}")
            return False

    # Callback: Se ejecuta si el ESP32 se desconecta (Botón BLE pulsado o apagado)
    def _on_disconnect(self, client):
        mac = client.address
        if mac in self.connected_devices:
            alias = self.connected_devices[mac]['alias']
            print(f"\n[ALERTA] {alias} ({mac}) se ha desconectado.")
            print("[SISTEMA] Eliminando dispositivo de la lista activa...")
            
            # Eliminamos de la lista 
            del self.connected_devices[mac]
            # Evitamos que se guarden las claves antiguas
            asyncio.create_task(client.unpair()) 

    # Activar las notificaciones
    async def start_listening(self):
        if not self.connected_devices:
            print(">> No hay dispositivos conectados.")
            return

        print("\n>> Activando sensores...")
        for mac, info in self.connected_devices.items():
            client = info["client"]
            alias = info["alias"]
            
            if client.is_connected:
                try:
                    await client.start_notify(
                        UUID_CHAR_DATA, 
                        lambda s, d, a=alias: self._handle_notification(a, d)
                    )
                    print(f"   -> Escuchando a {alias}")
                except Exception as e:
                    print(f"   -> Error escuchando a {alias}: {e}")
            else:
                print(f"   -> {alias} no está conectado (Ignorado)")

    # Parar las notificaciones
    async def stop_listening(self):
        for mac, info in self.connected_devices.items():
            client = info["client"]
            if client.is_connected:
                try:
                    await client.stop_notify(UUID_CHAR_DATA)
                except:
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
        print(">> Cerrando conexiones...")
        # Hacemos copia de las keys porque vamos a borrar del diccionario
        macs = list(self.connected_devices.keys())
        for mac in macs:
            info = self.connected_devices[mac]
            client = info["client"]
            if client.is_connected:
                await client.disconnect()

            try:
                await client.unpair()
            except:
                pass
        self.connected_devices.clear()