import asyncio # Para operaciones asíncronas
from bleak import BleakScanner, BleakClient # Librería BLE
try:
    # Importacion si ejecutamos main.py
    from modules.data_handler import decode_packet
except ImportError:
    # Si falla, se esta probando este archivo solo. Importacion directa.
    from data_handler import decode_packet

# Constantes BLE de los dispositivos BLE
TARGET_NAME = "Puls_1" 
UUID_SERVICE = "000000ff-0000-1000-8000-00805f9b34fb" 
UUID_CHAR_DATA = "0000ff01-0000-1000-8000-00805f9b34fb" 

class BLEManager:
    def __init__(self): # Constructor de la clase
        self.target_name = TARGET_NAME # Atributo de la clase
        self.client = None # Atributo de la clase
        self.device = None # Atributo de la clase
        print(f"[BLEManager] Inicializado. Buscando objetivo: {self.target_name}")

    # Función para escanear dispositivos BLE 
    async def scan(self):
        print("Buscando dispositivos BLE...")
        # Escaneo durante 5 segundos y guardamos todos los dispositivos encontrados 
        devices = await BleakScanner.discover(timeout=5.0)
        # Se van recorriendo todos los dispositivos encontrados
        for d in devices:
            name = d.name or "Desconocido"
            if name == self.target_name:
                self.device = d
                return True # Devolvemos True si encontramos el dispositivo
        return False # Devolvemos False si no encontramos el dispositivo

    # Función para conectar con el dispositivo BLE
    async def connect(self):
        # Devolvemos False si previamente no se hizo un escaneo exitoso 
        if not self.device: return False 
        
        print(f"Conectando a {self.device.address}...")
        # Creamos el cliente BLE para hablar con la dirección MAC del dispositivo
        self.client = BleakClient(self.device.address)
        
        try:
            # Conexión por BLE (paramos sin congelar la CPU)
            await self.client.connect()
            if self.client.is_connected:
                print(f"Conectado a {self.target_name}")

                # Nos suscribimos a las notificaciones de la característica de datos
                print("Suscribiéndose a notificaciones...")
                # Caada vez que llegue un paquete, se llamara a self.notification_handler
                await self.client.start_notify(UUID_CHAR_DATA, self.notification_handler)
                
                return True
        except Exception as e:
            print(f"ERROR BLE: {e}")
            return False

    # Función para desconectar del dispositivo BLE
    async def disconnect(self):
        # Comprobamos si existe un cliente y si esta conectado
        if self.client and self.client.is_connected:
            print(f"Desconectando de {self.target_name}")
            await self.client.stop_notify(UUID_CHAR_DATA)
            await self.client.disconnect()
            return True
        return False

    # Funcion callback cada vez que llega una notificación BLE
    def notification_handler(self, sender, data):
        # Decodificamos el paquete recibido
        packet = decode_packet(data)
        
        if packet: # Si la decodificacion fue correcta
            seq = packet['sequence_id']
            ts = packet['timestamp_start']
            first_sample = packet['samples'][0] 
            
            print(f"Paquete #{seq} | T: {ts}ms | {first_sample}")
        else:
            print("ERROR: Paquete recibido pero corrupto o incompleto.")

# PRUEBA UNITARIA DEL MÓDULO LANZADO COMO "ble_manager.py" ------------------------------
if __name__ == "__main__":
    async def main():
        manager = BLEManager()
        if await manager.scan():
            if await manager.connect():
                print("Recibiendo datos durante 10 segundos...")
                await asyncio.sleep(10)
                await manager.disconnect()
            
    asyncio.run(main())