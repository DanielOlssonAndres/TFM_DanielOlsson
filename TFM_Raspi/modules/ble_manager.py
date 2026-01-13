import asyncio
import subprocess  # Necesario para borrar claves de sistema en Linux
from functools import partial
from bleak import BleakClient, BleakScanner
from modules.data_handler import decode_packet

CHARACTERISTIC_UUID = "0000FF01-0000-1000-8000-00805F9B34FB"

class BLEManager:
    def __init__(self):
        self.connected_devices = {}  # Diccionario: {mac: {client, alias, ...}}
        self.scanner = BleakScanner()

    # Callback para manejar apagado/reset de dispositivos => Desconexiones
    def _handle_disconnect(self, client):
        
        mac = client.address
        alias = "Desconocido"

        if mac in self.connected_devices:
            # Se guarda el alias antes de borrar
            alias = self.connected_devices[mac]['alias'] 
            # Borramos del diccionario de memoria (actualiza el menú)
            del self.connected_devices[mac]
        try:
            subprocess.run(["bluetoothctl", "remove", mac], check=False, stdout=subprocess.DEVNULL)
        except Exception as e:
            print(f"Error borrando claves de sistema: {e}")

        # Mensaje al usuario
        print(f"\n" + "!"*50)
        print(f" [AVISO] {alias} ({mac}) se ha desconectado.")
        print(f" El dispositivo ha sido eliminado del sistema.")
        print("!"*50 + "\n")
        print(">> (Presione Enter para actualizar el menú): ", end="", flush=True)

    # Callback para manejar notificaciones entrantes
    def _notification_handler(self, alias, sender, data):
       
        # Decodificamos el paquete
        packet = decode_packet(data)

        if packet:           
            seq = packet['sequence_id']
            n_samples = len(packet['samples'])
            
            # Imprimimos resumen
            print(f"[{alias}] Paquete #{seq} recibido ({n_samples} muestras)")

            # LÓGICA PARA ALMACENAR/PROCESAR DATOS PENDIENTE AQUÍ

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

    async def start_listening(self):        
        for mac, info in self.connected_devices.items():
            client = info['client']
            alias = info['alias'] 
            
            if client.is_connected:
                try:
                    # Inyectar el alias en el callback para saber de quién es.
                    callback_con_alias = partial(self._notification_handler, alias)
                    
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
    