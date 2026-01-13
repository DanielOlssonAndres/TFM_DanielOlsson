import asyncio
import signal
import sys
from modules.ble_manager import BLEManager

# Funciones auxiliares

async def seleccionar_posicion():
    
    opciones_validas = {
        "1": "Mano_Izquierda",
        "2": "Mano_Derecha",
        "3": "Tobillo_Izquierdo",
        "4": "Tobillo_Derecho",
        "5": "Cadera_Izquierda",
        "6": "Cadera_Derecha"
    }

    while True:
        print("\n--- Seleccione posición del dispositivo ---")
        print("1. Mano Izquierda")
        print("2. Mano Derecha")
        print("3. Tobillo Izquierdo")
        print("4. Tobillo Derecho")
        print("5. Cadera Izquierda")
        print("6. Cadera Derecha")
        
        eleccion = await asyncio.to_thread(input, "\nElija una opción: ")
        eleccion = eleccion.strip()

        if eleccion in opciones_validas:
            alias = opciones_validas[eleccion]
            print(f"Posición asignada: {alias}")
            return alias 
        else:
            print(f"ERROR: '{eleccion}' no es válido. Debe elegir un número del 1 al 6.")


async def main():
    ble = BLEManager()

    # Menu principal
    while True:
        # Mostramos lista de conectados
        devs = ble.connected_devices
        print("\n" + "="*40)
        print(f"   Dispositivos Enlazados: {len(devs)}")
        if not devs:
            print(" (Ningún dispositivo enlazado)")
        else:
            for mac, info in devs.items():
                print(f" * {info['alias']} [{mac}]")
        print("="*40)

        print("1. Registrar un nuevo dispositivo")
        print("2. Comenzar la recepción de datos")
        print("3. Finalizar programa")
        
        choice = await asyncio.to_thread(input, "\n>> Seleccione opción: ")

        if choice.strip() == "":
            # Si el usuario solo dio a Enter, se refresca el menú
            continue
        elif choice == "1": # Registrar nuevo dispositivo
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
                    alias = await seleccionar_posicion()
                    
                    # Proceso de conexión
                    await ble.connect_and_register(target, alias)
                else:
                    print(">> Número inválido.")
            except ValueError:
                print(">> Entrada inválida.")

        elif choice == "2": # Iniciar recepción de datos
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
            
            await ble.stop_listening()

        elif choice == "3": # Finalizar programa
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