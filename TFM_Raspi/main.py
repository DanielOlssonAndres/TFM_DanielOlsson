import asyncio # Para operaciones asíncronas
import signal # Para capturar señales del sistema
from modules.ble_manager import BLEManager

# Flag para controlar el bucle principal
running = True

# Función para detectar Ctrl+C y parar el sistema
def handle_exit(sig, frame):
    global running
    running = False

# Función principal MAIN asíncrona (para no bloquear el loop de eventos)
async def main():
    global running
    
    # Funciones a ejecutar al recibir señales de terminación
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    print("--- INICIANDO SISTEMA ---")
    
    # Se crea una instancia del gestor BLE
    ble = BLEManager()
    
    # Comenzar escaneo de dispositivos BLE y esperar hasta que termine (sin congelar)
    found = await ble.scan()
    if not found:
        print("No se encontro el dispositivo BLE objetivo")
        return

    # Conectar con el dispositivo BLE
    connected = await ble.connect()
    if not connected:
        print("No se pudo conectar con el dispositivo BLE")
        return

    print("Sistema iniciado (Pulse Ctrl + C para terminar)")
    
    # Bucle principal
    try:
        while running:
            # El programa duerme durante 0.1 segundos para no bloquear la CPU 
            # mientras Bluetooth sigue recibiendo datos en segundo plano.
            await asyncio.sleep(0.1)

    # Si el sistema cancela una tarea por cerrar el programa, que no de error
    except asyncio.CancelledError: 
        print("Tarea cancelada")

    finally:
        # Fin de programa correcto
        print("Cerrando conexiones BLE...")
        await ble.disconnect()
        print("Programa terminado.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Para que no aparezcan errores al cerrar con Ctrl+C
        pass