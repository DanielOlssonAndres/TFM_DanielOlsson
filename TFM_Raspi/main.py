import asyncio
import signal
import sys
import os
from modules.ble_manager import BLEManager
from modules.ai_handler import AIManager

DEVICE_PREFIXES = {
    "Mano_Izquierda": "MI", "Mano_Derecha": "MD",
    "Tobillo_Izquierdo": "TI", "Tobillo_Derecho": "TD",
    "Cadera_Izquierda": "CI", "Cadera_Derecha": "CD"
}

ai_system = None # Variable global para instanciar la IA dinámicamente

# Funciones auxiliares

# Función para enviar los datos solo si la IA está iniciada
def data_router(mac, alias, samples):
    if ai_system and ai_system.is_active:
        ai_system.process_incoming_data(mac, alias, samples)

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

    ble = BLEManager(data_callback=data_router)

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
        print("3. Desconectar dispositivo")
        print("4. Finalizar programa")
        
        choice = await asyncio.to_thread(input, "\n>> Seleccione opción: ")

        if choice.strip() == "":
            # Si el usuario solo dio a Enter, se refresca el menú
            continue
        elif choice == "1": # Registrar nuevo dispositivo
            print("\nBuscando dispositivos cercanos...")
            candidates = await ble.scan_available()
            
            valid_candidates = []
            for d in candidates:
                # Que tenga nombre y este sea correcto, que tenga direccion y que no este ya conectado 
                if d.name and d.name.startswith("D2526") and d.address not in ble.connected_devices:
                    valid_candidates.append(d)

            if not valid_candidates:
                print(">> No se encontraron dispositivos 'D2526' nuevos.")
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
            # Buscar modelos en la carpeta
            modelos_disponibles = [f.replace('.json', '') for f in os.listdir("models") if f.endswith('.json')]
            if not modelos_disponibles:
                print(">> [ERROR] No hay modelos en la carpeta 'models'.")
                await asyncio.sleep(1)
                continue
                
            print("\n--- Modelos Disponibles ---")
            for i, mod in enumerate(modelos_disponibles):
                print(f"[{i}] {mod}")
                
            sel_mod = await asyncio.to_thread(input, ">> Seleccione modelo (o 'BACK'): ")
            if sel_mod.strip().upper() == "BACK": continue
            
            try:
                modelo_elegido = modelos_disponibles[int(sel_mod)]
            except (ValueError, IndexError):
                print(">> Selección inválida.")
                continue
                
            # Parsear el nombre: ej. MIMDTI_CoSa_1973783
            partes = modelo_elegido.split('_')
            if len(partes) < 2:
                print(">> [ERROR] El modelo no sigue la nomenclatura Dispositivos_Actividades_X.")
                continue
                
            # Extraer bloques de 2 letras
            req_devs = [partes[0][i:i+2] for i in range(0, len(partes[0]), 2)]
            req_acts = [partes[1][i:i+2] for i in range(0, len(partes[1]), 2)]
            
            # Validar dispositivos conectados
            connected_aliases = [info['alias'] for info in ble.connected_devices.values()]
            connected_prefixes = [DEVICE_PREFIXES.get(alias) for alias in connected_aliases]
            
            if sorted(req_devs) != sorted(connected_prefixes):
                print("\n>> [ERROR] Los dispositivos conectados no coinciden con las necesidades del modelo.")
                print(f"   El modelo requiere: {req_devs}")
                print(f"   Usted ha conectado: {connected_prefixes}")
                await asyncio.sleep(2)
                continue
                
            # Solicitar nombres de actividades
            print("\n--- Configuración de Actividades ---")
            clases_finales = []
            for act in req_acts:
                nombre_act = await asyncio.to_thread(input, f"Actividad correspondiente con '{act}': ")
                clases_finales.append(nombre_act.strip())
                
            # Ordenar las MACs según el modelo (Para que la red reciba los datos en orden)
            mac_order = []
            for req in req_devs:
                for mac, info in ble.connected_devices.items():
                    if DEVICE_PREFIXES.get(info['alias']) == req and mac not in mac_order:
                        mac_order.append(mac)
                        break
                        
            # Instanciar y arrancar IA
            global ai_system
            print(f"\n>> Cargando modelo '{modelo_elegido}' en memoria (esto puede tardar unos segundos)...")            
            ai_system = await asyncio.to_thread(AIManager, modelo_elegido, clases_finales, mac_order)
            
            print("\n>> INICIANDO SISTEMA DE RECONOCIMIENTO MULTI-SENSOR")
            print(">> Pulse ENTER para detener y volver al menú.\n")
            
            await ble.start_listening()
            ai_system.start_prediction()
            await asyncio.to_thread(input)
            
            ai_system.stop_prediction()
            await ble.stop_listening()

        elif choice == "3": # Desconectar dispositivo 
            if not ble.connected_devices:
                print(">> No hay dispositivos conectados para eliminar.")
                await asyncio.sleep(1)
                continue

            print("\n--- Seleccione dispositivo a desconectar ---")
            
            # Convertimos las claves (MACs) a una lista para poder usar índices
            mac_list = list(ble.connected_devices.keys())
            
            for i, mac in enumerate(mac_list):
                alias = ble.connected_devices[mac]['alias']
                print(f"[{i}] {alias} ({mac})")
            
            sel = await asyncio.to_thread(input, ">> Nº disp. (o 'BACK' para volver): ")
            
            if sel.strip().upper() == "BACK":
                continue
            
            try:
                idx = int(sel)
                if 0 <= idx < len(mac_list):
                    target_mac = mac_list[idx]
                    await ble.disconnect_device(target_mac)
                    await asyncio.sleep(1) 
                else:
                    print(">> Número inválido.")
            except ValueError:
                print(">> Entrada inválida. Introduzca el número del índice.")

        elif choice == "4": # Finalizar programa
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