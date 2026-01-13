import asyncio
import signal
import sys
from modules.ble_manager import BLEManager

# Variable global para detener la escucha
stop_listening_event = asyncio.Event()

async def main():
    ble = BLEManager()

    def handle_exit_signal():
        print("\n[!] Interrupción detectada. Saliendo...")
        sys.exit(0)

    # Menu principal
    while True:
        # Mostramos lista de conectados
        devs = ble.connected_devices
        print("\n" + "="*40)
        print(f"   Dispositivos Enlazados: {len(devs)}")
        print("="*40)
        
        if not devs:
            print(" (Ningún dispositivo enlazado)")
        else:
            for mac, info in devs.items():
                print(f" * {info['alias']} [{mac}]")
        
        print("-" * 40)
        print("1. Registrar un nuevo dispositivo")
        print("2. Comenzar la recepción de datos")
        print("3. Salir (Ctrl+C)")
        
        choice = await asyncio.to_thread(input, "\n>> Seleccione opción: ")

        if choice == "1":
            # --- OPCIÓN 1: REGISTRO ---
            print("\nBuscando dispositivos cercanos...")
            candidates = await ble.scan_available()
            
            valid_candidates = []
            for d in candidates:
                # Que tenga nombre y no esté ya conectado
                if d.name and d.address not in ble.connected_devices:
                    valid_candidates.append(d)

            if not valid_candidates:
                print(">> No se encontraron dispositivos nuevos.")
                continue

            print("\n--- Dispositivos Disponibles ---")
            for i, d in enumerate(valid_candidates):
                print(f"[{i}] {d.name} ({d.address})")
            
            sel = await asyncio.to_thread(input, ">> Nº disp. (o 'BACK' para volver): ")
            if sel.strip().upper() == "BACK":
                continue
            
            try:
                idx = int(sel)
                if 0 <= idx < len(valid_candidates):
                    target = valid_candidates[idx]
                    alias = await asyncio.to_thread(input, f">> Nombre para '{target.name}': ")
                    
                    # Proceso de conexión
                    await ble.connect_and_register(target, alias)
                else:
                    print(">> Número inválido.")
            except ValueError:
                print(">> Entrada inválida.")

        elif choice == "2":
            # --- OPCIÓN 2: RECEPCIÓN ---
            if not ble.connected_devices:
                print(">> Error: No hay dispositivos registrados.")
                await asyncio.sleep(1)
                continue

            print("\n>> INICIANDO RECEPCIÓN DE DATOS")
            print(">> Pulse ENTER para detener y volver al menú.\n")
            
            # Inicio notificaciones
            await ble.start_listening()
            
            # Esperamos a que el usuario pulse Enter 
            await asyncio.to_thread(input)
            
            print(">> Deteniendo...")
            await ble.stop_listening()

        elif choice == "3":
            break
        
        else:
            print("Opción no válida.")

    # Salida limpia
    await ble.disconnect_all()
    print("Sistema apagado.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass