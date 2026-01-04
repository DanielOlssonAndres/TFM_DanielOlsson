import asyncio
import signal
import sys
from modules.device_registry import DeviceRegistry
from modules.ble_manager import BLEManager

# Flag para controlar el bucle principal
running = True

# Función para detectar Ctrl+C y parar el sistema ordenadamente
def handle_exit(sig, frame):
    global running
    print("\n[SISTEMA] Solicitando parada... Espere a que se cierren conexiones.")
    running = False

# Menu interactivo para registrar nuevos dispositivos
async def registration_menu(ble, registry):
    while True:
        print("\n" + "="*30)
        print("      MENU DE REGISTRO")
        print("="*30)
        print("1. Buscar nuevos dispositivos")
        print("2. Ver dispositivos registrados")
        print("3. Volver al modo normal (RUN)")
        
        # Usamos to_thread para no bloquear el bucle asíncrono mientras esperamos al usuario
        opt = await asyncio.to_thread(input, ">> Seleccione opción: ")

        if opt == "1":
            candidates = await ble.scan_new_devices()
            if not candidates:
                print(">> No se encontraron dispositivos nuevos cercanos.")
                continue
            
            print("\n--- Candidatos encontrados ---")
            for i, dev in enumerate(candidates):
                print(f"[{i}] {dev.name} | MAC: {dev.address}")
            
            try:
                sel = await asyncio.to_thread(input, ">> Seleccione número a vincular (o 'c' cancelar): ")
                if sel.lower() == 'c': continue
                
                idx = int(sel)
                # Validamos que el índice exista
                if idx < 0 or idx >= len(candidates):
                    print(">> Número fuera de rango.")
                    continue

                target = candidates[idx]
                alias = await asyncio.to_thread(input, f">> Asigne un nombre a {target.name}: ")
                
                # Llamada al proceso de emparejamiento
                await ble.pair_and_register(target, alias)
                
            except ValueError:
                print(">> Entrada no válida (debe ser un número).")

        elif opt == "2":
            # Mostramos lo que ya tenemos en la base de datos
            devs = registry.get_all_devices()
            print("\n--- Dispositivos Registrados ---")
            for d in devs:
                print(f"* Alias: {d['alias']} | MAC: {d['mac']}")

        elif opt == "3":
            break
        
        else:
            print("Opción no reconocida.")

# Función principal MAIN
async def main():
    global running
    
    # Capturar Ctrl+C
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    print("--- INICIANDO SISTEMA TFM ---")
    
    # Inicializamos módulos
    registry = DeviceRegistry()
    ble = BLEManager(registry)

    print("Pulse ENTER en 3 segundos para ir al MENU DE REGISTRO...")
    print("(Si no pulsa nada, el sistema arrancará automáticamente)")

    try:
        # Esperamos input con timeout de 3 segundos
        await asyncio.wait_for(asyncio.to_thread(input), timeout=3.0)
        # Si el usuario pulsa enter a tiempo, entramos al menú
        await registration_menu(ble, registry)
    except asyncio.TimeoutError:
        print("\nTiempo agotado. Iniciando modo normal...")

    print("\nSistema activo. Monitorizando sensores...")
    
    # Bucle principal
    try:
        while running:
            # Intentamos conectar a los dispositivos conocidos
            await ble.connect_known_devices()
            
            # Dormimos un poco para no saturar la CPU y permitir re-escaneos periódicos
            # Usamos un bucle pequeño de sleep para responder rápido al Ctrl+C
            for _ in range(50): # 5 segundos (50 * 0.1)
                if not running: break
                await asyncio.sleep(0.1)

    except asyncio.CancelledError: 
        print("Tarea principal cancelada")

    finally:
        print("Cerrando conexiones BLE...")
        await ble.disconnect_all()
        print("Programa terminado correctamente.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass