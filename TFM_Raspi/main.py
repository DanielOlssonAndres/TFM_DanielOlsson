import asyncio
import signal
import sys
import os
from modules.ble_manager import BLEManager
from modules.ai_handler import AIManager

ai_system = None # Variable global para instanciar la IA dinámicamente

# Funciones auxiliares

# Función para enviar los datos solo si la IA está iniciada
def data_router(mac, alias, samples, timestamp):
    if ai_system and ai_system.is_active:
        ai_system.process_incoming_data(mac, alias, samples)

async def seleccionar_posicion():
    opciones_validas = {
        "1": "Mano_Izquierda", "2": "Mano_Derecha",
        "3": "Tobillo_Izquierdo", "4": "Tobillo_Derecho",
        "5": "Cadera_Izquierda", "6": "Cadera_Derecha",
        "7": "Personalizado"
    }

    while True:
        print("\n--- Seleccione posición del dispositivo ---")
        for k, v in opciones_validas.items():
            print(f"{k}. {v.replace('_', ' ')}")
        
        eleccion = await asyncio.to_thread(input, "\nElija una opción: ")
        eleccion = eleccion.strip()

        if eleccion in opciones_validas:
            if eleccion == "7":
                alias = await asyncio.to_thread(input, "Introduzca el alias personalizado: ")
                # Reemplazamos espacios por barras bajas para mantener consistencia en los nombres
                return alias.strip().replace(" ", "_")
            return opciones_validas[eleccion]
        
        print("ERROR: Opción no válida.")


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
        print("4. Consultar niveles de batería")
        print("5. Finalizar programa")
        
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
                
            # Validar y cargar configuración del modelo
            config_path = os.path.join("model_configurations", f"{modelo_elegido}.txt")
            if not os.path.exists(config_path):
                print(f">> [ERROR] Falta el fichero de configuración: {config_path}")
                await asyncio.sleep(2)
                continue
            
            req_devs = []
            clases_finales = []
            try:
                with open(config_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("DEVICES:"):
                            req_devs = [d.strip() for d in line.split("DEVICES:")[1].split(",")]
                        elif line.startswith("CLASSES:"):
                            clases_finales = [c.strip() for c in line.split("CLASSES:")[1].split(",")]
            except Exception as e:
                print(f">> [ERROR] Fallo crítico al leer {config_path}: {e}")
                continue
            
            if not req_devs or not clases_finales:
                print(">> [ERROR] El fichero de configuración está mal formateado o incompleto.")
                await asyncio.sleep(2)
                continue

            # Validar si los dispositivos conectados tienen los alias requeridos
            connected_aliases = [info['alias'] for info in ble.connected_devices.values()]
            faltan = [d for d in req_devs if d not in connected_aliases]
            
            if faltan:
                print("\n>> [ERROR] Los alias de los dispositivos conectados no coinciden con el modelo.")
                print(f"   Requeridos por config: {req_devs}")
                print(f"   Conectados actualmente: {connected_aliases}")
                print(f"   Faltan: {faltan}")
                await asyncio.sleep(3)
                continue

            print(f"\n>> Configuración cargada correctamente.")
            print(f"   Clases a predecir: {clases_finales}")

            # Ordenar las MACs según el orden exacto del fichero de configuración
            mac_order = []
            for req in req_devs:
                for mac, info in ble.connected_devices.items():
                    if info['alias'] == req and mac not in mac_order:
                        mac_order.append(mac)
                        break

            # Instanciar y arrancar IA
            global ai_system
            print(f"\n>> Cargando modelo '{modelo_elegido}' en memoria (esto puede tardar unos segundos)...")            
            ai_system = await asyncio.to_thread(AIManager, modelo_elegido, clases_finales, mac_order)
            
            print("\n>> INICIANDO SISTEMA DE RECONOCIMIENTO MULTI-SENSOR")
            print(">> Pulse ENTER para detener y volver al menú.\n")
            
            try:
                await ble.start_listening()
                ai_system.start_prediction()
                await asyncio.to_thread(input)
            finally:
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

        elif choice == "4": 
            if not ble.connected_devices:
                print(">> No hay dispositivos conectados.")
                await asyncio.sleep(1)
                continue

            print("\n--- Nivel de Batería ---")
            for mac, info in ble.connected_devices.items():
                alias = info['alias']
                nivel = await ble.read_battery_level(mac)
                
                if nivel is not None:
                    print(f" * {alias} ({mac}): {nivel}%")
                else:
                    print(f" * {alias} ({mac}): ERROR DE LECTURA")
                    
            await asyncio.to_thread(input, "\nPulse ENTER para continuar...")

        elif choice == "5": # Finalizar programa
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